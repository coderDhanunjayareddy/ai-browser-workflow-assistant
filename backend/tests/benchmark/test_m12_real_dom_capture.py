"""
M1.2 — real-DOM verification that value/checked/selected capture actually works.

Loads the existing login fixture in a real Chromium (via PlaywrightDriver), fills fields,
checks a box, and asserts the NEXT __m0Extract__() observation reports those values in
`state`. This is the "does it actually work in a browser" test the static drift-guard
(test_injection_fidelity.py) cannot provide — it only proves textual parity between the
two files, not that the DOM APIs behave as expected.

Skips (does not fail) when Playwright is not installed, matching this repo's existing
real-browser test convention (see tests/integration/test_phasec_real_browser.py).
"""
import pytest

pytest.importorskip("playwright")

from app.certification.fixtures import FixtureServer
from benchmark.m0_executor import PlaywrightDriver


@pytest.fixture
def fixture_server():
    srv = FixtureServer().start()
    yield srv
    srv.stop()


@pytest.fixture
def driver():
    d = PlaywrightDriver.launch(headless=True)
    yield d
    d.close()


def test_filled_text_input_value_is_captured(fixture_server, driver):
    driver.navigate(f"{fixture_server.base_url}/login")
    driver._page.fill("#username", "tester")
    ctx = driver.capture()
    el = next(e for e in ctx["interactive_elements"] if e["selector"] == "#username")
    assert el["state"]["value"] == "tester"


def test_password_field_value_never_captured(fixture_server, driver):
    driver.navigate(f"{fixture_server.base_url}/login")
    driver._page.fill("#password", "secret123")
    ctx = driver.capture()
    el = next(e for e in ctx["interactive_elements"] if e["selector"] == "#password")
    assert "value" not in el["state"]
    assert el["state"]["filled"] is True


def test_checkbox_checked_state_is_captured(fixture_server, driver):
    driver.navigate(f"{fixture_server.base_url}/register")
    driver._page.check("#tos")
    ctx = driver.capture()
    el = next(e for e in ctx["interactive_elements"] if e["selector"] == "#tos")
    assert el["state"]["checked"] is True


def test_select_option_captured(fixture_server, driver):
    driver.navigate(f"{fixture_server.base_url}/register")
    driver._page.select_option("#country", "in")
    ctx = driver.capture()
    el = next(e for e in ctx["interactive_elements"] if e["selector"] == "#country")
    assert el["state"]["value"] == "in"
    assert "India" in el["state"]["selected_text"]


def test_second_analyze_would_see_previously_filled_value(fixture_server, driver):
    """End-to-end proof of the M1.2 goal: after filling field A then observing again,
    the observation still shows A's value — the planner would not see an empty field."""
    driver.navigate(f"{fixture_server.base_url}/login")
    driver._page.fill("#username", "tester")
    driver.capture()  # first observation (simulates step N)
    ctx2 = driver.capture()  # second observation (simulates step N+1, unrelated action)
    el = next(e for e in ctx2["interactive_elements"] if e["selector"] == "#username")
    assert el["state"]["value"] == "tester"


# ── Unique selector generation (Amazon result-grid defect) ───────────────────

# Identical deep single-child nesting per card, so the old depth-capped path
# (`div > div > div > div > a`) collided across every card — exactly the Amazon
# failure. A hidden anchor sits first in DOM order inside the same structure, the
# node the old `.first` resolution wrongly bound to.
_GRID_HTML = """
<div id="root">
  <div class="card"><div><div><div><div><div>
    <a href="/hidden" style="display:none">Hidden Decoy</a>
  </div></div></div></div></div></div>
  <div class="card"><div><div><div><div><div>
    <a href="/p1">Product One</a>
  </div></div></div></div></div></div>
  <div class="card"><div><div><div><div><div>
    <a href="/p2">Product Two</a>
  </div></div></div></div></div></div>
  <div class="card"><div><div><div><div><div>
    <a href="/p3">Product Three</a>
  </div></div></div></div></div></div>
</div>
"""


def test_repeated_cards_receive_distinct_unique_selectors(driver):
    driver._page.set_content(_GRID_HTML)
    ctx = driver.capture()
    links = [e for e in ctx["interactive_elements"]
             if e["type"] == "a" and e["text"].strip().startswith("Product")]
    assert len(links) == 3, "the three visible product links should be extracted"

    selectors = [e["selector"] for e in links]
    # 1. distinct: no two result links share a selector (the core defect)
    assert len(set(selectors)) == 3, f"duplicate selectors emitted: {selectors}"

    # 2. each selector resolves to exactly one element — the intended visible link,
    #    never the hidden decoy that the old non-unique path bound to.
    for e in links:
        loc = driver._page.locator(e["selector"])
        assert loc.count() == 1, f"selector {e['selector']!r} is ambiguous ({loc.count()} matches)"
        assert loc.inner_text().strip() == e["text"].strip()


def test_id_bearing_element_still_prefers_short_id_selector(driver):
    # Guard: uniqueness verification must not regress the simple case — a unique id
    # still yields the short `#id`, not a verbose structural path.
    driver._page.set_content('<div><button id="go">Go</button></div>')
    ctx = driver.capture()
    btn = next(e for e in ctx["interactive_elements"] if e["text"].strip() == "Go")
    assert btn["selector"] == "#go"
