"""Deterministic Phase 2 trusted-input benchmark.

Measures the DOM-synthetic fast path and a bounded CDP fallback on four surfaces
that commonly reject or escape synthetic main-frame events. No network or model
call is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


@dataclass
class SurfaceResult:
    surface: str
    synthetic_effect: bool
    cdp_attempted: bool
    hybrid_effect: bool
    grounding: str
    screenshot_hash: str | None = None


HTML = r"""<!doctype html>
<html><body>
  <label>Controlled <input id="controlled" /></label><output id="input-result">idle</output>
  <iframe id="test-frame" srcdoc="<button id='frame-button'>Frame action</button><output id='frame-result'>idle</output><script>document.querySelector('#frame-button').addEventListener('click',e=>{if(e.isTrusted)document.querySelector('#frame-result').textContent='done'})</script>"></iframe>
  <button id="popup-button">Open popup</button><output id="popup-result">idle</output>
  <canvas id="widget" width="220" height="90" tabindex="0"></canvas><output id="widget-result">idle</output>
  <script>
    document.querySelector('#controlled').addEventListener('input', e => {
      document.querySelector('#input-result').textContent = e.isTrusted ? 'done' : 'ignored'
    })
    document.querySelector('#popup-button').addEventListener('click', e => {
      if (e.isTrusted) {
        window.open('about:blank', '_blank')
        document.querySelector('#popup-result').textContent = 'done'
      }
    })
    document.querySelector('#widget').addEventListener('pointerdown', e => {
      document.querySelector('#widget-result').textContent = e.isTrusted ? 'done' : 'ignored'
    })
  </script>
</body></html>"""


def center(page: Page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).bounding_box()
    assert box
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def click_cdp(session, x: float, y: float) -> None:
    session.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    session.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    session.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})


def run(headless: bool = True) -> dict:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1000, "height": 800})
        page = context.new_page()
        page.set_content(HTML)
        page.wait_for_load_state("load")
        session = context.new_cdp_session(page)
        results: list[SurfaceResult] = []

        page.evaluate("""() => {
          const el = document.querySelector('#controlled'); el.value = 'phase2';
          el.dispatchEvent(new InputEvent('input', {bubbles:true, data:'phase2', inputType:'insertText'}));
        }""")
        synthetic = page.locator("#input-result").inner_text() == "done"
        if not synthetic:
            x, y = center(page, "#controlled")
            click_cdp(session, x, y)
            session.send("Input.insertText", {"text": "trusted"})
        results.append(SurfaceResult("controlled_input", synthetic, not synthetic, page.locator("#input-result").inner_text() == "done", "dom"))

        page.evaluate("""() => document.querySelector('#test-frame').contentDocument.querySelector('#frame-button').click()""")
        frame = page.frame_locator("#test-frame")
        synthetic = frame.locator("#frame-result").inner_text() == "done"
        if not synthetic:
            button_box = frame.locator("#frame-button").bounding_box()
            assert button_box
            click_cdp(session, button_box["x"] + button_box["width"] / 2,
                      button_box["y"] + button_box["height"] / 2)
        results.append(SurfaceResult("iframe", synthetic, not synthetic, frame.locator("#frame-result").inner_text() == "done", "dom_recursive_frame"))

        existing_pages = len(context.pages)
        page.evaluate("() => document.querySelector('#popup-button').click()")
        synthetic = len(context.pages) > existing_pages
        if not synthetic:
            x, y = center(page, "#popup-button")
            click_cdp(session, x, y)
            page.wait_for_timeout(150)
        popup_effect = page.locator("#popup-result").inner_text() == "done" and len(context.pages) > existing_pages
        results.append(SurfaceResult("popup", synthetic, not synthetic, popup_effect, "accessibility"))

        page.evaluate("""() => document.querySelector('#widget').dispatchEvent(new PointerEvent('pointerdown', {bubbles:true}))""")
        synthetic = page.locator("#widget-result").inner_text() == "done"
        screenshot_hash = None
        if not synthetic:
            screenshot_hash = hashlib.sha256(page.screenshot()).hexdigest()
            x, y = center(page, "#widget")
            click_cdp(session, x, y)
        results.append(SurfaceResult("complex_widget", synthetic, not synthetic, page.locator("#widget-result").inner_text() == "done", "vision_region", screenshot_hash))

        browser.close()

    synthetic_no_effect = sum(not item.synthetic_effect for item in results)
    hybrid_no_effect = sum(not item.hybrid_effect for item in results)
    return {
        "schema_version": "phase2.control_benchmark.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "surface_count": len(results),
        "synthetic_no_effect_count": synthetic_no_effect,
        "hybrid_no_effect_count": hybrid_no_effect,
        "synthetic_no_effect_rate": synthetic_no_effect / len(results),
        "hybrid_no_effect_rate": hybrid_no_effect / len(results),
        "relative_no_effect_reduction": (synthetic_no_effect - hybrid_no_effect) / max(1, synthetic_no_effect),
        "results": [asdict(item) for item in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    report = run(headless=not args.headed)
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["hybrid_no_effect_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
