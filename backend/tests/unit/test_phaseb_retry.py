"""Phase B Execution Gateway — Unit tests: retry_engine.py."""
import pytest
from app.execution_gateway import retry_engine
from app.execution_gateway.models import RetryConfig


class TestShouldRetry:
    def test_retry_on_dispatch_failure(self):
        cfg = RetryConfig(max_retries=2)
        assert retry_engine.should_retry(1, cfg, dispatch_failed=True, validation_failed=False) is True

    def test_no_retry_after_max_attempts(self):
        cfg = RetryConfig(max_retries=2)   # max_attempts = 3
        assert retry_engine.should_retry(3, cfg, dispatch_failed=True, validation_failed=False) is False

    def test_retry_on_validation_failure_when_enabled(self):
        cfg = RetryConfig(max_retries=2, retry_on_validation_failure=True)
        assert retry_engine.should_retry(1, cfg, dispatch_failed=False, validation_failed=True) is True

    def test_no_retry_on_validation_when_disabled(self):
        cfg = RetryConfig(max_retries=2, retry_on_validation_failure=False)
        assert retry_engine.should_retry(1, cfg, dispatch_failed=False, validation_failed=True) is False

    def test_no_retry_on_success(self):
        cfg = RetryConfig(max_retries=2)
        assert retry_engine.should_retry(1, cfg, dispatch_failed=False, validation_failed=False) is False

    def test_zero_retries_means_one_attempt(self):
        cfg = RetryConfig(max_retries=0)   # max_attempts = 1
        assert retry_engine.should_retry(1, cfg, dispatch_failed=True, validation_failed=False) is False

    def test_bounded_never_infinite(self):
        cfg = RetryConfig(max_retries=5)
        # at attempt == max_attempts, always stop
        assert retry_engine.should_retry(cfg.max_attempts, cfg, dispatch_failed=True, validation_failed=True) is False

    def test_attempts_allowed(self):
        assert retry_engine.attempts_allowed(RetryConfig(max_retries=3)) == 4
