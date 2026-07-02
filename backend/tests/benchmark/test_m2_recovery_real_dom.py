"""
M2 — Adaptive Execution & Recovery Engine: real-browser confirmation.

Purpose-built, generic HTML snippets (via page.set_content) reproduce the DOM conditions
observed in the real m1-eval.json evidence — outside-viewport, overlay-intercept, and a
button masquerading as a fillable field — and confirm PlaywrightDriver.execute_playwright()
recovers via the new engine, end to end, against a real Chromium.

Skips (does not fail) when Playwright is not installed, matching this repo's existing
real-browser test convention.
"""
import pytest

pytest.importorskip("playwright")

from benchmark.m0_executor import PlaywrightDriver


@pytest.fixture
def driver():
    d = PlaywrightDriver.launch(headless=True)
    yield d
    d.close()


def _load(driver, html: str) -> None:
    driver.navigate("about:blank")
    driver._page.set_content(html, wait_until="domcontentloaded")


# ── outside viewport: a real click that fails without recovery, succeeds with it ────

_OFFSCREEN_HTML = """
<!doctype html><html><body>
  <div style="height:3000px"></div>
  <button id="target" onclick="document.getElementById('out').textContent='clicked'">Go</button>
  <div id="out"></div>
</body></html>
"""


def test_simple_below_fold_click_succeeds_without_needing_recovery(driver):
    """
    A simple "scroll down the page" case is already handled by Playwright's OWN
    scroll_into_view_if_needed() inside the PRIMARY attempt (unchanged by M2) — so this
    should succeed WITHOUT the recovery engine ever triggering. This is an honest, useful
    finding: it means the real Amazon "element is outside of the viewport" failures (see
    m1-eval.json) are NOT simple below-the-fold cases — #nav-assist-search is a hidden
    keyboard-shortcut menu item that no amount of scrolling reveals, which is closer to a
    grounding problem (wrong target chosen) than an actionability problem. Recovery
    correctly does not manufacture a fake success for a target that is fundamentally wrong
    (see test_permanently_hidden_element_fails_cleanly_without_hanging below).
    """
    _load(driver, _OFFSCREEN_HTML)
    result = driver.execute_playwright({
        "action_type": "click", "target_selector": "#target", "value": None,
        "description": "click Go button",
    })
    assert result.success is True
    assert result.recovery_attempted is False   # never needed — Playwright's own scroll sufficed
    text = driver._page.evaluate("() => document.getElementById('out').textContent")
    assert text == "clicked"


_SLOW_REVEAL_HTML = """
<!doctype html><html><body>
  <div id="spacer" style="height:3000px"></div>
  <button id="target" style="display:none"
    onclick="document.getElementById('out').textContent='clicked'">Go</button>
  <div id="out"></div>
  <script>
    // The PRIMARY attempt's own scroll_into_view_if_needed(timeout=4000) fails first
    // (element is display:none -> "not visible", ~4s) — _attempt() never even reaches
    // .click(). Recovery then gets its OWN scroll_into_view_if_needed(timeout=3000)
    // starting around the 4s mark; reveal at 5s lands inside that 4s-7s window.
    setTimeout(function () {
      document.getElementById('target').style.display = 'block';
      document.getElementById('spacer').scrollIntoView();
    }, 5000);
  </script>
</body></html>
"""


def test_late_appearing_element_recovers_after_primary_attempt_exhausts(driver):
    """A target that only becomes interactable AFTER the primary attempt's own scroll
    budget has been exhausted. Recovery's fresh diagnosis + retry, running strictly after
    that budget is spent, catches the now-visible element."""
    _load(driver, _SLOW_REVEAL_HTML)
    result = driver.execute_playwright({
        "action_type": "click", "target_selector": "#target", "value": None,
        "description": "click Go button",
    })
    assert result.success is True
    assert result.recovery_attempted is True
    assert result.recovery_strategy == "scroll_into_view"
    text = driver._page.evaluate("() => document.getElementById('out').textContent")
    assert text == "clicked"


# ── overlay intercept: a full-viewport backdrop blocking the real target ────────────

_OVERLAY_HTML = """
<!doctype html><html><body>
  <button id="target" style="position:fixed;top:40px;left:40px;"
    onclick="document.getElementById('out').textContent='clicked'">Save</button>
  <div id="backdrop" role="dialog"
    style="position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:9999;"
    onkeydown="if(event.key==='Escape'){this.remove()}"></div>
  <div id="out"></div>
  <script>
    window.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') { var b = document.getElementById('backdrop'); if (b) b.remove(); }
    });
  </script>
</body></html>
"""


def test_overlay_intercept_click_recovers_via_escape(driver):
    _load(driver, _OVERLAY_HTML)
    result = driver.execute_playwright({
        "action_type": "click", "target_selector": "#target", "value": None,
        "description": "click Save button",
    })
    assert result.success is True
    assert result.recovery_attempted is True
    assert result.recovery_diagnosis == "OVERLAY_INTERCEPT"
    assert result.recovery_strategy == "dismiss_overlay"
    text = driver._page.evaluate("() => document.getElementById('out').textContent")
    assert text == "clicked"


# ── wrong element type: a button-with-search-semantics, not a real input ────────────

_FAKE_INPUT_HTML = """
<!doctype html><html><body>
  <button id="target" aria-label="Search or jump to..."
    onclick="document.getElementById('real-input').style.display='block';
             document.getElementById('real-input').focus()">Search or jump to...</button>
  <input id="real-input" type="text" style="display:none">
</body></html>
"""


def test_fill_on_button_recovers_by_redirecting_to_real_input(driver):
    _load(driver, _FAKE_INPUT_HTML)
    result = driver.execute_playwright({
        "action_type": "fill", "target_selector": "#target", "value": "fastapi",
        "description": "search for fastapi",
    })
    assert result.success is True
    assert result.recovery_attempted is True
    assert result.recovery_diagnosis == "WRONG_ELEMENT_TYPE"
    assert result.recovery_strategy == "redirect_to_real_input"
    value = driver._page.evaluate("() => document.getElementById('real-input').value")
    assert value == "fastapi"


# ── abort-aware: a genuinely unrecoverable target does not loop forever ─────────────

def test_permanently_hidden_element_fails_cleanly_without_hanging(driver):
    html = """<!doctype html><html><body>
      <button id="target" style="display:none">Never visible</button>
    </body></html>"""
    _load(driver, html)
    result = driver.execute_playwright({
        "action_type": "click", "target_selector": "#target", "value": None,
        "description": "click hidden button",
    })
    assert result.success is False
    assert result.error_type == "RecoveryExhausted"
    assert result.recovery_attempted is True


# ── failure_classifier routing: recovery-exhausted is EXECUTION, not INFRASTRUCTURE ──

def test_recovery_exhausted_classifies_as_execution_not_infrastructure():
    from benchmark.failure_classifier import classify, FailureSignal
    from benchmark.m0_models import FailureCategory

    sig = FailureSignal(phase="execute", error_type="RecoveryExhausted",
                        error_message="click blocked (OUTSIDE_VIEWPORT): still outside",
                        executed=True, dom_changed=False)
    assert classify(sig) == FailureCategory.execution
    assert classify(sig) != FailureCategory.infrastructure
