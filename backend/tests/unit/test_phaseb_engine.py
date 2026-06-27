"""Phase B Execution Gateway — Unit tests: engine.py (gateway orchestration)."""
import time
import pytest
from app.execution_gateway import engine, registry as exec_reg, analytics as gw_anal, timeline as gw_tl, audit
from app.execution_gateway.engine import GatewayError
from app.execution_gateway.models import ExecutionState, RetryConfig
from app.execution_gateway.mock_adapter import MockBrowserAdapter
from app.execution_planning import registry as plan_reg, planner
from app.execution_planning.registry import set_status
from app.execution_planning.models import PlanStatus
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


@pytest.fixture(autouse=True)
def clean():
    for m in [exec_reg, gw_anal, gw_tl, audit, plan_reg, auth_reg, mission_store]:
        m._reset_for_testing()
    yield
    for m in [exec_reg, gw_anal, gw_tl, audit, plan_reg, auth_reg, mission_store]:
        m._reset_for_testing()


def _ready_plan(mission="m-1", task="t-1", active=True, authorized=True):
    auth = make_authorization("ctr-1", authorized, "ok", "HIGH", time.time() + 3600,
                              mission_id=mission, task_id=task)
    auth_reg.add(auth)
    if mission:
        state = MissionState.active if active else MissionState.paused
        mission_store.put(Mission(mission, "t", "obj", state, task_ids=[task] if task else []))
    plan = planner.create_plan(auth)
    plan_reg.add(plan)
    set_status(plan.plan_id, PlanStatus.ready)
    return plan_reg.get(plan.plan_id)


class TestPreflight:
    def test_ready_plan_passes(self):
        plan = _ready_plan()
        assert engine.preflight(plan)["passed"] is True

    def test_draft_plan_fails(self):
        plan = _ready_plan()
        set_status(plan.plan_id, PlanStatus.draft)
        report = engine.preflight(plan_reg.get(plan.plan_id))
        assert report["passed"] is False
        assert report["checks"]["plan_ready"] is False

    def test_paused_mission_fails(self):
        plan = _ready_plan(active=False)
        assert engine.preflight(plan)["checks"]["mission_active"] is False

    def test_preflight_checks_present(self):
        plan = _ready_plan()
        checks = engine.preflight(plan)["checks"]
        for k in ["plan_ready", "authorization_valid", "mission_active",
                  "governance_present", "approval_present", "runtime_present", "browser_sync_present"]:
            assert k in checks


class TestStart:
    def test_start_completes(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        assert rec.state == ExecutionState.completed

    def test_start_missing_plan_404(self):
        with pytest.raises(GatewayError) as ei:
            engine.start("no-plan")
        assert ei.value.status_code == 404

    def test_start_draft_plan_409(self):
        plan = _ready_plan()
        set_status(plan.plan_id, PlanStatus.draft)
        with pytest.raises(GatewayError) as ei:
            engine.start(plan.plan_id)
        assert ei.value.status_code == 409

    def test_start_stores_record(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        assert exec_reg.get(rec.execution_id) is not None

    def test_start_records_analytics(self):
        plan = _ready_plan()
        engine.start(plan.plan_id)
        a = gw_anal.get_analytics()
        assert a["executions_started"] == 1
        assert a["executions_completed"] == 1

    def test_start_records_timeline(self):
        plan = _ready_plan(mission="m-tl")
        engine.start(plan.plan_id)
        events = {e["event_type"] for e in gw_tl.get("m-tl")}
        assert "started" in events
        assert "completed" in events

    def test_start_no_autorun_pending(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id, auto_run=False)
        assert rec.state == ExecutionState.pending

    def test_start_preflight_attached(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        assert rec.preflight["passed"] is True

    def test_failure_path_state(self):
        plan = _ready_plan()
        bad = plan.steps[1].step_id
        rec = engine.start(plan.plan_id, adapter=MockBrowserAdapter(failure_steps={bad}))
        assert rec.state == ExecutionState.failed

    def test_failure_records_analytics(self):
        plan = _ready_plan()
        bad = plan.steps[0].step_id
        engine.start(plan.plan_id, adapter=MockBrowserAdapter(failure_steps={bad}),
                     retry_config=RetryConfig(max_retries=0))
        assert gw_anal.get_analytics()["executions_failed"] == 1


class TestPauseResume:
    def test_pause_pending(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id, auto_run=False)
        paused = engine.pause(rec.execution_id)
        assert paused.state == ExecutionState.paused

    def test_pause_completed_409(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)  # completes
        with pytest.raises(GatewayError) as ei:
            engine.pause(rec.execution_id)
        assert ei.value.status_code == 409

    def test_resume_runs_to_completion(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id, auto_run=False)
        engine.pause(rec.execution_id)
        resumed = engine.resume(rec.execution_id)
        assert resumed.state == ExecutionState.completed

    def test_resume_from_pending(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id, auto_run=False)
        resumed = engine.resume(rec.execution_id)
        assert resumed.state == ExecutionState.completed

    def test_pause_missing_404(self):
        with pytest.raises(GatewayError) as ei:
            engine.pause("no-exec")
        assert ei.value.status_code == 404


class TestAbort:
    def test_abort_pending(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id, auto_run=False)
        aborted = engine.abort(rec.execution_id)
        assert aborted.state == ExecutionState.aborted

    def test_abort_completed_409(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        with pytest.raises(GatewayError) as ei:
            engine.abort(rec.execution_id)
        assert ei.value.status_code == 409

    def test_abort_records_analytics(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id, auto_run=False)
        engine.abort(rec.execution_id)
        assert gw_anal.get_analytics()["executions_aborted"] == 1

    def test_abort_missing_404(self):
        with pytest.raises(GatewayError) as ei:
            engine.abort("no-exec")
        assert ei.value.status_code == 404
