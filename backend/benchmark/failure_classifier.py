"""
M0 — Failure classifier.

Assigns exactly ONE FailureCategory to a failed step/task by walking the decision tree
from docs/benchmark-m0.md Part 6. Deterministic and pure: it reads a FailureSignal
(the evidence available at failure time) and returns a category. No browser, no AI.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from benchmark.m0_models import FailureCategory


# page-text markers that indicate a site defense rather than an agent failure
_CAPTCHA_MARKERS = (
    "captcha", "i'm not a robot", "i am not a robot", "recaptcha", "hcaptcha",
    "security check", "verify you are human", "cf-challenge", "are you a robot",
)
_ANTI_BOT_MARKERS = (
    "access denied", "request blocked", "unusual traffic", "automated requests",
    "datadome", "akamai", "bot detected", "enable javascript and cookies",
)
_LOGIN_WALL_MARKERS = (
    "log in to continue", "log in to see", "sign in to continue", "please log in",
    "join linkedin to", "login to continue",
)
_AUTH_EXPIRED_URL = re.compile(r"(accounts\.google\.com|/login|/signin|/auth)", re.IGNORECASE)


def _is_local_url(url: str) -> bool:
    """A loopback / fixture URL is never a real auth redirect (RC-2)."""
    u = (url or "").lower()
    return "127.0.0.1" in u or "localhost" in u


@dataclass
class FailureSignal:
    """Evidence available at the moment a step or task fails."""
    phase:            str = "execute"     # observe|analyze|gate|execute|validate|loop|setup
    error_type:      str = ""             # exception class name, if any
    error_message:   str = ""
    page_text:       str = ""
    final_url:       str = ""
    http_status:     int | None = None
    locator_all_failed: bool = False      # every locator strategy missed (element not found)
    executed:        bool = False         # the action call was invoked
    dom_changed:     bool = False         # an observable DOM/URL change occurred after the action
    element_in_dom:  bool = False         # the target was in the extracted DOM snapshot
    element_visible_pixels: bool = False  # the target was visible in the screenshot (vision hint)
    recovery_attempted: bool = False
    timed_out:       bool = False         # exceeded max_steps / timeout_ms
    is_cross_site:   bool = False
    needs_visual:    bool = False         # canvas / coordinate-only target
    page_text_lower: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.page_text_lower = (self.page_text or "").lower()


_INFRA_ERRORS = (
    "TimeoutError", "ConnectionError", "ConnectError", "PlaywrightError",
    "TargetClosedError", "BrowserError", "ReadTimeout", "ConnectionResetError",
)


def classify(sig: FailureSignal) -> FailureCategory:
    txt = sig.page_text_lower

    # 1. infrastructure / transport
    if sig.error_type in _INFRA_ERRORS:
        return FailureCategory.infrastructure
    if sig.http_status is not None and sig.http_status >= 500:
        return FailureCategory.infrastructure

    # 2. site defenses (blocked, not failed)
    if any(m in txt for m in _CAPTCHA_MARKERS):
        return FailureCategory.blocked_captcha
    if sig.http_status == 429 or "429" in (sig.error_message or ""):
        return FailureCategory.blocked_rate_limit
    if sig.http_status == 403:
        return FailureCategory.blocked_anti_bot
    if any(m in txt for m in _ANTI_BOT_MARKERS):
        return FailureCategory.blocked_anti_bot
    if any(m in txt for m in _LOGIN_WALL_MARKERS):
        return FailureCategory.blocked_login_wall
    # RC-2: only a real (remote) auth redirect counts as auth-expired. Local fixture URLs
    # legitimately contain "/login" etc. and must NOT be misread as an expired session.
    if _AUTH_EXPIRED_URL.search(sig.final_url or "") and not _is_local_url(sig.final_url):
        return FailureCategory.blocked_auth_expired

    # 3. visual-only target with no DOM equivalent
    if sig.needs_visual:
        return FailureCategory.vision_required

    # 4. grounding: element could not be located at all
    if sig.locator_all_failed:
        # present in pixels but absent from the DOM snapshot => perception, not grounding
        if sig.element_visible_pixels and not sig.element_in_dom:
            return FailureCategory.perception
        return FailureCategory.grounding

    # 5. execution: action ran (or element found) but the page did not respond
    if sig.executed and not sig.dom_changed:
        if sig.element_visible_pixels and not sig.element_in_dom:
            return FailureCategory.perception
        return FailureCategory.execution

    # 6. validation: DOM changed but the expected post-condition was not met
    if sig.executed and sig.dom_changed and sig.phase == "validate":
        return FailureCategory.validation

    # 7. recovery exhausted
    if sig.recovery_attempted:
        return FailureCategory.recovery

    # 8. timeout / budget
    if sig.timed_out:
        return FailureCategory.timeout

    # 9. orchestration (cross-site / multi-tab coordination)
    if sig.is_cross_site:
        return FailureCategory.orchestration

    # 10. planning: the agent chose a logically wrong action (found element, no clear failure above)
    if sig.phase in ("analyze", "gate") or (sig.executed and sig.dom_changed):
        return FailureCategory.planning

    return FailureCategory.unknown
