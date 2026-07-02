"""
M2 — Adaptive Execution & Recovery Engine.

Generic, DOM-state-driven recovery for element-targeted actions (click/fill/select_option/
hover/choose_date) that fail AFTER the locator resolved. Every decision is made by
INSPECTING the current page — bounding box vs. viewport, elementFromPoint interception,
element attachment, tag/role fitness for the requested action, URL delta — never by
repeating the exact same call and never by asking the LLM.

Bounded: one diagnosis -> one matching strategy -> one retry of the original action.
Abort-aware: a per-driver-instance history skips retrying an action that already failed
with the same diagnosis (see RecoveryHistory).

No website-specific logic anywhere in this file — every check is a generic DOM/Playwright
property, applicable to any page by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RecoveryDiagnosis(str, Enum):
    navigation_occurred = "NAVIGATION_OCCURRED"
    detached_stale      = "DETACHED_STALE"
    outside_viewport    = "OUTSIDE_VIEWPORT"
    overlay_intercept   = "OVERLAY_INTERCEPT"
    wrong_element_type  = "WRONG_ELEMENT_TYPE"
    autocomplete_list   = "AUTOCOMPLETE_LIST"
    unresolved          = "UNRESOLVED"


@dataclass
class RecoveryOutcome:
    success:   bool
    diagnosis: Optional[str] = None
    strategy:  str = ""
    message:   str = ""
    # set when the recovery strategy resolved a DIFFERENT locator than the one passed in
    # (e.g. wrong_element_type redirects a fill() to the real input that appeared)
    new_locator: Optional[object] = None


class RecoveryHistory:
    """Per-task memory of (action_type, selector, diagnosis) outcomes, so an action that
    already failed with the same diagnosis is not retried a second time (abort-aware).
    Cleared on navigation — a new page is a new situation."""

    def __init__(self) -> None:
        self._seen: dict[tuple, str] = {}

    def already_failed(self, action_type: str, selector: str, diagnosis: str) -> bool:
        return self._seen.get((action_type, selector)) == diagnosis

    def record(self, action_type: str, selector: str, diagnosis: str) -> None:
        self._seen[(action_type, selector)] = diagnosis

    def reset(self) -> None:
        self._seen.clear()


class RecoveryEngine:
    """Stateless pipeline; call recover() once per failed action attempt."""

    def recover(self, *, page, locator, action_type: str, selector: str, value,
               description: str, before_url: str, history: RecoveryHistory) -> RecoveryOutcome:
        diagnosis, context = self._diagnose(
            page=page, locator=locator, action_type=action_type, before_url=before_url)

        if diagnosis is None:
            return RecoveryOutcome(False, None, "none", "no matching diagnosis")

        if history.already_failed(action_type, selector, diagnosis.value):
            return RecoveryOutcome(False, diagnosis.value, "abort",
                                   "identical (action, selector, diagnosis) already failed once — aborting")

        outcome = self._apply(diagnosis, page=page, locator=locator, action_type=action_type,
                              value=value, context=context)
        if not outcome.success:
            history.record(action_type, selector, diagnosis.value)
        return outcome

    # ── diagnosis (priority order: most certain / cheapest first) ───────────--

    def _diagnose(self, *, page, locator, action_type: str, before_url: str):
        if page.url != before_url:
            return RecoveryDiagnosis.navigation_occurred, None

        if self._is_detached(locator):
            return RecoveryDiagnosis.detached_stale, None

        if self._is_outside_viewport(locator):
            return RecoveryDiagnosis.outside_viewport, None

        intercept = self._intercepting_element(locator)
        if intercept is not None:
            return RecoveryDiagnosis.overlay_intercept, intercept

        if action_type == "fill" and not self._is_fillable(locator):
            return RecoveryDiagnosis.wrong_element_type, None

        if self._looks_like_autocomplete_option(locator):
            return RecoveryDiagnosis.autocomplete_list, None

        return RecoveryDiagnosis.unresolved, None

    def _is_detached(self, locator) -> bool:
        try:
            return locator.count() == 0
        except Exception:
            return True

    def _is_outside_viewport(self, locator) -> bool:
        try:
            box = locator.bounding_box()
            if box is None:
                return True
            vp = locator.page.viewport_size
            if not vp:
                return False
            return (box["y"] + box["height"] <= 0 or box["y"] >= vp["height"] or
                    box["x"] + box["width"] <= 0 or box["x"] >= vp["width"])
        except Exception:
            return False

    def _intercepting_element(self, locator) -> Optional[dict]:
        try:
            box = locator.bounding_box()
            if not box:
                return None
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            handle = locator.element_handle(timeout=1000)
            if handle is None:
                return None
            info = locator.page.evaluate(
                """([target, x, y]) => {
                    const top = document.elementFromPoint(x, y);
                    if (!top) return null;
                    if (top === target || target.contains(top) || top.contains(target)) return null;
                    return { tag: top.tagName, role: top.getAttribute('role') || '',
                             cls: (top.className || '').toString().slice(0, 120) };
                }""",
                [handle, cx, cy],
            )
            return info
        except Exception:
            return None

    def _is_fillable(self, locator) -> bool:
        try:
            return bool(locator.evaluate(
                "el => ['INPUT','TEXTAREA'].includes(el.tagName) || el.isContentEditable === true"))
        except Exception:
            return True  # unknown -> don't block a legitimate fill

    def _looks_like_autocomplete_option(self, locator) -> bool:
        try:
            return bool(locator.evaluate(
                """el => {
                    const role = (el.getAttribute('role') || '').toLowerCase();
                    if (role === 'option') return true;
                    const parent = el.closest('[role="listbox"], ul, ol');
                    return !!parent;
                }"""))
        except Exception:
            return False

    # ── strategies (one per diagnosis) ──────────────────────────────────────--

    def _apply(self, diagnosis: RecoveryDiagnosis, *, page, locator, action_type: str,
              value, context) -> RecoveryOutcome:
        if diagnosis == RecoveryDiagnosis.navigation_occurred:
            return RecoveryOutcome(False, diagnosis.value, "recognize_navigation",
                                   "URL changed during the action — treat as a new page state, "
                                   "not a retryable failure; caller should re-observe")

        if diagnosis == RecoveryDiagnosis.detached_stale:
            return RecoveryOutcome(False, diagnosis.value, "reresolve_required",
                                   "element detached/stale — caller must re-resolve against a "
                                   "fresh capture before retrying")

        if diagnosis == RecoveryDiagnosis.outside_viewport:
            try:
                locator.scroll_into_view_if_needed(timeout=3000)
                page.wait_for_timeout(150)
                if not self._is_outside_viewport(locator):
                    return self._retry_action(locator, action_type, value, diagnosis, "scroll_into_view")
                return RecoveryOutcome(False, diagnosis.value, "scroll_into_view",
                                       "scrolled but element is still outside the viewport")
            except Exception as e:
                return RecoveryOutcome(False, diagnosis.value, "scroll_into_view", str(e))

        if diagnosis == RecoveryDiagnosis.overlay_intercept:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                still_blocked = self._intercepting_element(locator)
                if still_blocked is None:
                    return self._retry_action(locator, action_type, value, diagnosis, "dismiss_overlay")
                return RecoveryOutcome(False, diagnosis.value, "dismiss_overlay",
                                       f"still intercepted by {context or still_blocked} after Escape")
            except Exception as e:
                return RecoveryOutcome(False, diagnosis.value, "dismiss_overlay", str(e))

        if diagnosis == RecoveryDiagnosis.wrong_element_type:
            try:
                locator.click(timeout=3000)
                page.wait_for_timeout(300)
                real_input = self._find_newly_focused_input(page)
                if real_input is not None:
                    real_input.fill(value or "", timeout=4000)
                    return RecoveryOutcome(True, diagnosis.value, "redirect_to_real_input",
                                           "clicked the control and filled the input it revealed",
                                           new_locator=real_input)
                return RecoveryOutcome(False, diagnosis.value, "redirect_to_real_input",
                                       "clicked the control but no fillable input appeared")
            except Exception as e:
                return RecoveryOutcome(False, diagnosis.value, "redirect_to_real_input", str(e))

        if diagnosis == RecoveryDiagnosis.autocomplete_list:
            try:
                box1 = locator.bounding_box()
                page.wait_for_timeout(250)
                box2 = locator.bounding_box()
                if box1 and box2 and box1 == box2:
                    return self._retry_action(locator, action_type, value, diagnosis, "wait_for_stability")
                return RecoveryOutcome(False, diagnosis.value, "wait_for_stability",
                                       "autocomplete list position still changing after wait")
            except Exception as e:
                return RecoveryOutcome(False, diagnosis.value, "wait_for_stability", str(e))

        # unresolved: one bounded extra try after a short settle wait — no diagnosis matched,
        # but transient timing issues (animation, late paint) are common and cheap to retry once
        try:
            page.wait_for_timeout(300)
            return self._retry_action(locator, action_type, value, diagnosis, "settle_and_retry")
        except Exception as e:
            return RecoveryOutcome(False, diagnosis.value, "settle_and_retry", str(e))

    def _retry_action(self, locator, action_type: str, value, diagnosis, strategy: str) -> RecoveryOutcome:
        try:
            if action_type == "click" or action_type == "choose_date":
                locator.click(timeout=4000)
            elif action_type == "fill":
                locator.fill(value or "", timeout=4000)
            elif action_type == "select_option":
                try:
                    locator.select_option(value=value, timeout=3000)
                except Exception:
                    locator.select_option(label=value, timeout=3000)
            elif action_type == "hover":
                locator.hover(timeout=4000)
            else:
                return RecoveryOutcome(False, diagnosis.value, strategy,
                                       f"unsupported action_type for retry: {action_type}")
            return RecoveryOutcome(True, diagnosis.value, strategy, "recovered")
        except Exception as e:
            return RecoveryOutcome(False, diagnosis.value, strategy, f"retry failed: {e}")

    def _find_newly_focused_input(self, page):
        try:
            has_focus = page.evaluate(
                """() => {
                    const el = document.activeElement;
                    if (!el) return false;
                    return ['INPUT','TEXTAREA'].includes(el.tagName) || el.isContentEditable === true;
                }""")
            if has_focus:
                return page.locator(":focus").first
            visible = page.locator(
                'input:not([type="hidden"]):visible, textarea:visible, [contenteditable="true"]:visible'
            ).first
            if visible.count() > 0:
                return visible
        except Exception:
            pass
        return None
