"""Phase B Execution Gateway — Unit tests: rollback_engine.py."""
import pytest
from app.execution_gateway import rollback_engine
from app.execution_gateway.models import StepExecution, StepOutcome


def _step(order, step_id=None):
    return StepExecution(
        step_id=step_id or f"step-{order}", order=order, action_type="NAVIGATE",
        command_type="NAVIGATE", outcome=StepOutcome.success, attempts=1,
        duration_ms=5.0, validation_passed=True,
    )


class TestSimulate:
    def test_reverse_order(self):
        steps = [_step(1), _step(2), _step(3)]
        report = rollback_engine.simulate(steps)
        assert [d["order"] for d in report] == [3, 2, 1]

    def test_marks_rollback_performed(self):
        steps = [_step(1), _step(2)]
        rollback_engine.simulate(steps)
        assert all(s.rollback_performed for s in steps)

    def test_descriptor_fields(self):
        report = rollback_engine.simulate([_step(1)])
        for k in ["step_id", "order", "action_type", "command_type", "simulated", "note"]:
            assert k in report[0]

    def test_simulated_true(self):
        report = rollback_engine.simulate([_step(1)])
        assert report[0]["simulated"] is True

    def test_empty(self):
        assert rollback_engine.simulate([]) == []

    def test_count(self):
        report = rollback_engine.simulate([_step(1), _step(2)])
        assert len(report) == 2

    def test_no_browser_note(self):
        report = rollback_engine.simulate([_step(1)])
        assert "no browser action" in report[0]["note"]
