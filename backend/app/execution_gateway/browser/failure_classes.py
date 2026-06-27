"""
Phase D — Failure Classification Engine.

Expands raw browser exceptions into deterministic, recovery-aware FailureCategories.
Layered ON TOP of the Phase C errors.classify() (which is unchanged) — this module
adds richer categories (hidden element, page crash, network-idle timeout, popup, auth
expired, ...) and attaches, per category, a severity + retryable flag + recommended
recovery actions.

NO AI. NO LLM. Pure deterministic mapping.

This engine is consumed only when recovery is enabled on the adapter; the default
(recovery-off) path keeps the Phase C errors.classify() semantics intact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.execution_gateway.browser.errors import BrowserErrorType, ErrorClassification, classify


# ── Recovery actions (deterministic) ──────────────────────────────────────────

class RecoveryAction(str, Enum):
    wait              = "WAIT"
    scroll_into_view  = "SCROLL_INTO_VIEW"
    refresh_locator   = "REFRESH_LOCATOR"
    requery           = "REQUERY"
    wait_network_idle = "WAIT_NETWORK_IDLE"
    reload_page       = "RELOAD_PAGE"
    reread_page       = "REREAD_PAGE"
    dismiss_popup     = "DISMISS_POPUP"
    none              = "NONE"


# ── Severity ──────────────────────────────────────────────────────────────────

class FailureSeverity(str, Enum):
    transient   = "TRANSIENT"     # likely self-clears; retry (maybe after a short wait)
    recoverable = "RECOVERABLE"   # needs a deterministic recovery action, then retry
    permanent   = "PERMANENT"     # never retry — fail immediately


# ── Failure categories (Phase D) ──────────────────────────────────────────────

class FailureCategory(str, Enum):
    element_not_found     = "ElementNotFound"
    element_hidden        = "ElementHidden"
    detached_element      = "DetachedElement"
    navigation_timeout    = "NavigationTimeout"
    page_crash            = "PageCrash"
    download_timeout      = "DownloadTimeout"
    download_failure      = "DownloadFailure"
    upload_failure        = "UploadFailure"
    validation_failure    = "ValidationFailure"
    unexpected_popup      = "UnexpectedPopup"
    network_idle_timeout  = "NetworkIdleTimeout"
    authentication_expired = "AuthenticationExpired"
    transient_timeout     = "TransientTimeout"
    stale_element         = "StaleElement"
    temporary_rendering   = "TemporaryRendering"
    invalid_selector      = "InvalidSelector"
    navigation_failed     = "NavigationFailed"
    unknown               = "Unknown"


@dataclass(frozen=True)
class FailureProfile:
    category:            FailureCategory
    severity:            FailureSeverity
    retryable:           bool
    recommended_recovery: tuple[RecoveryAction, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "category":             self.category.value,
            "severity":             self.severity.value,
            "retryable":            self.retryable,
            "recommended_recovery": [r.value for r in self.recommended_recovery],
        }


# Per-category profile table. The single source of truth for severity/retry/recovery.
PROFILES: dict[FailureCategory, FailureProfile] = {
    FailureCategory.element_not_found:    FailureProfile(FailureCategory.element_not_found,   FailureSeverity.recoverable, True,  (RecoveryAction.wait, RecoveryAction.refresh_locator)),
    FailureCategory.element_hidden:       FailureProfile(FailureCategory.element_hidden,      FailureSeverity.recoverable, True,  (RecoveryAction.scroll_into_view,)),
    FailureCategory.detached_element:     FailureProfile(FailureCategory.detached_element,    FailureSeverity.recoverable, True,  (RecoveryAction.requery,)),
    FailureCategory.navigation_timeout:   FailureProfile(FailureCategory.navigation_timeout,  FailureSeverity.recoverable, True,  (RecoveryAction.wait_network_idle,)),
    FailureCategory.page_crash:           FailureProfile(FailureCategory.page_crash,          FailureSeverity.recoverable, True,  (RecoveryAction.reload_page,)),
    FailureCategory.download_timeout:     FailureProfile(FailureCategory.download_timeout,    FailureSeverity.recoverable, True,  (RecoveryAction.wait,)),
    FailureCategory.validation_failure:   FailureProfile(FailureCategory.validation_failure,  FailureSeverity.recoverable, True,  (RecoveryAction.reread_page,)),
    FailureCategory.unexpected_popup:     FailureProfile(FailureCategory.unexpected_popup,    FailureSeverity.recoverable, True,  (RecoveryAction.dismiss_popup,)),
    FailureCategory.network_idle_timeout: FailureProfile(FailureCategory.network_idle_timeout, FailureSeverity.recoverable, True, (RecoveryAction.wait,)),
    FailureCategory.transient_timeout:    FailureProfile(FailureCategory.transient_timeout,   FailureSeverity.transient,   True,  (RecoveryAction.wait,)),
    FailureCategory.stale_element:        FailureProfile(FailureCategory.stale_element,       FailureSeverity.recoverable, True,  (RecoveryAction.requery,)),
    FailureCategory.temporary_rendering:  FailureProfile(FailureCategory.temporary_rendering, FailureSeverity.transient,   True,  (RecoveryAction.wait,)),
    # Permanent — fail immediately.
    FailureCategory.download_failure:     FailureProfile(FailureCategory.download_failure,    FailureSeverity.permanent, False, (RecoveryAction.none,)),
    FailureCategory.upload_failure:       FailureProfile(FailureCategory.upload_failure,      FailureSeverity.permanent, False, (RecoveryAction.none,)),
    FailureCategory.authentication_expired: FailureProfile(FailureCategory.authentication_expired, FailureSeverity.permanent, False, (RecoveryAction.none,)),
    FailureCategory.invalid_selector:     FailureProfile(FailureCategory.invalid_selector,    FailureSeverity.permanent, False, (RecoveryAction.none,)),
    FailureCategory.navigation_failed:    FailureProfile(FailureCategory.navigation_failed,   FailureSeverity.permanent, False, (RecoveryAction.none,)),
    FailureCategory.unknown:              FailureProfile(FailureCategory.unknown,             FailureSeverity.permanent, False, (RecoveryAction.none,)),
}

RETRYABLE_CATEGORIES: frozenset[FailureCategory] = frozenset(
    c for c, p in PROFILES.items() if p.retryable
)
PERMANENT_CATEGORIES: frozenset[FailureCategory] = frozenset(
    c for c, p in PROFILES.items() if not p.retryable
)


def profile_for(category: FailureCategory) -> FailureProfile:
    return PROFILES[category]


# Base BrowserErrorType -> default FailureCategory (before message refinement).
_BASE_MAP: dict[BrowserErrorType, FailureCategory] = {
    BrowserErrorType.timeout:             FailureCategory.transient_timeout,
    BrowserErrorType.detached_node:       FailureCategory.detached_element,
    BrowserErrorType.stale_handle:        FailureCategory.stale_element,
    BrowserErrorType.temporary_rendering: FailureCategory.temporary_rendering,
    BrowserErrorType.selector_not_found:  FailureCategory.element_not_found,
    BrowserErrorType.invalid_selector:    FailureCategory.invalid_selector,
    BrowserErrorType.navigation_failed:   FailureCategory.navigation_failed,
    BrowserErrorType.download_failed:     FailureCategory.download_failure,
    BrowserErrorType.upload_failed:       FailureCategory.upload_failure,
    BrowserErrorType.validation_failed:   FailureCategory.validation_failure,
    BrowserErrorType.authorization_error: FailureCategory.authentication_expired,
    BrowserErrorType.unexpected:          FailureCategory.unknown,
}


@dataclass
class FailureAnalysis:
    category: FailureCategory
    profile:  FailureProfile
    base:     ErrorClassification

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "profile":  self.profile.to_dict(),
            "base":     self.base.to_dict(),
        }


def _refine(category: FailureCategory, msg_low: str, phase: str) -> FailureCategory:
    """Refine a base category using message + phase hints (deterministic)."""
    # Hidden / obscured element (Playwright actionability messages)
    if category == FailureCategory.element_not_found:
        if any(n in msg_low for n in ("not visible", "is hidden", "hidden", "intercepts pointer",
                                      "element is outside of the viewport", "not stable")):
            return FailureCategory.element_hidden
    # Timeout flavour
    if category == FailureCategory.transient_timeout:
        if "networkidle" in msg_low or "network idle" in msg_low or "load state" in msg_low:
            return FailureCategory.network_idle_timeout
        if phase == "navigate" or "navigat" in msg_low or "goto" in msg_low:
            return FailureCategory.navigation_timeout
        if phase == "download" or "download" in msg_low:
            return FailureCategory.download_timeout
    # Page crash (target/page closed/crashed)
    if any(n in msg_low for n in ("crash", "target closed", "page closed", "browser has been closed",
                                  "page has been closed")):
        return FailureCategory.page_crash
    # Unexpected popup / dialog
    if any(n in msg_low for n in ("unexpected popup", "popup", "dialog", "beforeunload", "alert(")):
        return FailureCategory.unexpected_popup
    # Download flavour
    if category == FailureCategory.download_failure and "timeout" in msg_low:
        return FailureCategory.download_timeout
    return category


def classify_failure(exc: BaseException, base: ErrorClassification | None = None,
                     phase: str = "") -> FailureAnalysis:
    """Map an exception (optionally a pre-computed base classification) to a FailureAnalysis."""
    base = base or classify(exc, during=phase)
    msg_low = (base.message or "").lower()
    category = _BASE_MAP.get(base.error_type, FailureCategory.unknown)
    category = _refine(category, msg_low, phase)
    return FailureAnalysis(category=category, profile=PROFILES[category], base=base)


def classify_category(exc: BaseException, phase: str = "") -> FailureCategory:
    return classify_failure(exc, phase=phase).category
