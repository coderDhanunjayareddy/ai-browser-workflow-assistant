"""Phase C — Unit tests: errors.py (browser error classification)."""
import pytest
from app.execution_gateway.browser import errors
from app.execution_gateway.browser.errors import (
    BrowserErrorType, RETRYABLE_ERRORS, NEVER_RETRY_ERRORS, classify, classify_type, is_retryable,
)


class TestErrorTypes:
    def test_count(self):
        assert len(BrowserErrorType) == 12

    def test_retryable_set(self):
        assert BrowserErrorType.timeout in RETRYABLE_ERRORS
        assert BrowserErrorType.detached_node in RETRYABLE_ERRORS
        assert BrowserErrorType.stale_handle in RETRYABLE_ERRORS
        assert BrowserErrorType.temporary_rendering in RETRYABLE_ERRORS
        assert len(RETRYABLE_ERRORS) == 4

    def test_never_retry_set(self):
        assert BrowserErrorType.selector_not_found in NEVER_RETRY_ERRORS
        assert BrowserErrorType.invalid_selector in NEVER_RETRY_ERRORS
        assert BrowserErrorType.authorization_error in NEVER_RETRY_ERRORS

    def test_disjoint(self):
        assert RETRYABLE_ERRORS.isdisjoint(NEVER_RETRY_ERRORS)

    def test_is_retryable(self):
        assert is_retryable(BrowserErrorType.timeout) is True
        assert is_retryable(BrowserErrorType.selector_not_found) is False


class TestClassify:
    @pytest.mark.parametrize("msg,expected,retryable", [
        ("Timeout 30000ms exceeded",               BrowserErrorType.timeout,            True),
        ("page.goto: Timeout exceeded",            BrowserErrorType.timeout,            True),
        ("element is detached from the DOM",       BrowserErrorType.detached_node,      True),
        ("stale element handle",                   BrowserErrorType.stale_handle,       True),
        ("layout not stable, rendering not ready", BrowserErrorType.temporary_rendering, True),
        ("waiting for selector .x: no node found", BrowserErrorType.selector_not_found, False),
        ("locator resolved to 0 elements",         BrowserErrorType.selector_not_found, False),
        ("is not a valid selector",                BrowserErrorType.invalid_selector,   False),
        ("net::ERR_NAME_NOT_RESOLVED",             BrowserErrorType.navigation_failed,  False),
        ("download did not complete",              BrowserErrorType.download_failed,    False),
        ("set_input_files: no such file",          BrowserErrorType.upload_failed,      False),
        ("403 Forbidden / unauthorized",           BrowserErrorType.authorization_error, False),
        ("something totally weird happened",       BrowserErrorType.unexpected,         False),
    ])
    def test_classify(self, msg, expected, retryable):
        c = classify(Exception(msg))
        assert c.error_type == expected
        assert c.retryable == retryable

    def test_timeout_by_type_name(self):
        class TimeoutError(Exception): ...
        c = classify(TimeoutError("anything"))
        assert c.error_type == BrowserErrorType.timeout
        assert c.retryable is True

    def test_to_dict(self):
        c = classify(Exception("Timeout exceeded"))
        d = c.to_dict()
        for k in ["error_type", "retryable", "message", "original_type"]:
            assert k in d

    def test_classify_type(self):
        c = classify_type(BrowserErrorType.selector_not_found, "missing")
        assert c.error_type == BrowserErrorType.selector_not_found
        assert c.retryable is False
        assert c.original_type == "explicit"

    def test_original_type_recorded(self):
        c = classify(ValueError("Timeout exceeded"))
        assert c.original_type == "ValueError"
