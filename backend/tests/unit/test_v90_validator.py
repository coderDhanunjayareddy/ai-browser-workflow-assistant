"""V9.0 Execution Planning Layer — Unit tests: validator.py."""
import time
import pytest
from app.execution_planning import validator, planner
from app.execution_planning.models import (
    ActionType, TargetType, ExecutionMode, make_step, make_plan,
)
from app.authorization.models import make_authorization
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


@pytest.fixture(autouse=True)
def clean():
    auth_reg._reset_for_testing()
    mission_store._reset_for_testing()
    yield
    auth_reg._reset_for_testing()
    mission_store._reset_for_testing()


def _setup(mission_active=True, with_task=True, authorized=True):
    auth = make_authorization("ctr-1", authorized, "ok", "HIGH", time.time() + 3600,
                              mission_id="m-1", task_id="t-1" if with_task else None)
    auth_reg.add(auth)
    state = MissionState.active if mission_active else MissionState.paused
    m = Mission("m-1", "t", "obj", state, task_ids=["t-1"] if with_task else [])
    mission_store.put(m)
    return auth


def _plan_for(auth, runtime_url=None):
    rc = None
    if runtime_url:
        class _RC: last_url = runtime_url
        rc = _RC()
    return planner.create_plan(auth, runtime_context=rc)


class TestValidPlan:
    def test_valid_full(self):
        auth = _setup()
        res = validator.validate(_plan_for(auth, "http://a"))
        assert res.valid is True

    def test_all_checks_present(self):
        auth = _setup()
        res = validator.validate(_plan_for(auth, "http://a"))
        for k in ["authorization_valid", "mission_active", "task_exists",
                  "no_missing_parameters", "rollback_defined", "execution_mode_valid", "has_steps"]:
            assert k in res.checks

    def test_no_errors_when_valid(self):
        auth = _setup()
        res = validator.validate(_plan_for(auth, "http://a"))
        assert res.errors == []

    def test_validated_at_set(self):
        auth = _setup()
        res = validator.validate(_plan_for(auth, "http://a"))
        assert res.validated_at > 0


class TestAuthorizationCheck:
    def test_missing_authorization_fails(self):
        auth = _setup()
        plan = _plan_for(auth, "http://a")
        auth_reg._reset_for_testing()   # remove the auth
        res = validator.validate(plan)
        assert res.checks["authorization_valid"] is False
        assert res.valid is False

    def test_denied_authorization_not_executable(self):
        auth = make_authorization("ctr-1", False, "denied", "HIGH", time.time() + 3600,
                                  mission_id="m-1", task_id="t-1")
        auth_reg.add(auth)
        m = Mission("m-1", "t", "obj", MissionState.active, task_ids=["t-1"])
        mission_store.put(m)
        plan = make_plan(auth.authorization_id, mission_id="m-1", task_id="t-1",
                         created_at=time.time(), execution_mode=ExecutionMode.sequential,
                         steps=[make_step(1, ActionType.read, TargetType.page, "p")],
                         estimated_duration_ms=300, rollback_supported=True, confidence=0.5)
        res = validator.validate(plan)
        assert res.checks["authorization_valid"] is False


class TestMissionCheck:
    def test_paused_mission_fails(self):
        auth = _setup(mission_active=False)
        res = validator.validate(_plan_for(auth, "http://a"))
        assert res.checks["mission_active"] is False

    def test_no_mission_id_skips(self):
        # auth without mission → mission_active check passes vacuously
        auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600,
                                  mission_id=None, task_id=None)
        auth_reg.add(auth)
        res = validator.validate(_plan_for(auth, "http://a"))
        assert res.checks["mission_active"] is True


class TestTaskCheck:
    def test_task_not_attached_fails(self):
        auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600,
                                  mission_id="m-1", task_id="t-999")
        auth_reg.add(auth)
        m = Mission("m-1", "t", "obj", MissionState.active, task_ids=["t-1"])
        mission_store.put(m)
        res = validator.validate(_plan_for(auth, "http://a"))
        assert res.checks["task_exists"] is False

    def test_no_task_id_skips(self):
        auth = _setup(with_task=False)
        res = validator.validate(_plan_for(auth, "http://a"))
        assert res.checks["task_exists"] is True


class TestParameterCheck:
    def test_navigate_missing_url_fails(self):
        auth = _setup()
        plan = make_plan(auth.authorization_id, mission_id="m-1", task_id="t-1",
                         created_at=time.time(), execution_mode=ExecutionMode.sequential,
                         steps=[make_step(1, ActionType.navigate, TargetType.url, "u")],  # no url param
                         estimated_duration_ms=800, rollback_supported=True, confidence=0.5)
        res = validator.validate(plan)
        assert res.checks["no_missing_parameters"] is False

    def test_empty_target_description_fails(self):
        auth = _setup()
        plan = make_plan(auth.authorization_id, mission_id="m-1", task_id="t-1",
                         created_at=time.time(), execution_mode=ExecutionMode.sequential,
                         steps=[make_step(1, ActionType.read, TargetType.page, "")],
                         estimated_duration_ms=300, rollback_supported=True, confidence=0.5)
        res = validator.validate(plan)
        assert res.checks["no_missing_parameters"] is False


class TestRollbackCheck:
    def test_mutating_without_rollback_fails(self):
        from app.execution_planning.models import RollbackAction
        auth = _setup()
        bad_step = make_step(1, ActionType.click, TargetType.element, "btn",
                             rollback_action=RollbackAction.none)
        plan = make_plan(auth.authorization_id, mission_id="m-1", task_id="t-1",
                         created_at=time.time(), execution_mode=ExecutionMode.sequential,
                         steps=[bad_step], estimated_duration_ms=600,
                         rollback_supported=False, confidence=0.5)
        res = validator.validate(plan)
        assert res.checks["rollback_defined"] is False

    def test_readonly_steps_pass_rollback(self):
        auth = _setup()
        plan = make_plan(auth.authorization_id, mission_id="m-1", task_id="t-1",
                         created_at=time.time(), execution_mode=ExecutionMode.sequential,
                         steps=[make_step(1, ActionType.extract, TargetType.region, "c")],
                         estimated_duration_ms=400, rollback_supported=True, confidence=0.5)
        res = validator.validate(plan)
        assert res.checks["rollback_defined"] is True


class TestEmptyPlan:
    def test_no_steps_fails(self):
        auth = _setup()
        plan = make_plan(auth.authorization_id, mission_id="m-1", task_id="t-1",
                         created_at=time.time(), execution_mode=ExecutionMode.sequential,
                         steps=[], estimated_duration_ms=0,
                         rollback_supported=True, confidence=0.5)
        res = validator.validate(plan)
        assert res.checks["has_steps"] is False
        assert res.valid is False
