"""Phase B Execution Gateway — Unit tests: inspector.py."""
import time
import pytest
from app.execution_gateway import engine, inspector, registry as exec_reg, analytics as gw_anal, timeline as gw_tl, audit
from app.execution_gateway.mock_adapter import MockBrowserAdapter
from app.execution_gateway.models import RetryConfig
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


def _ready_plan(mission="m-1"):
    auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600,
                              mission_id=mission, task_id="t-1")
    auth_reg.add(auth)
    mission_store.put(Mission(mission, "t", "obj", MissionState.active, task_ids=["t-1"]))
    plan = planner.create_plan(auth)
    plan_reg.add(plan)
    set_status(plan.plan_id, PlanStatus.ready)
    return plan_reg.get(plan.plan_id)


class TestStructure:
    def test_missing_none(self):
        assert inspector.inspect("absent") is None

    def test_keys(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        ins = inspector.inspect(rec.execution_id)
        for k in ["execution_id", "state", "adapter_used", "plan_id", "authorization_id",
                  "current_step", "total_steps", "completed_steps", "failed_steps",
                  "remaining_steps", "execution_history", "retry_history", "rollback_history",
                  "validation_results", "audit_trail", "preflight", "mission_context",
                  "total_retries", "total_duration_ms", "analytics", "registry_stats",
                  "audit_stats", "latency_ms"]:
            assert k in ins

    def test_adapter_used(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        assert inspector.inspect(rec.execution_id)["adapter_used"] == "mock"

    def test_completed_state(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        ins = inspector.inspect(rec.execution_id)
        assert ins["state"] == "COMPLETED"
        assert ins["completed_steps"] == 3
        assert ins["remaining_steps"] == 0


class TestHistory:
    def test_execution_history(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        ins = inspector.inspect(rec.execution_id)
        assert len(ins["execution_history"]) == 3

    def test_validation_results(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        ins = inspector.inspect(rec.execution_id)
        assert len(ins["validation_results"]) == 3
        assert all(v["validation_passed"] for v in ins["validation_results"])

    def test_audit_trail(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        ins = inspector.inspect(rec.execution_id)
        assert len(ins["audit_trail"]) == 3

    def test_retry_history_on_flaky(self):
        plan = _ready_plan()
        flaky = plan.steps[0].step_id
        rec = engine.start(plan.plan_id, adapter=MockBrowserAdapter(flaky_steps={flaky}))
        ins = inspector.inspect(rec.execution_id)
        assert len(ins["retry_history"]) == 1

    def test_rollback_history_on_failure(self):
        plan = _ready_plan()
        bad = plan.steps[1].step_id
        rec = engine.start(plan.plan_id, adapter=MockBrowserAdapter(failure_steps={bad}))
        ins = inspector.inspect(rec.execution_id)
        assert len(ins["rollback_history"]) == 1


class TestCurrentStep:
    def test_current_step_none_when_done(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        assert inspector.inspect(rec.execution_id)["current_step"] is None

    def test_current_step_set_when_pending(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id, auto_run=False)
        cs = inspector.inspect(rec.execution_id)["current_step"]
        assert cs is not None
        assert cs["index"] == 0


class TestMeta:
    def test_latency(self):
        plan = _ready_plan()
        rec = engine.start(plan.plan_id)
        assert inspector.inspect(rec.execution_id)["latency_ms"] >= 0.0

    def test_mission_context(self):
        plan = _ready_plan(mission="m-ctx")
        rec = engine.start(plan.plan_id)
        mc = inspector.inspect(rec.execution_id)["mission_context"]
        assert mc["state"] == "ACTIVE"
