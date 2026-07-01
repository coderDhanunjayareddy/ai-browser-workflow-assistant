"""
Phase D — Real Browser Certification (deterministic, local pages, no internet).

Drives REAL chromium through the UNCHANGED gateway with Phase D enabled
(execute_plan_with_browser), certifying: navigation, forms, tables, uploads, downloads,
iframes, multiple tabs, dialogs, validation, retries, and deterministic recoveries.

Skips automatically if Playwright/chromium is unavailable.
"""
import os
import socket
import tempfile
import threading
import time
import http.server
import socketserver

import pytest

pytest.importorskip("playwright")

from app.execution_gateway import registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_gateway.models import ExecutionState
from app.execution_gateway.browser import run as browser_run
from app.execution_gateway.browser import session as bsession
from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl
from app.execution_planning import registry as plan_reg
from app.execution_planning.registry import set_status
from app.execution_planning.models import (
    PlanStatus, ActionType, TargetType, ValidationStrategy, ExecutionMode, make_step, make_plan,
)
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


# ── Local deterministic pages ─────────────────────────────────────────────────
PAGES: dict[str, bytes] = {
    "/": b"""<!doctype html><html><head><title>Form</title></head><body>
      <h1 id="hdr">Welcome Phase D</h1>
      <input id="email" name="email" placeholder="Email" type="text"/>
      <button id="submit" data-testid="submit">Submit</button>
      <div id="result"></div>
      <script>document.getElementById('submit').addEventListener('click',function(){
        document.getElementById('result').textContent='Form submitted';});</script>
    </body></html>""",
    "/table": b"""<!doctype html><html><head><title>Table</title></head><body>
      <table><tr><td id="cell">TableValue</td></tr></table></body></html>""",
    "/late": b"""<!doctype html><html><head><title>Late</title></head><body>
      <div id="slot"></div>
      <script>setTimeout(function(){var b=document.createElement('button');
        b.id='late';b.setAttribute('data-testid','late');b.textContent='Late';
        document.getElementById('slot').appendChild(b);},600);</script></body></html>""",
    "/hidden": b"""<!doctype html><html><head><title>Hidden</title></head><body>
      <button id="hb" data-testid="hb" style="display:none">Hidden</button>
      <script>setTimeout(function(){document.getElementById('hb').style.display='block';},500);
      </script></body></html>""",
    "/upload": b"""<!doctype html><html><head><title>Upload</title></head><body>
      <input id="file" type="file"/><div id="fname"></div>
      <script>document.getElementById('file').addEventListener('change',function(e){
        document.getElementById('fname').textContent='Uploaded: '+(e.target.files[0]?e.target.files[0].name:'');});
      </script></body></html>""",
    "/dl": b"""<!doctype html><html><head><title>DL</title></head><body>
      <a id="dl" href="/download" download="report.txt">Download</a></body></html>""",
    "/dialog": b"""<!doctype html><html><head><title>Dialog</title></head><body>
      <button id="alertbtn" data-testid="alertbtn"
        onclick="alert('hi');document.getElementById('d').textContent='dialog handled'">Alert</button>
      <div id="d"></div></body></html>""",
    "/iframe": b"""<!doctype html><html><head><title>IframeHost</title></head><body>
      <h1 id="top">Iframe Host Page</h1><iframe src="/table"></iframe></body></html>""",
    "/tabs": b"""<!doctype html><html><head><title>Tabs</title></head><body>
      <a id="newtab" href="/table" target="_blank">Open</a></body></html>""",
}
DOWNLOAD_BODY = b"phase-d-download-payload"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/download"):
            self.send_response(200); self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Disposition", 'attachment; filename="report.txt"')
            self.send_header("Content-Length", str(len(DOWNLOAD_BODY))); self.end_headers()
            self.wfile.write(DOWNLOAD_BODY); return
        body = PAGES.get(self.path.split("?")[0], PAGES["/"])
        self.send_response(200); self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    httpd = socketserver.TCPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


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
def clean():
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl]:
        m._reset_for_testing()
    bsession._reset_for_testing()
    yield
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl]:
        m._reset_for_testing()
    bsession._reset_for_testing()


_COUNTER = {"n": 0}


