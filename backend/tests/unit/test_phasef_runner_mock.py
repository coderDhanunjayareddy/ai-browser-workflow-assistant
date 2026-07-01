"""Phase F — Unit tests: certification runner in deterministic MOCK mode (no browser).

Certifies the planner + gateway + authorization pipeline for every scenario without a
browser. Real-browser behaviour is certified separately in the guarded integration suite.
"""
import pytest

from app.certification import scenarios, runner, reliability, failure_catalog
from app.certification.models import OutcomeStatus
from app.execution_gateway import registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_planning import registry as plan_reg
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl


@pytest.fixture(autouse=True)
def _clean():
    mods = [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl,
            reliability, failure_catalog]
    for m in mods:
        m._reset_for_testing()
    yield
    for m in mods:
        m._reset_for_testing()


def test_mock_certifies_full_pipeline():
    scs = scenarios.build_scenarios()
    results = runner.certify_all(scs, base_url="", real_browser=False, seen_at=1000.0)
    assert len(results) == len(scs)
    # every scenario's plan builds, authorizes, and runs through the gateway pipeline
    passed = [r for r in results if r.status == OutcomeStatus.passed]
    assert len(passed) == len(scs), [r.scenario_id for r in results if not r.passed]


def test_mock_records_reliability():
    scs = scenarios.build_scenarios()
    runner.certify_all(scs, base_url="", real_browser=False, seen_at=1000.0)
    m = reliability.metrics()
    assert m["workflows_total"] == len(scs)
    assert m["workflow_success_rate"] == 1.0
    # semantic_present criteria recorded latencies deterministically
    assert m["semantic_analysis_ms"]["samples"] >= 10


def test_mock_is_deterministic():
    scs = scenarios.build_scenarios()
    r1 = runner.certify_all(scs, base_url="", real_browser=False, seen_at=1.0)
    states1 = [(r.scenario_id, r.status.value, r.completed_steps) for r in r1]
    reliability._reset_for_testing()
    for m in [ereg, plan_reg, auth_reg, mission_store, mon, met, etl]:
        m._reset_for_testing()
    r2 = runner.certify_all(scs, base_url="", real_browser=False, seen_at=1.0)
    states2 = [(r.scenario_id, r.status.value, r.completed_steps) for r in r2]
    assert states1 == states2


def test_single_scenario_result_shape():
    s = scenarios.build_scenarios()[0]
    r = runner.run_scenario(s, base_url="", real_browser=False, seen_at=1.0)
    d = r.to_dict()
    for k in ["scenario_id", "status", "passed", "execution_state", "completed_steps",
              "total_steps", "duration_ms", "criteria"]:
        assert k in d
    assert r.execution_state == "COMPLETED"  # mock adapter completes deterministically


def test_semantic_criteria_evaluated_in_mock():
    # semantic_present is browser-independent and IS evaluated in mock mode
    login = next(s for s in scenarios.build_scenarios() if s.scenario_id == "cert-login")
    r = runner.run_scenario(login, base_url="", real_browser=False, seen_at=1.0)
    sem = [c for c in r.criteria if c.kind == "SEMANTIC_PRESENT"]
    assert sem and all(c.passed for c in sem)
