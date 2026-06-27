"""V9.0 Execution Planning Layer — Unit tests: inspector.py."""
import time
import pytest
from app.execution_planning import inspector as insp
from app.execution_planning import registry as reg
from app.execution_planning import planner
from app.authorization.models import make_authorization
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    auth_reg._reset_for_testing()
    mission_store._reset_for_testing()
    yield
    reg._reset_for_testing()
    auth_reg._reset_for_testing()
    mission_store._reset_for_testing()


def _make_plan():
    auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600,
                              mission_id="m-1", task_id="t-1")
    auth_reg.add(auth)
    m = Mission("m-1", "t", "obj", MissionState.active, task_ids=["t-1"])
    mission_store.put(m)
    plan = planner.create_plan(auth)
    reg.add(plan)
    return plan


class TestStructure:
    def test_returns_dict(self):
        p = _make_plan()
        assert isinstance(insp.inspect(p.plan_id), dict)

    def test_missing_returns_none(self):
        assert insp.inspect("absent") is None

    def test_keys(self):
        p = _make_plan()
        r = insp.inspect(p.plan_id)
        for k in ["plan_id", "plan", "step_count", "mutating_steps", "rollback",
                  "validation", "authorization", "mission_context",
                  "timeline_summary", "analytics", "registry_stats", "latency_ms"]:
            assert k in r

    def test_plan_id(self):
        p = _make_plan()
        assert insp.inspect(p.plan_id)["plan_id"] == p.plan_id

    def test_step_count(self):
        p = _make_plan()
        assert insp.inspect(p.plan_id)["step_count"] == 3

    def test_plan_has_steps(self):
        p = _make_plan()
        assert len(insp.inspect(p.plan_id)["plan"]["steps"]) == 3


class TestRollbackSection:
    def test_rollback_present(self):
        p = _make_plan()
        rb = insp.inspect(p.plan_id)["rollback"]
        assert "fully_supported" in rb
        assert "rollback_steps" in rb


class TestValidationSection:
    def test_validation_present(self):
        p = _make_plan()
        v = insp.inspect(p.plan_id)["validation"]
        assert v["valid"] is True

    def test_validation_checks(self):
        p = _make_plan()
        v = insp.inspect(p.plan_id)["validation"]
        assert "authorization_valid" in v["checks"]


class TestAuthorizationLinkage:
    def test_authorization_present(self):
        p = _make_plan()
        a = insp.inspect(p.plan_id)["authorization"]
        assert a is not None
        assert a["is_executable"] is True

    def test_mission_context_present(self):
        p = _make_plan()
        mc = insp.inspect(p.plan_id)["mission_context"]
        assert mc is not None
        assert mc["state"] == "ACTIVE"


class TestMeta:
    def test_latency_non_negative(self):
        p = _make_plan()
        assert insp.inspect(p.plan_id)["latency_ms"] >= 0.0

    def test_analytics_present(self):
        p = _make_plan()
        assert "plans_created" in insp.inspect(p.plan_id)["analytics"]
