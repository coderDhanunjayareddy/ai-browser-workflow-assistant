"""V9.0 Execution Planning Layer — Unit tests: rollback.py (RollbackPlanner)."""
import pytest
from app.execution_planning import rollback
from app.execution_planning.models import (
    ActionType, TargetType, RollbackAction, make_step,
)


class TestRollbackForAction:
    def test_navigate(self):
        assert rollback.rollback_for_action(ActionType.navigate) == RollbackAction.navigate_back

    def test_input(self):
        assert rollback.rollback_for_action(ActionType.input) == RollbackAction.clear_input

    def test_click_manual(self):
        assert rollback.rollback_for_action(ActionType.click) == RollbackAction.manual_review

    def test_scroll(self):
        assert rollback.rollback_for_action(ActionType.scroll) == RollbackAction.scroll_restore

    def test_extract_none(self):
        assert rollback.rollback_for_action(ActionType.extract) == RollbackAction.none

    def test_read_none(self):
        assert rollback.rollback_for_action(ActionType.read) == RollbackAction.none


class TestDescribe:
    def test_describe_keys(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "http://a")
        d = rollback.describe(s)
        for k in ["step_id", "order", "action_type", "rollback_action", "reversible", "requires_manual", "target"]:
            assert k in d

    def test_reversible_navigate(self):
        s = make_step(1, ActionType.navigate, TargetType.url, "http://a")
        assert rollback.describe(s)["reversible"] is True

    def test_not_reversible_extract(self):
        s = make_step(1, ActionType.extract, TargetType.region, "c")
        assert rollback.describe(s)["reversible"] is False

    def test_requires_manual_click(self):
        s = make_step(1, ActionType.click, TargetType.element, "btn")
        assert rollback.describe(s)["requires_manual"] is True


class TestPlanRollback:
    def test_reverse_order(self):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, "http://a"),
            make_step(2, ActionType.input, TargetType.form, "field"),
            make_step(3, ActionType.click, TargetType.element, "btn"),
        ]
        meta = rollback.plan_rollback(steps)
        orders = [d["order"] for d in meta["rollback_steps"]]
        assert orders == [3, 2, 1]

    def test_keys(self):
        steps = [make_step(1, ActionType.navigate, TargetType.url, "http://a")]
        meta = rollback.plan_rollback(steps)
        for k in ["rollback_steps", "mutating_steps", "covered_steps", "fully_supported", "manual_steps"]:
            assert k in meta

    def test_mutating_count(self):
        steps = [
            make_step(1, ActionType.navigate, TargetType.url, "http://a"),  # mutating
            make_step(2, ActionType.extract, TargetType.region, "c"),       # not
            make_step(3, ActionType.click, TargetType.element, "btn"),      # mutating
        ]
        meta = rollback.plan_rollback(steps)
        assert meta["mutating_steps"] == 2

    def test_fully_supported_true(self):
        steps = [make_step(1, ActionType.navigate, TargetType.url, "http://a")]
        assert rollback.plan_rollback(steps)["fully_supported"] is True

    def test_fully_supported_false(self):
        bad = make_step(1, ActionType.click, TargetType.element, "btn",
                        rollback_action=RollbackAction.none)
        assert rollback.plan_rollback([bad])["fully_supported"] is False

    def test_manual_steps_counted(self):
        steps = [make_step(1, ActionType.click, TargetType.element, "btn")]  # manual_review
        assert rollback.plan_rollback(steps)["manual_steps"] == 1


class TestIsSupported:
    def test_supported_navigate(self):
        steps = [make_step(1, ActionType.navigate, TargetType.url, "http://a")]
        assert rollback.is_supported(steps) is True

    def test_readonly_supported(self):
        steps = [make_step(1, ActionType.extract, TargetType.region, "c")]
        assert rollback.is_supported(steps) is True

    def test_mutating_without_rollback_unsupported(self):
        bad = make_step(1, ActionType.click, TargetType.element, "btn",
                        rollback_action=RollbackAction.none)
        assert rollback.is_supported([bad]) is False

    def test_empty_supported(self):
        assert rollback.is_supported([]) is True
