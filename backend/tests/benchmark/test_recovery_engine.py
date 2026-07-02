"""
M2 — Adaptive Execution & Recovery Engine: unit tests (no browser).

Uses lightweight fakes for Playwright's Locator/Page surface so each diagnosis and
strategy branch is tested in isolation and fast. Real-browser confirmation lives in
test_m2_recovery_real_dom.py.
"""
import pytest

from benchmark.recovery_engine import RecoveryEngine, RecoveryHistory, RecoveryDiagnosis


class FakePage:
    def __init__(self, url="http://x/a", viewport=(1366, 900), evaluate_result=None,
                keyboard=None):
        self.url = url
        self.viewport_size = {"width": viewport[0], "height": viewport[1]}
        self._evaluate_result = evaluate_result
        self.keyboard = keyboard or FakeKeyboard()
        self.waits = []

    def evaluate(self, script, arg=None):
        return self._evaluate_result

    def wait_for_timeout(self, ms):
        self.waits.append(ms)


class FakeKeyboard:
    def __init__(self):
        self.pressed = []

    def press(self, key):
        self.pressed.append(key)


class FakeLocator:
    def __init__(self, page, box=None, count=1, evaluate_result=True, fail_retry=False):
        self.page = page
        self._box = box
        self._count = count
        self._evaluate_result = evaluate_result
        self.fail_retry = fail_retry
        self.click_calls = 0
        self.fill_calls = 0
        self.scroll_calls = 0

    def bounding_box(self):
        return self._box

    def count(self):
        return self._count

    def element_handle(self, timeout=1000):
        return object()

    def evaluate(self, script, arg=None):
        return self._evaluate_result

    def scroll_into_view_if_needed(self, timeout=3000):
        self.scroll_calls += 1
        if self._box:
            self._box = {**self._box, "y": 100}  # simulate moving into view

    def click(self, timeout=6000):
        self.click_calls += 1
        if self.fail_retry:
            raise RuntimeError("still failing")

    def fill(self, value, timeout=6000):
        self.fill_calls += 1
        if self.fail_retry:
            raise RuntimeError("still failing")

    def select_option(self, value=None, label=None, timeout=3000):
        if self.fail_retry:
            raise RuntimeError("still failing")

    def hover(self, timeout=6000):
        if self.fail_retry:
            raise RuntimeError("still failing")

    @property
    def first(self):
        return self


VIEWPORT_BOX = {"x": 10, "y": 10, "width": 100, "height": 30}
OFFSCREEN_BOX = {"x": 10, "y": 5000, "width": 100, "height": 30}


def engine():
    return RecoveryEngine()


def history():
    return RecoveryHistory()


# ── diagnosis: navigation occurred ──────────────────────────────────────────

def test_navigation_occurred_diagnosed_first_and_not_retried():
    page = FakePage(url="http://x/b")  # url now differs from before_url
    loc = FakeLocator(page, box=VIEWPORT_BOX)
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                           value=None, description="", before_url="http://x/a", history=history())
    assert out.diagnosis == RecoveryDiagnosis.navigation_occurred.value
    assert out.success is False
    assert loc.click_calls == 0  # never retries after navigation


# ── diagnosis: detached/stale ────────────────────────────────────────────────

def test_detached_element_diagnosed():
    page = FakePage()
    loc = FakeLocator(page, box=VIEWPORT_BOX, count=0)  # locator no longer resolves
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                           value=None, description="", before_url=page.url, history=history())
    assert out.diagnosis == RecoveryDiagnosis.detached_stale.value
    assert out.success is False
    assert out.strategy == "reresolve_required"


# ── diagnosis + strategy: outside viewport ───────────────────────────────────

def test_outside_viewport_scrolls_and_retries_successfully():
    page = FakePage()
    loc = FakeLocator(page, box=OFFSCREEN_BOX)
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                           value=None, description="", before_url=page.url, history=history())
    assert out.diagnosis == RecoveryDiagnosis.outside_viewport.value
    assert out.success is True
    assert out.strategy == "scroll_into_view"
    assert loc.scroll_calls == 1
    assert loc.click_calls == 1  # retried the ORIGINAL action once


def test_outside_viewport_still_offscreen_after_scroll_fails():
    page = FakePage()

    class StuckLocator(FakeLocator):
        def scroll_into_view_if_needed(self, timeout=3000):
            self.scroll_calls += 1  # does NOT move into view

    loc = StuckLocator(page, box=OFFSCREEN_BOX)
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                           value=None, description="", before_url=page.url, history=history())
    assert out.success is False
    assert "still outside" in out.message


# ── diagnosis + strategy: overlay intercept ──────────────────────────────────

def test_overlay_intercept_dismissed_with_escape_and_retries():
    page = FakePage(evaluate_result={"tag": "DIV", "role": "dialog", "cls": "modal-backdrop"})
    loc = FakeLocator(page, box=VIEWPORT_BOX)
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                           value=None, description="", before_url=page.url, history=history())
    assert out.diagnosis == RecoveryDiagnosis.overlay_intercept.value
    # first evaluate() call (interception check) returned a blocker; the SAME fake page
    # keeps returning it, so this exercises the "still blocked" path deterministically.
    assert "Escape" in page.keyboard.pressed