def _setup_plan(steps, mission=None):
    _COUNTER["n"] += 1
    mission = mission or f"m-cert-{_COUNTER['n']}"
    auth = make_authorization(f"ctr-{_COUNTER['n']}", True, "ok", "HIGH", time.time() + 3600,
                              mission_id=mission, task_id="t-1")
    auth_reg.add(auth)
    mission_store.put(Mission(mission, "t", "obj", MissionState.active, task_ids=["t-1"]))
    plan = make_plan(auth.authorization_id, mission_id=mission, task_id="t-1", created_at=time.time(),
                     execution_mode=ExecutionMode.sequential, steps=steps, estimated_duration_ms=0,
                     rollback_supported=True, confidence=0.9)
    plan_reg.add(plan); set_status(plan.plan_id, PlanStatus.ready)
    return plan


class TestNavigationFormValidation:
    def test_form_fill_submit_validate(self, server, chromium_ok):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/"}),
            make_step(2, ActionType.input, TargetType.form, "email",
                      parameters={"id": "email", "value": "tester@example.com",
                                  "validate_after": {"value_equals": "tester@example.com"}}),
            make_step(3, ActionType.click, TargetType.element, "submit",
                      parameters={"testid": "submit", "validate_after": {"text_contains": "Form submitted"}}),
            make_step(4, ActionType.validate, TargetType.page, "submitted text",
                      parameters={"expected_text": "Form submitted"}, expected_result="Form submitted",
                      validation_strategy=ValidationStrategy.text_match),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True)
        assert rec.state == ExecutionState.completed
        assert rec.completed_steps == 4
        # post-validation engaged on the click step
        assert rec.step_executions[2].output.get("post_validation", {}).get("passed") is True


class TestTableExtraction:
    def test_extract_table_cell(self, server, chromium_ok):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/table"}),
            make_step(2, ActionType.extract, TargetType.region, "cell", parameters={"id": "cell", "mode": "text"}),
            make_step(3, ActionType.validate, TargetType.element, "cell exists",
                      parameters={"id": "cell"}, validation_strategy=ValidationStrategy.dom_presence),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True)
        assert rec.state == ExecutionState.completed
        assert "TableValue" in rec.step_executions[1].output["details"]["content_preview"]


class TestRecovery:
    def test_late_element_recovers_and_succeeds(self, server, chromium_ok):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/late"}),
            make_step(2, ActionType.click, TargetType.element, "late button",
                      parameters={"testid": "late", "timeout_ms": 300}),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True, cleanup=False)
        try:
            assert rec.state == ExecutionState.completed
            click = rec.step_executions[1]
            assert click.output["attempts"] >= 2           # first attempt failed, recovered, retried
            assert len(click.output["recovery_used"]) >= 1
            # metrics reflect a recovery
            assert met.get_metrics()["recoveries_attempted"] >= 1
        finally:
            bsession.close(rec.execution_id)

    def test_hidden_element_recovers(self, server, chromium_ok):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/hidden"}),
            make_step(2, ActionType.click, TargetType.element, "hidden button",
                      parameters={"testid": "hb", "timeout_ms": 250}),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True)
        assert rec.state == ExecutionState.completed
        assert rec.step_executions[1].output["attempts"] >= 2

    def test_missing_element_bounded_failure(self, server, chromium_ok):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/"}),
            make_step(2, ActionType.click, TargetType.element, "ghost",
                      parameters={"selector": "#never", "timeout_ms": 300}),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True)
        assert rec.state == ExecutionState.failed
        # bounded — never an infinite loop
        assert rec.step_executions[1].output["attempts"] <= 3


# NOTE: the V9.0 planner's ActionType has no UPLOAD/DOWNLOAD — those are adapter
# capabilities not yet emitted by the planner. They are certified by driving the
# Phase D adapter methods directly against a real browser (the dispatcher/runner path
# is identical; only the action source differs).

def _real_adapter(execution_id):
    from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
    return PlaywrightAdapter(execution_id=execution_id, headless=True,
                             adaptive=True, recovery=True, post_validation=True)


