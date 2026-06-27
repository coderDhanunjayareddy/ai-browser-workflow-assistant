"""Phase B Execution Gateway — Unit tests: runner.py."""
import pytest
from app.execution_gateway import runner, audit
from app.execution_gateway.mock_adapter import MockBrowserAdapter
from app.execution_gateway.models import ExecutionState, StepOutcome, RetryConfig, make_execution
from app.execution_planning.models import (
    ActionType, TargetType, ExecutionMode, make_step, make_plan,
)


@pytest.fixture(autouse=True)
def clean():
    audit._reset_for_testing()
    yield
    audit._reset_for_testing()


def _plan(steps=None):
    steps = steps or [
        make_step(1, ActionType.navigate, TargetType.url, "http://a", parameters={"url": "http://a"}),
        make_step(2, ActionType.extract, TargetType.region, "content"),
        make_step(3, ActionType.validate, TargetType.page, "result"),
    ]
    return make_plan("auth-1", mission_id="m-1", task_id="t-1", created_at=100.0,
                     execution_mode=ExecutionMode.sequential, steps=steps,
                     estimated_duration_ms=1450, rollback_supported=True, confidence=0.8)


def _record(plan, retry=None):
    return make_execution(plan.plan_id, plan.authorization_id, mission_id="m-1", task_id="t-1",
                          total_steps=len(plan.steps), adapter_name="mock", created_at=100.0,
                          retry_config=retry)


class TestHappyPath:
    def test_completes(self):
        plan = _plan()
        rec = runner.run(_record(plan), plan, MockBrowserAdapter())
        assert rec.state == ExecutionState.completed

    def test_all_steps_succeed(self):
        plan = _plan()
        rec = runner.run(_record(plan), plan, MockBrowserAdapter())
        assert rec.completed_steps == 3
        assert rec.failed_steps == 0

    def test_step_outcomes(self):
        plan = _plan()
        rec = runner.run(_record(plan), plan, MockBrowserAdapter())
        assert all(s.outcome == StepOutcome.success for s in rec.step_executions)

    def test_current_index_advances(self):
        plan = _plan()
        rec = runner.run(_record(plan), plan, MockBrowserAdapter())
        assert rec.current_step_index == 3

    def test_started_finished_set(self):
        plan = _plan()
        rec = runner.run(_record(plan), plan, MockBrowserAdapter())
        assert rec.started_at is not None
        assert rec.finished_at is not None

    def test_audit_per_step(self):
        plan = _plan()
        rec = runner.run(_record(plan), plan, MockBrowserAdapter())
        assert audit.count_for_execution(rec.execution_id) == 3

    def test_command_types(self):
        plan = _plan()
        rec = runner.run(_record(plan), plan, MockBrowserAdapter())
        assert [s.command_type for s in rec.step_executions] == ["NAVIGATE", "EXTRACT", "VALIDATE"]


class TestFailurePath:
    def test_dispatch_failure_fails(self):
        plan = _plan()
        bad = plan.steps[1].step_id
        rec = runner.run(_record(plan), plan, MockBrowserAdapter(failure_steps={bad}))
        assert rec.state == ExecutionState.failed

    def test_stops_at_failure(self):
        plan = _plan()
        bad = plan.steps[1].step_id
        rec = runner.run(_record(plan), plan, MockBrowserAdapter(failure_steps={bad}))
        # step 1 ok, step 2 failed → step 3 never runs
        assert rec.current_step_index == 2
        assert len(rec.step_executions) == 2

    def test_rollback_on_failure(self):
        plan = _plan()
        bad = plan.steps[1].step_id
        rec = runner.run(_record(plan), plan, MockBrowserAdapter(failure_steps={bad}))
        # one completed step (navigate) gets rolled back
        assert len(rec.rollback_history) == 1

    def test_validation_failure_fails(self):
        plan = _plan()
        vbad = plan.steps[0].step_id
        # disable retry to make validation failure terminal immediately
        rec = runner.run(_record(plan, RetryConfig(max_retries=0)), plan,
                         MockBrowserAdapter(validation_fail_steps={vbad}))
        assert rec.state == ExecutionState.failed
        assert rec.step_executions[0].outcome == StepOutcome.validation_failed

    def test_failed_step_counted(self):
        plan = _plan()
        bad = plan.steps[0].step_id
        rec = runner.run(_record(plan, RetryConfig(max_retries=0)), plan,
                         MockBrowserAdapter(failure_steps={bad}))
        assert rec.failed_steps == 1


class TestRetry:
    def test_flaky_step_retried_and_succeeds(self):
        plan = _plan()
        flaky = plan.steps[0].step_id
        rec = runner.run(_record(plan), plan, MockBrowserAdapter(flaky_steps={flaky}))
        assert rec.state == ExecutionState.completed
        # first step took 2 attempts
        assert rec.step_executions[0].attempts == 2

    def test_total_retries(self):
        plan = _plan()
        flaky = plan.steps[0].step_id
        rec = runner.run(_record(plan), plan, MockBrowserAdapter(flaky_steps={flaky}))
        assert rec.total_retries == 1

    def test_retry_exhausted_fails(self):
        plan = _plan()
        bad = plan.steps[0].step_id
        rec = runner.run(_record(plan, RetryConfig(max_retries=2)), plan,
                         MockBrowserAdapter(failure_steps={bad}))
        # 3 attempts all fail → step failed
        assert rec.step_executions[0].attempts == 3
        assert rec.state == ExecutionState.failed


class TestResume:
    def test_run_from_current_index(self):
        plan = _plan()
        rec = _record(plan)
        rec.current_step_index = 2   # skip first two as if already done
        rec.completed_steps = 2
        runner.run(rec, plan, MockBrowserAdapter())
        # only the last step runs
        assert len(rec.step_executions) == 1
        assert rec.state == ExecutionState.completed
