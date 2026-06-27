"""
Phase C — Integration tests: Gateway -> Dispatcher -> PlaywrightAdapter -> Validation -> State.

Drives the UNCHANGED Phase B gateway with the real PlaywrightAdapter class, but backed
by a fake browser session (no real browser needed here — the real browser is exercised
in the E2E suite). Proves the adapter is a drop-in replacement for the mock.
"""
import time
import pytest

from app.execution_gateway import engine as gateway, registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_gateway.models import RetryConfig, ExecutionState
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_planning import registry as plan_reg, planner
from app.execution_planning.registry import set_status
from app.execution_planning.models import PlanStatus
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


# ── Fake browser backing the real adapter class ───────────────────────────────

class FakeLocator:
    def __init__(self, page): self.page = page
    def click(self, **k): self.page.clicks += 1
    def fill(self, t, **k): self.page.filled = t
    def inner_text(self): return self.page.body
    def inner_html(self): return f"<b>{self.page.body}</b>"
    def count(self): return 1
    def wait_for(self, **k): pass
    def set_input_files(self, f): self.page.uploaded = f


class FakePage:
    def __init__(self, body="objective satisfied here"):
        self.url = "about:blank"; self.body = body; self.clicks = 0
    def is_closed(self): return False
    def goto(self, url, **k): self.url = url
    def title(self): return "Fake"
    def locator(self, s): return FakeLocator(self)
    def get_by_test_id(self, v): return FakeLocator(self)
    def get_by_label(self, v): return FakeLocator(self)
    def get_by_role(self, v, name=None): return FakeLocator(self)
    def inner_text(self, sel): return self.body
    def content(self): return f"<html>{self.body}</html>"
    def wait_for_timeout(self, ms): pass


class FailPage(FakePage):
    def __init__(self, exc): super().__init__(); self._exc = exc
    def inner_text(self, sel): raise self._exc


class FakeSession:
    def __init__(self, page): self.page = page; self.active_tab_id = "tab-0"; self.downloads = []
    def ensure_page(self): return self.page
    def screenshot(self, label=""): return f"/tmp/{label}.png"


class FakeMgr:
    def __init__(self, page): self.session = FakeSession(page)
    def get_or_create(self, eid, headless=True): return self.session
    def get(self, eid): return self.session
    def close(self, eid): return True


@pytest.fixture(autouse=True)
def clean():
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store]:
        m._reset_for_testing()
    yield
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store]:
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


def _run_with_fake(plan, page):
    """Two-step start+resume, binding a fake-backed PlaywrightAdapter (mirrors run.py)."""
    adapter = PlaywrightAdapter(session_manager=FakeMgr(page))
    rec = gateway.start(plan.plan_id, auto_run=False, adapter=adapter,
                        retry_config=RetryConfig(max_retries=0))
    adapter.execution_id = rec.execution_id
    return gateway.resume(rec.execution_id, adapter=adapter)


class TestDropInReplacement:
    def test_completes_with_playwright_adapter(self):
        plan = _ready_plan()
        rec = _run_with_fake(plan, FakePage())
        assert rec.state == ExecutionState.completed

    def test_adapter_name_is_playwright(self):
        plan = _ready_plan()
        rec = _run_with_fake(plan, FakePage())
        assert rec.adapter_name == "playwright"

    def test_all_steps_succeed(self):
        plan = _ready_plan()
        rec = _run_with_fake(plan, FakePage())
        assert rec.completed_steps == 3
        assert rec.failed_steps == 0

    def test_command_types_dispatched(self):
        plan = _ready_plan()
        rec = _run_with_fake(plan, FakePage())
        assert [s.command_type for s in rec.step_executions] == ["NAVIGATE", "EXTRACT", "VALIDATE"]

    def test_audit_recorded(self):
        plan = _ready_plan()
        rec = _run_with_fake(plan, FakePage())
        assert audit.count_for_execution(rec.execution_id) == 3

    def test_gateway_unchanged_analytics(self):
        plan = _ready_plan()
        _run_with_fake(plan, FakePage())
        a = ganal.get_analytics()
        assert a["executions_started"] == 1
        assert a["executions_completed"] == 1


class TestValidationIntegration:
    def test_validation_failure_fails_execution(self):
        # canonical VALIDATE expects "objective satisfied"; body lacks it → validation fails
        plan = _ready_plan()
        rec = _run_with_fake(plan, FakePage(body="totally different content"))
        assert rec.state == ExecutionState.failed
        # the validate step (order 3) is the one that failed validation
        assert rec.step_executions[-1].validation_passed is False

    def test_validation_pass_completes(self):
        plan = _ready_plan()
        rec = _run_with_fake(plan, FakePage(body="the objective satisfied indeed"))
        assert rec.state == ExecutionState.completed


class TestFailurePath:
    def test_transient_error_terminal_with_no_runner_retry(self):
        # extract raises a terminal selector error → step fails → execution FAILED + rollback
        plan = _ready_plan()
        rec = _run_with_fake(plan, FailPage(Exception("no node found")))
        assert rec.state == ExecutionState.failed
        assert len(rec.rollback_history) >= 1


class TestMissionIntegration:
    def test_mission_inspect_shows_playwright_execution(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        plan = _ready_plan(mission="m-pw")
        _run_with_fake(plan, FakePage())
        eg = client.get("/mission/m-pw/inspect").json()["execution_gateway"]
        assert eg["completed_executions"] >= 1


class TestSafetyChain:
    def test_revoked_authorization_blocks(self):
        plan = _ready_plan()
        auth_reg.revoke(plan.authorization_id, reason="t")
        from app.execution_gateway.engine import GatewayError
        with pytest.raises(GatewayError):
            gateway.start(plan.plan_id, auto_run=False)
