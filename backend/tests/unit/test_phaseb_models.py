"""Phase B Execution Gateway — Unit tests: models.py."""
import pytest
from app.execution_gateway.models import (
    ExecutionState, CommandType, StepOutcome, TERMINAL_STATES, GATEWAY_VERSION,
    ExecutionCommand, AdapterResult, StepExecution, AuditEntry, RetryConfig,
    ExecutionRecord, make_command, make_audit_entry, make_execution,
)


class TestExecutionState:
    def test_six_states(self):
        assert len(ExecutionState) == 6
    def test_values(self):
        assert ExecutionState.pending.value == "PENDING"
        assert ExecutionState.running.value == "RUNNING"
        assert ExecutionState.paused.value == "PAUSED"
        assert ExecutionState.completed.value == "COMPLETED"
        assert ExecutionState.failed.value == "FAILED"
        assert ExecutionState.aborted.value == "ABORTED"
    def test_terminal_states(self):
        assert ExecutionState.completed in TERMINAL_STATES
        assert ExecutionState.failed in TERMINAL_STATES
        assert ExecutionState.aborted in TERMINAL_STATES
        assert ExecutionState.running not in TERMINAL_STATES
        assert ExecutionState.pending not in TERMINAL_STATES


class TestCommandType:
    def test_nine_commands(self):
        assert len(CommandType) == 9
    def test_values(self):
        for ct, v in [(CommandType.navigate, "NAVIGATE"), (CommandType.click, "CLICK"),
                      (CommandType.type, "TYPE"), (CommandType.wait, "WAIT"),
                      (CommandType.extract, "EXTRACT"), (CommandType.validate, "VALIDATE"),
                      (CommandType.upload, "UPLOAD"), (CommandType.download, "DOWNLOAD"),
                      (CommandType.custom, "CUSTOM")]:
            assert ct.value == v


class TestStepOutcome:
    def test_values(self):
        assert StepOutcome.success.value == "SUCCESS"
        assert StepOutcome.failed.value == "FAILED"
        assert StepOutcome.validation_failed.value == "VALIDATION_FAILED"
        assert StepOutcome.rolled_back.value == "ROLLED_BACK"
    def test_count(self):
        assert len(StepOutcome) == 5


class TestExecutionCommand:
    def test_make_command_id(self):
        c = make_command(CommandType.navigate, "step-1", 1, "http://a")
        assert c.command_id.startswith("cmd-")
    def test_fields(self):
        c = make_command(CommandType.click, "step-1", 2, "btn",
                         parameters={"x": 1}, expected_result="clicked",
                         validation_strategy="DOM_PRESENCE", rollback_action="MANUAL_REVIEW")
        assert c.command_type == CommandType.click
        assert c.step_id == "step-1"
        assert c.order == 2
        assert c.parameters == {"x": 1}
        assert c.validation_strategy == "DOM_PRESENCE"
        assert c.rollback_action == "MANUAL_REVIEW"
    def test_to_dict(self):
        d = make_command(CommandType.navigate, "s", 1, "u").to_dict()
        for k in ["command_id", "command_type", "step_id", "order", "target_description",
                  "parameters", "expected_result", "validation_strategy", "rollback_action"]:
            assert k in d
        assert d["command_type"] == "NAVIGATE"


class TestAdapterResult:
    def test_defaults(self):
        r = AdapterResult(success=True, duration_ms=5.0)
        assert r.validation_passed is True
        assert r.logs == []
    def test_to_dict(self):
        d = AdapterResult(success=True, duration_ms=5.0, logs=["x"]).to_dict()
        for k in ["success", "duration_ms", "logs", "output", "validation_passed", "message"]:
            assert k in d


class TestRetryConfig:
    def test_default_max_retries(self):
        assert RetryConfig().max_retries == 2
    def test_max_attempts(self):
        assert RetryConfig(max_retries=3).max_attempts == 4
    def test_to_dict(self):
        d = RetryConfig().to_dict()
        for k in ["max_retries", "retry_on_validation_failure", "max_attempts"]:
            assert k in d


class TestStepExecution:
    def test_to_dict(self):
        s = StepExecution(step_id="s", order=1, action_type="NAVIGATE", command_type="NAVIGATE",
                          outcome=StepOutcome.success, attempts=1, duration_ms=5.0, validation_passed=True)
        d = s.to_dict()
        for k in ["step_id", "order", "action_type", "command_type", "outcome", "attempts",
                  "duration_ms", "validation_passed", "rollback_performed", "output", "logs"]:
            assert k in d
        assert d["outcome"] == "SUCCESS"


class TestAuditEntry:
    def test_make_audit_entry(self):
        e = make_audit_entry("exec-1", "step-1", 1, "NAVIGATE", 100.0, 5.0, "SUCCESS", True, 0)
        assert e.entry_id.startswith("audit-")
        assert e.execution_id == "exec-1"
    def test_to_dict(self):
        e = make_audit_entry("exec-1", "step-1", 1, "NAVIGATE", 100.0, 5.0, "SUCCESS", True, 0)
        d = e.to_dict()
        for k in ["entry_id", "execution_id", "step_id", "order", "command_type", "timestamp",
                  "duration_ms", "outcome", "validation_passed", "retry_count", "rollback_performed"]:
            assert k in d


class TestExecutionRecord:
    def _rec(self, total=3):
        return make_execution("plan-1", "auth-1", mission_id="m-1", task_id="t-1",
                              total_steps=total, adapter_name="mock", created_at=100.0)
    def test_make_execution_id(self):
        assert self._rec().execution_id.startswith("exec-")
    def test_initial_pending(self):
        assert self._rec().state == ExecutionState.pending
    def test_retry_config_default(self):
        assert self._rec().retry_config.max_retries == 2
    def test_remaining_steps(self):
        r = self._rec(total=5)
        r.current_step_index = 2
        assert r.remaining_steps == 3
    def test_is_terminal_false(self):
        assert self._rec().is_terminal is False
    def test_is_terminal_true(self):
        r = self._rec()
        r.state = ExecutionState.completed
        assert r.is_terminal is True
    def test_total_retries(self):
        r = self._rec()
        r.step_executions = [
            StepExecution("s1", 1, "N", "NAVIGATE", StepOutcome.success, attempts=3, duration_ms=5, validation_passed=True),
            StepExecution("s2", 2, "E", "EXTRACT", StepOutcome.success, attempts=1, duration_ms=4, validation_passed=True),
        ]
        assert r.total_retries == 2
    def test_total_duration(self):
        r = self._rec()
        r.step_executions = [
            StepExecution("s1", 1, "N", "NAVIGATE", StepOutcome.success, attempts=1, duration_ms=5.0, validation_passed=True),
            StepExecution("s2", 2, "E", "EXTRACT", StepOutcome.success, attempts=1, duration_ms=4.0, validation_passed=True),
        ]
        assert r.total_duration_ms == 9.0
    def test_to_dict_keys(self):
        d = self._rec().to_dict()
        for k in ["execution_id", "plan_id", "authorization_id", "mission_id", "task_id",
                  "state", "adapter_name", "current_step_index", "total_steps",
                  "completed_steps", "failed_steps", "remaining_steps", "total_retries",
                  "total_duration_ms", "rollback_history", "retry_config", "preflight", "is_terminal"]:
            assert k in d
    def test_to_dict_with_steps(self):
        assert "step_executions" in self._rec().to_dict(include_steps=True)
    def test_to_dict_without_steps(self):
        assert "step_executions" not in self._rec().to_dict(include_steps=False)
    def test_gateway_version(self):
        assert GATEWAY_VERSION == "1.0"
