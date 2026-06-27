"""Phase B Execution Gateway — Unit tests: validation.py."""
import pytest
from app.execution_gateway import validation
from app.execution_gateway.models import AdapterResult, CommandType, make_command


def _cmd(strategy="DOM_PRESENCE", rollback="NAVIGATE_BACK"):
    return make_command(CommandType.navigate, "s", 1, "t",
                        validation_strategy=strategy, rollback_action=rollback)


class TestValidationPass:
    def test_success_and_validation(self):
        r = AdapterResult(success=True, duration_ms=5.0, validation_passed=True)
        out = validation.validate(_cmd(), r)
        assert out.passed is True

    def test_checks_present(self):
        out = validation.validate(_cmd(), AdapterResult(success=True, duration_ms=5.0))
        for k in ["dispatch_succeeded", "strategy_passed", "rollback_metadata_present"]:
            assert k in out.checks

    def test_none_strategy_passes(self):
        r = AdapterResult(success=True, duration_ms=5.0, validation_passed=False)
        # NONE strategy → validation_passed irrelevant
        out = validation.validate(_cmd(strategy="NONE"), r)
        assert out.passed is True

    def test_rollback_metadata_present(self):
        out = validation.validate(_cmd(rollback="NAVIGATE_BACK"), AdapterResult(success=True, duration_ms=5.0))
        assert out.checks["rollback_metadata_present"] is True


class TestValidationFail:
    def test_dispatch_failure_fails(self):
        r = AdapterResult(success=False, duration_ms=5.0, validation_passed=True)
        out = validation.validate(_cmd(), r)
        assert out.passed is False
        assert out.checks["dispatch_succeeded"] is False

    def test_strategy_failure_fails(self):
        r = AdapterResult(success=True, duration_ms=5.0, validation_passed=False)
        out = validation.validate(_cmd(strategy="DOM_PRESENCE"), r)
        assert out.passed is False
        assert out.checks["strategy_passed"] is False

    def test_reason_on_dispatch_fail(self):
        r = AdapterResult(success=False, duration_ms=5.0)
        out = validation.validate(_cmd(), r)
        assert "dispatch failure" in out.reason

    def test_reason_on_strategy_fail(self):
        r = AdapterResult(success=True, duration_ms=5.0, validation_passed=False)
        out = validation.validate(_cmd(strategy="URL_MATCH"), r)
        assert "URL_MATCH" in out.reason

    def test_to_dict(self):
        out = validation.validate(_cmd(), AdapterResult(success=True, duration_ms=5.0))
        d = out.to_dict()
        for k in ["passed", "checks", "reason"]:
            assert k in d
