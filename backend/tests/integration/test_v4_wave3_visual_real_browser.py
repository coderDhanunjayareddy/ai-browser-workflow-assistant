from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright

from app.execution_gateway.browser import wave3_visual


def test_canvas_svg_and_visual_region_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <canvas id="canvas" width="120" height="80" style="width:120px;height:80px"></canvas>
                  <svg id="svg" width="120" height="80"><circle id="dot" cx="40" cy="30" r="20"></circle></svg>
                  <script>
                    window.canvasClicks = 0; window.svgClicks = 0;
                    document.querySelector('#canvas').addEventListener('click', () => window.canvasClicks++);
                    document.querySelector('#dot').addEventListener('click', () => window.svgClicks++);
                  </script>
                </body></html>"""
            )
            canvas = wave3_visual.execute_canvas(page, page.locator("#canvas"), {"operation": "click", "x": 20, "y": 20})
            svg = wave3_visual.execute_svg(page, page.locator("#svg"), {"operation": "click", "x": 40, "y": 30})
            region = wave3_visual.execute_visual_region(page, page.locator("#canvas"), {"mode": "element"})
            assert canvas.success is True
            assert svg.success is True
            assert region.success is True
            assert region.details["bytes"] > 0
            assert page.evaluate("window.canvasClicks") == 1
            assert page.evaluate("window.svgClicks") == 1
        finally:
            browser.close()


def test_pdf_file_preview_and_media_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <embed id="pdf" type="application/pdf" src="sample.pdf">
                  <div class="preview" id="preview"><img alt="preview" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==">Report Preview</div>
                  <audio id="audio"></audio>
                  <script>
                    const audio = document.querySelector('#audio');
                    Object.defineProperty(audio, 'duration', { value: 60, configurable: true });
                  </script>
                </body></html>"""
            )
            pdf = wave3_visual.execute_pdf_viewer(page, page.locator("#pdf"), {"operation": "detect"})
            preview = wave3_visual.execute_file_preview(page, page.locator("#preview"), {"expected_text": "Report Preview"})
            media = wave3_visual.execute_media(page, page.locator("#audio"), {"operation": "volume", "volume": 0.25})
            assert pdf.success is True
            assert preview.success is True
            assert media.success is True
            assert media.details["volume"] == 0.25
        finally:
            browser.close()
