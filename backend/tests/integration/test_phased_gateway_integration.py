"""
Phase D — Integration tests: Gateway -> Dispatcher -> Phase-D PlaywrightAdapter.

Drives the UNCHANGED gateway with a Phase D-enabled adapter backed by a fake browser
(no real browser here — the real browser is in the certification suite). Verifies
recovery/validation/monitor flow through the full chain and that the gateway is unchanged.
"""
import time
import pytest

from app.execution_gateway import engine as gateway, registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_gateway.models import RetryConfig, ExecutionState
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl
from app.execution_planning import registry as plan_reg, planner
from app.execution_planning.registry import set_status
from app.execution_planning.models import PlanStatus
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


class FakeLocator:
    def __init__(self, page): self.page = page
    def click(self, **k):
        self.page.click_calls += 1
        if self.page.click_calls <= self.page.click_fail_times:
            raise Exception(self.page.click_fail_msg)
    def fill(self, t, **k): self.page.filled = t
    def inner_text(self): return self.page.body
    def inner_html(self): return f"<b>{self.page.body}</b>"
    def count(self): return self.page.element_count
    def input_value(self): return self.page.field_value
    def wait_for(self, **k): pass
    def scroll_into_view_if_needed(self, **k): self.page.scrolled = True


class FakePage:
    def __init__(self, body="objective satisfied", element_count=1, click_fail_times=0,
                 click_fail_msg="no node found"):
        self.url = "about:blank"; self.body = body; self.element_count = element_count
        self.field_value = ""; self.click_calls = 0; self.click_fail_times = click_fail_times
        self.click_fail_msg = click_fail_msg; self.filled = None; self.scrolled = False; self.events = []
    def is_closed(self): return False
    def goto(self, u, **k): self.url = u
    def title(self): return "T"
    def locator(self, s): return FakeLocator(self)
    def get_by_test_id(self, v): return FakeLocator(self)
    def get_by_label(self, v): return FakeLocator(self)
    def get_by_role(self, v, name=None): return FakeLocator(self)
    def get_by_placeholder(self, v): return FakeLocator(self)
    def get_by_text(self, v): return FakeLocator(self)
    def inner_text(self, sel): return self.body
    def content(self): return f"<html>{self.body}</html>"
    def wait_for_timeout(self, ms): self.events.append(("wait", ms))
    def wait_for_load_state(self, s, timeout=None): pass
    def evaluate(self, js): pass


class FakeSession:
    def __init__(self, page): self.page = page; self.active_tab_id = "tab-0"; self.downloads = []; self.context = None
    def ensure_page(self): return self.page
    def screenshot(self, l=""): return f"/tmp/{l}.png"
    def refresh(self): pass


class FakeMgr:
    def __init__(self, page): self.session = FakeSession(page)
    def get_or_create(self, eid, headless=True): return self.session
    def get(self, eid): return self.session
    def close(self, eid): return True


@pytest.fixture(autouse=True)
def clean():
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl]:
        m._reset_for_testing()
    yield
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl]:
        m._reset_for_testing()


def _ready_plan(mission="m-1"):
    auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600,
                              mission_id=mission, task_id="t-1")
    auth_reg.add(auth)
    mission_store.put(Mission(mission, "t", "objective satisfied", MissionState.active, task_ids=["t-1"]))
    plan = planner.create_plan(auth)
    plan_reg.add(plan)
    set_status(plan.plan_id, PlanStatus.ready)
    return plan_reg.get(plan.plan_id)


def _run(plan, page, **flags):
    base = dict(adaptive=True, recovery=True, post_validation=True)
    base.update(flags)
    adapter = PlaywrightAdapter(session_manager=FakeMgr(page), **base)
    rec = gateway.start(plan.plan_id, auto_run=False, adapter=adapter,
                        retry_config=RetryConfig(max_retries=0))
    adapter.execution_id = rec.execution_id
    return gateway.resume(rec.execution_id, adapter=adapter)


class TestGatewayUnchanged:
    def test_completes_through_gateway(self):
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied here"))
        assert rec.state == ExecutionState.completed

    def test_adapter_name_playwright(self):
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied"))
        assert rec.adapter_name == "playwright"

    def test_command_types(self):
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied"))
        assert [s.command_type for s in rec.step_executions] == ["NAVIGATE", "EXTRACT", "VALIDATE"]

    def test_gateway_analytics(self):
        plan = _ready_plan()
        _run(plan, FakePage(body="objective satisfied"))
        assert ganal.get_analytics()["executions_completed"] == 1


class TestPhaseDFlows:
    def test_monitor_records_steps(self):
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied"))
        assert mon.summary(rec.execution_id)["total_steps"] == 3

    def test_metrics_populated(self):
        plan = _ready_plan()
        _run(plan, FakePage(body="objective satisfied"))
        assert met.get_metrics()["steps_total"] >= 3

    def test_timeline_populated(self):
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied"))
        types = etl.summary(rec.execution_id)["type_counts"]
        assert "started" in types and "completed" in types

    def test_validation_failure_fails_execution(self):
        plan = _ready_plan()
        # canonical VALIDATE expects "objective satisfied"; body lacks it → fails after recovery
        rec = _run(plan, FakePage(body="unrelated"))
        assert rec.state == ExecutionState.failed


class TestMissionIntegration:
    def test_mission_inspect_shows_execution(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        plan = _ready_plan(mission="m-phd")
        _run(plan, FakePage(body="objective satisfied"))
        eg = client.get("/mission/m-phd/inspect").json()["execution_gateway"]
        assert eg["completed_executions"] >= 1


class TestDiagnosticsEndpoints:
    def test_metrics_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        plan = _ready_plan()
        _run(plan, FakePage(body="objective satisfied"))
        r = client.get("/gateway/browser/metrics")
        assert r.status_code == 200
        assert r.json()["steps_total"] >= 3

    def test_monitor_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied"))
        r = client.get(f"/gateway/browser/monitor/{rec.execution_id}")
        assert r.status_code == 200
        assert r.json()["total_steps"] == 3

    def test_timeline_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied"))
        r = client.get(f"/gateway/browser/timeline/{rec.execution_id}")
        assert r.status_code == 200
        assert r.json()["event_count"] > 0

    def test_diagnostics_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        plan = _ready_plan()
        rec = _run(plan, FakePage(body="objective satisfied"))
        r = client.get(f"/gateway/browser/diagnostics/{rec.execution_id}")
        assert r.status_code == 200
        for k in ["recovery_history", "validation_history", "retry_history", "metrics"]:
            assert k in r.json()

    def test_diagnostics_404(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        assert client.get("/gateway/browser/diagnostics/no-such").status_code == 404
