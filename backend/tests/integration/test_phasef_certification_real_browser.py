"""
Phase F — Real Website Certification (regression certification, real chromium).

Runs EVERY certification scenario against real chromium via the UNCHANGED gateway and
asserts each one passes (or fails-fast where a negative path is certified). This is the
regression baseline: a change must not reduce certification success.

Skips automatically if Playwright/chromium is unavailable.
"""
import os
import tempfile
import time

import pytest

pytest.importorskip("playwright")

from app.certification import scenarios as cert_scenarios
from app.certification import runner as cert_runner
from app.certification import fixtures as cert_fixtures
from app.certification import reliability, failure_catalog, trace
from app.certification.models import OutcomeStatus
from app.execution_gateway import registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_planning import registry as plan_reg
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.execution_gateway.browser import (
    monitor as mon, metrics as met, exec_timeline as etl, session as bsession, run as browser_run,
)

_ALL = cert_scenarios.build_scenarios()


@pytest.fixture(scope="module")
def server():
    srv = cert_fixtures.FixtureServer().start()
    yield srv
    srv.stop()


@pytest.fixture(scope="module")
def chromium_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True); b.close()
        return True
    except Exception as e:  # pragma: no cover
        pytest.skip(f"chromium unavailable: {e}")


@pytest.fixture(autouse=True)
def _clean():
    mods = [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl,
            reliability, failure_catalog]
    for m in mods:
        m._reset_for_testing()
    bsession._reset_for_testing()
    yield
    for m in mods:
        m._reset_for_testing()
    bsession._reset_for_testing()


@pytest.mark.parametrize("scenario", _ALL, ids=[s.scenario_id for s in _ALL])
def test_scenario_certifies(scenario, server, chromium_ok):
    r = cert_runner.run_scenario(scenario, base_url=server.base_url, real_browser=True,
                                 headless=True, seen_at=1000.0)
    failing = [c.to_dict() for c in r.criteria if not c.passed]
    assert r.status == OutcomeStatus.passed, \
        f"{scenario.scenario_id}: state={r.execution_state} failing={failing} detail={r.failure_detail}"


def test_ambiguous_locator_fails_fast(server, chromium_ok):
    """The reliability fix: an ambiguous strict locator is classified AmbiguousLocator and
    fails at attempt 1 (no wasted recovery cycles)."""
    s = next(x for x in _ALL if x.scenario_id == "cert-ambiguous-guard")
    r = cert_runner.run_scenario(s, base_url=server.base_url, real_browser=True, seen_at=1.0)
    assert r.passed
    assert r.execution_state == "FAILED"


def test_recovery_engaged_on_delayed_element(server, chromium_ok):
    s = next(x for x in _ALL if x.scenario_id == "cert-recover")
    cert_runner.run_scenario(s, base_url=server.base_url, real_browser=True, seen_at=1.0)
    assert met.get_metrics()["recoveries_attempted"] >= 1


def test_workflow_trace_after_real_run(server, chromium_ok):
    s = next(x for x in _ALL if x.scenario_id == "cert-login")
    r = cert_runner.run_scenario(s, base_url=server.base_url, real_browser=True,
                                 cleanup=False, seen_at=1.0)
    try:
        assert trace.has_trace(r.execution_id)
        wt = trace.workflow_trace(r.execution_id)
        assert wt["step_trace"] and len(wt["step_trace"]) >= 4
        assert wt["execution_summary"]["total_steps"] >= 4
        assert any(s["lifecycle"] for s in wt["step_trace"])
        assert "semantic_snapshot" in wt
    finally:
        bsession.close(r.execution_id)


# ── Adapter-level upload/download certification (no planner ActionType; documented) ──

def _adapter(execution_id):
    from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
    return PlaywrightAdapter(execution_id=execution_id, headless=True,
                             adaptive=True, recovery=True, post_validation=True)


def test_upload_certified_at_adapter(server, chromium_ok):
    from app.execution_gateway.models import make_command, CommandType
    f = os.path.join(tempfile.gettempdir(), "phasef_cert_upload.txt")
    with open(f, "w") as fh:
        fh.write("certification payload")
    a = _adapter("cert-f-upload")
    try:
        a.navigate(make_command(CommandType.navigate, "s1", 1, server.base_url + "/upload",
                                parameters={"url": server.base_url + "/upload"}))
        r = a.upload(make_command(CommandType.upload, "s2", 2, "file input",
                     parameters={"testid": "file", "files": [f],
                                 "validate_after": {"filename_visible": os.path.basename(f)}}))
        assert r.success is True
        assert r.output["post_validation"]["passed"] is True
    finally:
        a.close()
        os.remove(f)


def test_download_certified_at_adapter(server, chromium_ok):
    from app.execution_gateway.models import make_command, CommandType
    a = _adapter("cert-f-download")
    try:
        a.navigate(make_command(CommandType.navigate, "s1", 1, server.base_url + "/download",
                                parameters={"url": server.base_url + "/download"}))
        r = a.download(make_command(CommandType.download, "s2", 2, "download link",
                       parameters={"testid": "dl", "validate_after": {"file_exists": True}}))
        assert r.success is True
        assert os.path.exists(r.output["details"]["download_path"])
    finally:
        a.close()


def test_overall_certification_pass_rate(server, chromium_ok):
    """Regression gate: the whole suite certifies at 100% against the local baseline."""
    results = cert_runner.certify_all(_ALL, base_url=server.base_url, real_browser=True, seen_at=1.0)
    passed = sum(1 for r in results if r.passed)
    assert passed == len(results), \
        [(r.scenario_id, r.failure_detail) for r in results if not r.passed]
    m = reliability.metrics()
    assert m["workflow_success_rate"] == 1.0
    assert m["duration_ms"]["p95"] > 0
