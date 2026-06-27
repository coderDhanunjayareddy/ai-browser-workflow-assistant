"""
Phase C — Browser Error Classification.

Classifies a browser/Playwright exception into a stable BrowserErrorType and decides
whether it is a TRANSIENT failure (safe to retry) or a TERMINAL failure (never retry).

This maps cleanly into the EXISTING Phase B Retry Engine:
  retryable error  -> dispatch_failed=True  -> retry_engine retries (bounded)
  non-retryable    -> dispatch_failed=False -> no retry

Retry (transient):     navigation timeout, detached node, stale handle, temporary rendering
Never retry (terminal): missing element, invalid selector, authorization failure,
                        validation failure, navigation failed, download/upload failed

No Playwright types are imported here — classification is by exception class name +
message substring, so this module loads without Playwright installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BrowserErrorType(str, Enum):
    timeout              = "TIMEOUT"                 # navigation/action timeout (transient)
    detached_node        = "DETACHED_NODE"           # element detached mid-action (transient)
    stale_handle         = "STALE_HANDLE"            # stale element handle (transient)
    temporary_rendering  = "TEMPORARY_RENDERING"     # transient render/layout (transient)
    selector_not_found   = "SELECTOR_NOT_FOUND"      # missing element (terminal)
    invalid_selector     = "INVALID_SELECTOR"        # malformed selector (terminal)
    navigation_failed    = "NAVIGATION_FAILED"       # net error / nav refused (terminal)
    download_failed      = "DOWNLOAD_FAILED"         # download did not complete (terminal)
    upload_failed        = "UPLOAD_FAILED"           # file set failed (terminal)
    validation_failed    = "VALIDATION_FAILED"       # expected outcome not met (terminal)
    authorization_error  = "AUTHORIZATION_ERROR"     # auth/permission (terminal)
    unexpected           = "UNEXPECTED_BROWSER_ERROR"  # anything else (terminal)


# Transient error types — the ONLY ones that may be retried.
RETRYABLE_ERRORS: frozenset[BrowserErrorType] = frozenset({
    BrowserErrorType.timeout,
    BrowserErrorType.detached_node,
    BrowserErrorType.stale_handle,
    BrowserErrorType.temporary_rendering,
})

# Errors that must NEVER be retried (explicit, per spec).
NEVER_RETRY_ERRORS: frozenset[BrowserErrorType] = frozenset({
    BrowserErrorType.selector_not_found,
    BrowserErrorType.invalid_selector,
    BrowserErrorType.authorization_error,
    BrowserErrorType.validation_failed,
    BrowserErrorType.navigation_failed,
    BrowserErrorType.download_failed,
    BrowserErrorType.upload_failed,
    BrowserErrorType.unexpected,
})


@dataclass
class ErrorClassification:
    error_type:    BrowserErrorType
    retryable:     bool
    message:       str
    original_type: str

    def to_dict(self) -> dict:
        return {
            "error_type":    self.error_type.value,
            "retryable":     self.retryable,
            "message":       self.message,
            "original_type": self.original_type,
        }


def is_retryable(error_type: BrowserErrorType) -> bool:
    return error_type in RETRYABLE_ERRORS


# Ordered (message-substring, error_type) rules. First match wins.
_MESSAGE_RULES: list[tuple[tuple[str, ...], BrowserErrorType]] = [
    (("invalid selector", "is not a valid selector", "unsupported selector",
      "malformed", "syntaxerror"),                          BrowserErrorType.invalid_selector),
    (("element is detached", "detached from", "node is detached"), BrowserErrorType.detached_node),
    (("stale element", "stale handle", "element handle is stale"), BrowserErrorType.stale_handle),
    (("temporarily", "temporary render", "rendering not ready", "layout not stable"),
                                                            BrowserErrorType.temporary_rendering),
    (("waiting for selector", "no node found", "not found", "no element", "could not find",
      "locator resolved to 0", "element is not attached", "0 elements"),
                                                            BrowserErrorType.selector_not_found),
    (("net::", "err_name_not_resolved", "err_connection", "navigation failed",
      "frame was detached during navigation", "err_aborted"),
                                                            BrowserErrorType.navigation_failed),
    (("download failed", "download did not", "download error"), BrowserErrorType.download_failed),
    (("upload failed", "set_input_files", "file chooser", "no such file"), BrowserErrorType.upload_failed),
    (("forbidden", "unauthorized", "permission denied", "authoriz"), BrowserErrorType.authorization_error),
    (("validation failed", "expected", "assertion"),       BrowserErrorType.validation_failed),
]


def classify(exc: BaseException, *, during: str = "") -> ErrorClassification:
    """
    Classify an exception into an ErrorClassification.

    `during` is an optional phase hint ("navigate", "click", ...) so a TimeoutError can
    be attributed to navigation vs. another action — but the type alone drives retry.
    """
    name = type(exc).__name__
    msg  = str(exc) or ""
    low  = msg.lower()

    # TimeoutError (Playwright raises *TimeoutError) is always a transient timeout.
    if "timeout" in name.lower() or "timeout" in low or "timed out" in low:
        et = BrowserErrorType.timeout
        return ErrorClassification(et, is_retryable(et), msg, name)

    for needles, et in _MESSAGE_RULES:
        if any(n in low for n in needles):
            return ErrorClassification(et, is_retryable(et), msg, name)

    et = BrowserErrorType.unexpected
    return ErrorClassification(et, is_retryable(et), msg, name)


def classify_type(error_type: BrowserErrorType, message: str = "") -> ErrorClassification:
    """Build a classification directly from a known error type (used by action code)."""
    return ErrorClassification(error_type, is_retryable(error_type), message, "explicit")
