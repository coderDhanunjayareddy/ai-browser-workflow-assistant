from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright

from app.execution_gateway.browser import rich_text


def test_rich_text_contenteditable_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <div id="editor" contenteditable="true"><p>Existing</p></div>
                </body></html>"""
            )
            locator = page.locator("#editor")
            result = rich_text.execute(
                page,
                locator,
                rich_text.parse_payload('{"text":"Hello rich editor","mode":"replace","shortcuts":["ctrl+b"]}'),
            )
            assert result.success is True
            assert result.validated is True
            assert result.editor_kind == "contenteditable"
            assert "Hello rich editor" in page.locator("#editor").inner_text()
        finally:
            browser.close()