def test_overlay_intercept_clears_after_escape_and_recovers():
    class ClearingPage(FakePage):
        def __init__(self):
            super().__init__()
            self._calls = 0

        def evaluate(self, script, arg=None):
            self._calls += 1
            # first call (diagnosis) sees a blocker; second call (post-Escape check) is clear
            return {"tag": "DIV", "role": "dialog"} if self._calls == 1 else None

    page = ClearingPage()
    loc = FakeLocator(page, box=VIEWPORT_BOX)
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                           value=None, description="", before_url=page.url, history=history())
    assert out.success is True
    assert out.strategy == "dismiss_overlay"
    assert loc.click_calls == 1


# ── diagnosis + strategy: wrong element type (fill on a non-fillable) ────────

def test_wrong_element_type_redirects_fill_to_revealed_input():
    class RevealPage(FakePage):
        def evaluate(self, script, arg=None):
            if "activeElement" in script:
                return True  # a real input is now focused after the click
            return None  # not intercepted

        def locator(self, selector):
            return FakeLocator(self, box=VIEWPORT_BOX)

    page = RevealPage()

    class NonFillableLocator(FakeLocator):
        def evaluate(self, script, arg=None):
            return False  # not INPUT/TEXTAREA/contenteditable

    loc = NonFillableLocator(page, box=VIEWPORT_BOX)
    out = engine().recover(page=page, locator=loc, action_type="fill", selector="#s",
                           value="hello", description="", before_url=page.url, history=history())
    assert out.diagnosis == RecoveryDiagnosis.wrong_element_type.value
    assert out.success is True
    assert out.strategy == "redirect_to_real_input"
    assert loc.click_calls == 1  # clicked the control to reveal the real input


def test_wrong_element_type_no_input_appears():
    class NoRevealPage(FakePage):
        def evaluate(self, script, arg=None):
            # mirror the real two call sites: interception probe returns null/None;
            # the focused-element probe returns false (nothing focused)
            if "elementFromPoint" in script:
                return None
            return False

        def locator(self, selector):
            class Empty(FakeLocator):
                def count(self):
                    return 0
            return Empty(self)

    page = NoRevealPage()

    class NonFillableLocator(FakeLocator):
        def evaluate(self, script, arg=None):
            return False

    loc = NonFillableLocator(page, box=VIEWPORT_BOX)
    out = engine().recover(page=page, locator=loc, action_type="fill", selector="#s",
                           value="hello", description="", before_url=page.url, history=history())
    assert out.success is False
    assert out.diagnosis == RecoveryDiagnosis.wrong_element_type.value


# ── diagnosis + strategy: autocomplete list stabilization ───────────────────

def test_autocomplete_option_waits_for_stability_then_retries():
    class OptionLocator(FakeLocator):
        def evaluate(self, script, arg=None):
            if "getAttribute" in script or "role" in script:
                return True  # looks like an autocomplete option
            return True

    page = FakePage()
    loc = OptionLocator(page, box=VIEWPORT_BOX)  # same box both bounding_box() calls -> stable
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#opt",
                           value=None, description="", before_url=page.url, history=history())
    assert out.diagnosis == RecoveryDiagnosis.autocomplete_list.value
    assert out.success is True
    assert out.strategy == "wait_for_stability"


# ── abort-aware: repeated identical failure is not retried a second time ────

def test_repeated_identical_diagnosis_aborts_without_retrying():
    class StuckOffscreenLocator(FakeLocator):
        """Genuinely stays offscreen — scroll is attempted but never moves the element
        (e.g. it's fixed-position behind something, or the page ignores the scroll)."""
        def scroll_into_view_if_needed(self, timeout=3000):
            self.scroll_calls += 1  # box intentionally NOT mutated

    page = FakePage()
    loc = StuckOffscreenLocator(page, box=OFFSCREEN_BOX)
    h = history()
    first = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                             value=None, description="", before_url=page.url, history=h)
    assert first.diagnosis == RecoveryDiagnosis.outside_viewport.value
    assert first.success is False  # still offscreen after the scroll attempt

    second = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                              value=None, description="", before_url=page.url, history=h)
    assert second.strategy == "abort"
    assert second.success is False
    assert loc.scroll_calls == 1  # NOT attempted a second time


# ── unresolved: bounded single settle-and-retry ──────────────────────────────

def test_unresolved_diagnosis_gets_one_settle_and_retry():
    page = FakePage()
    # evaluate_result=False -> not fillable-check n/a (click), not autocomplete-shaped either
    loc = FakeLocator(page, box=VIEWPORT_BOX, evaluate_result=False)
    out = engine().recover(page=page, locator=loc, action_type="click", selector="#s",
                           value=None, description="", before_url=page.url, history=history())
    assert out.diagnosis == RecoveryDiagnosis.unresolved.value
    assert out.strategy == "settle_and_retry"
    assert out.success is True
    assert loc.click_calls == 1