class TestUpload:
    def test_upload_and_validate_filename(self, server, chromium_ok):
        from app.execution_gateway.models import make_command, CommandType
        f = os.path.join(tempfile.gettempdir(), "phased_cert_upload.txt")
        with open(f, "w") as fh:
            fh.write("x")
        a = _real_adapter("cert-upload")
        try:
            a.navigate(make_command(CommandType.navigate, "s1", 1, server + "/upload",
                                    parameters={"url": server + "/upload"}))
            r = a.upload(make_command(CommandType.upload, "s2", 2, "file input",
                         parameters={"id": "file", "files": [f],
                                     "validate_after": {"filename_visible": os.path.basename(f)}}))
            assert r.success is True
            assert r.output["details"]["count"] == 1
            assert r.output["post_validation"]["passed"] is True   # filename visible on page
        finally:
            a.close()
            os.remove(f)


class TestDownload:
    def test_download_and_validate_file(self, server, chromium_ok):
        from app.execution_gateway.models import make_command, CommandType
        a = _real_adapter("cert-download")
        try:
            a.navigate(make_command(CommandType.navigate, "s1", 1, server + "/dl",
                                    parameters={"url": server + "/dl"}))
            r = a.download(make_command(CommandType.download, "s2", 2, "download link",
                           parameters={"id": "dl", "validate_after": {"file_exists": True}}))
            assert r.success is True
            assert r.output["details"]["download_path"]
            assert os.path.exists(r.output["details"]["download_path"])
            assert r.output["post_validation"]["passed"] is True   # downloaded file exists
        finally:
            a.close()


class TestDialog:
    def test_dialog_auto_dismissed(self, server, chromium_ok):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/dialog"}),
            make_step(2, ActionType.click, TargetType.element, "alert button",
                      parameters={"testid": "alertbtn", "validate_after": {"text_contains": "dialog handled"}}),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True)
        assert rec.state == ExecutionState.completed
        assert rec.step_executions[1].output["post_validation"]["passed"] is True


class TestIframe:
    def test_iframe_host_handled(self, server, chromium_ok):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/iframe"}),
            make_step(2, ActionType.extract, TargetType.region, "top heading",
                      parameters={"id": "top", "mode": "text"}),
            make_step(3, ActionType.validate, TargetType.element, "iframe present",
                      parameters={"css": "iframe"}, validation_strategy=ValidationStrategy.dom_presence),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True)
        assert rec.state == ExecutionState.completed
        assert "Iframe Host" in rec.step_executions[1].output["details"]["content_preview"]


class TestMultipleTabs:
    def test_session_multi_tab_registry(self, server, chromium_ok):
        # Certify real multi-tab handling at the BrowserSession level: open a second
        # page in the same context, register + switch tabs, and drive each tab.
        sess = bsession.get_or_create("cert-tabs", headless=True)
        try:
            sess.ensure_page().goto(server + "/")
            assert sess.tab_count() == 1
            p2 = sess.context.new_page()
            p2.goto(server + "/table")
            tid = sess.register_tab(p2)
            assert sess.tab_count() == 2
            assert sess.switch_tab(tid) is True
            assert sess.active_tab_id == tid
            assert "TableValue" in sess.ensure_page().inner_text("body")
            assert sess.switch_tab("tab-0") is True
        finally:
            bsession.close("cert-tabs")

    def test_target_blank_link_click_handled(self, server, chromium_ok):
        # A target=_blank link click must execute without error (adapter is robust to
        # new-window links). Full popup orchestration is a documented basic capability.
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/tabs"}),
            make_step(2, ActionType.click, TargetType.element, "open new tab", parameters={"id": "newtab"}),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True)
        assert rec.state == ExecutionState.completed


class TestDiagnosticsAfterRealRun:
    def test_diagnostics_populated(self, server, chromium_ok):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, server, parameters={"url": server + "/"}),
            make_step(2, ActionType.click, TargetType.element, "submit", parameters={"testid": "submit"}),
        ]
        rec = browser_run.execute_plan_with_browser(_setup_plan(steps).plan_id, headless=True, cleanup=False)
        try:
            d = client.get(f"/gateway/browser/diagnostics/{rec.execution_id}").json()
            assert d["page_url"] is not None
            assert d["locator_strategy_used"] in ("testid", "id", None)
            assert "metrics" in d
            tl = client.get(f"/gateway/browser/timeline/{rec.execution_id}").json()
            assert tl["type_counts"].get("planned", 0) >= 2
            assert "completed" in tl["type_counts"]
        finally:
            bsession.close(rec.execution_id)
