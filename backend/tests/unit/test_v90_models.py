"""V9.0 Execution Planning Layer — Unit tests: models.py."""
import pytest
from app.execution_planning.models import (
    PlanStatus, ExecutionMode, ActionType, TargetType, ValidationStrategy,
    RollbackAction, ExecutionStep, ExecutionPlan, PlanValidationResult,
    ACTION_PROFILE, MUTATING_ACTIONS, VALID_EXECUTION_MODES,
    PLANNING_ASSIGNABLE_STATUSES, GATEWAY_ONLY_STATUSES, PLANNER_VERSION,
    make_step, make_plan,
)


class TestPlanStatus:
    def test_draft(self):     assert PlanStatus.draft.value     == "DRAFT"
    def test_ready(self):     assert PlanStatus.ready.value     == "READY"
    def test_executing(self): assert PlanStatus.executing.value == "EXECUTING"
    def test_completed(self): assert PlanStatus.completed.value == "COMPLETED"
    def test_failed(self):    assert PlanStatus.failed.value    == "FAILED"
    def test_aborted(self):   assert PlanStatus.aborted.value   == "ABORTED"
    def test_count(self):     assert len(PlanStatus) == 6
    def test_from_string(self): assert PlanStatus("READY") == PlanStatus.ready
    def test_planning_assignable(self):
        assert PlanStatus.draft in PLANNING_ASSIGNABLE_STATUSES
        assert PlanStatus.ready in PLANNING_ASSIGNABLE_STATUSES
        assert PlanStatus.aborted in PLANNING_ASSIGNABLE_STATUSES
    def test_gateway_only(self):
        assert PlanStatus.executing in GATEWAY_ONLY_STATUSES
        assert PlanStatus.completed in GATEWAY_ONLY_STATUSES
        assert PlanStatus.failed in GATEWAY_ONLY_STATUSES
    def test_no_overlap(self):
        assert PLANNING_ASSIGNABLE_STATUSES.isdisjoint(GATEWAY_ONLY_STATUSES)


class TestExecutionMode:
    def test_sequential(self): assert ExecutionMode.sequential.value == "SEQUENTIAL"
    def test_atomic(self):     assert ExecutionMode.atomic.value     == "ATOMIC"
    def test_dry_run(self):    assert ExecutionMode.dry_run.value    == "DRY_RUN"
    def test_count(self):      assert len(ExecutionMode) == 3
    def test_valid_modes(self): assert len(VALID_EXECUTION_MODES) == 3


class TestActionTypes:
    def test_action_count(self):    assert len(ActionType) == 8
    def test_navigate(self):        assert ActionType.navigate.value == "NAVIGATE"
    def test_extract(self):         assert ActionType.extract.value == "EXTRACT"
    def test_validate(self):        assert ActionType.validate.value == "VALIDATE"
    def test_target_count(self):    assert len(TargetType) == 6
    def test_validation_count(self): assert len(ValidationStrategy) == 5
    def test_rollback_count(self):  assert len(RollbackAction) == 5
    def test_action_profile_complete(self):
        for at in ActionType:
            assert at in ACTION_PROFILE
            assert "duration_ms" in ACTION_PROFILE[at]
            assert "validation" in ACTION_PROFILE[at]
            assert "rollback" in ACTION_PROFILE[at]
            assert "mutating" in ACTION_PROFILE[at]
    def test_mutating_actions(self):
        assert ActionType.navigate in MUTATING_ACTIONS
        assert ActionType.click in MUTATING_ACTIONS
        assert ActionType.input in MUTATING_ACTIONS
        assert ActionType.extract not in MUTATING_ACTIONS
        assert ActionType.read not in MUTATING_ACTIONS


class TestExecutionStep:
    def test_make_step_id(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "http://a")
        assert s.step_id.startswith("step-")

    def test_order(self):
        s = make_step(5, ActionType.read, TargetType.page, "page")
        assert s.order == 5

    def test_default_validation_from_profile(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "http://a")
        assert s.validation_strategy == ValidationStrategy.url_match

    def test_default_rollback_from_profile(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "http://a")
        assert s.rollback_action == RollbackAction.navigate_back

    def test_navigate_is_mutating(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "http://a")
        assert s.is_mutating
        assert s.requires_rollback

    def test_extract_not_mutating(self):
        s = make_step(1, ActionType.extract, TargetType.region, "content")
        assert not s.is_mutating
        assert not s.requires_rollback

    def test_has_rollback_navigate(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "http://a")
        assert s.has_rollback

    def test_no_rollback_extract(self):
        s = make_step(1, ActionType.extract, TargetType.region, "content")
        assert not s.has_rollback

    def test_override_rollback(self):
        s = make_step(1, ActionType.click, TargetType.element, "btn",
                      rollback_action=RollbackAction.none)
        assert s.rollback_action == RollbackAction.none

    def test_parameters_stored(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "u", parameters={"url": "u"})
        assert s.parameters == {"url": "u"}

    def test_to_dict_keys(self):
        d = make_step(1, ActionType.navigate, TargetType.url, "u").to_dict()
        for k in ["step_id", "order", "action_type", "target_type", "target_description",
                  "parameters", "expected_result", "validation_strategy", "rollback_action",
                  "approval_scope", "is_mutating", "requires_rollback", "has_rollback"]:
            assert k in d

    def test_to_dict_enum_strings(self):
        d = make_step(1, ActionType.navigate, TargetType.url, "u").to_dict()
        assert d["action_type"] == "NAVIGATE"
        assert d["target_type"] == "URL"


class TestExecutionPlan:
    def _plan(self, steps=None):
        steps = steps or [make_step(1, ActionType.navigate, TargetType.url, "u", parameters={"url": "u"})]
        return make_plan("auth-1", mission_id="m-1", task_id="t-1", created_at=100.0,
                         execution_mode=ExecutionMode.sequential, steps=steps,
                         estimated_duration_ms=800, rollback_supported=True, confidence=0.7)

    def test_plan_id_prefix(self):
        assert self._plan().plan_id.startswith("plan-")

    def test_status_draft_initial(self):
        assert self._plan().status == PlanStatus.draft

    def test_estimated_steps(self):
        assert self._plan().estimated_steps == 1

    def test_planner_version(self):
        assert self._plan().planner_version == PLANNER_VERSION

    def test_is_ready_false_initial(self):
        assert not self._plan().is_ready

    def test_is_ready_true_when_ready(self):
        p = self._plan()
        p.status = PlanStatus.ready
        assert p.is_ready

    def test_mutating_step_count(self):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, "u", parameters={"url": "u"}),
            make_step(2, ActionType.extract, TargetType.region, "c"),
        ]
        assert self._plan(steps).mutating_step_count == 1

    def test_to_dict_with_steps(self):
        d = self._plan().to_dict(include_steps=True)
        assert "steps" in d
        assert len(d["steps"]) == 1

    def test_to_dict_without_steps(self):
        d = self._plan().to_dict(include_steps=False)
        assert "steps" not in d

    def test_to_dict_keys(self):
        d = self._plan().to_dict()
        for k in ["plan_id", "authorization_id", "mission_id", "task_id", "created_at",
                  "planner_version", "execution_mode", "estimated_steps",
                  "estimated_duration_ms", "rollback_supported", "confidence",
                  "status", "mutating_step_count", "is_ready"]:
            assert k in d

    def test_to_dict_mode_string(self):
        assert self._plan().to_dict()["execution_mode"] == "SEQUENTIAL"


class TestPlanValidationResult:
    def test_to_dict(self):
        r = PlanValidationResult(plan_id="p-1", valid=True, checks={"a": True},
                                 errors=[], validated_at=1.0)
        d = r.to_dict()
        for k in ["plan_id", "valid", "checks", "errors", "validated_at"]:
            assert k in d

    def test_valid_true(self):
        r = PlanValidationResult(plan_id="p-1", valid=True, checks={}, errors=[], validated_at=1.0)
        assert r.valid is True
