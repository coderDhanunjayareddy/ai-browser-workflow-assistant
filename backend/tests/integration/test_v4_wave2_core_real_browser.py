from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright

from app.execution_gateway.browser import wave2_core


def test_codemirror_like_editor_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <div id="editor" class="cm-editor">
                    <div class="cm-content" contenteditable="true">old</div>
                  </div>
                </body></html>"""
            )
            result = wave2_core.execute_code_editor(
                page,
                page.locator("#editor"),
                {"text": "const answer = 42;", "mode": "replace"},
                capability_id="browser.editors.codemirror",
            )
            assert result.success is True
            assert result.details["editor_kind"] == "codemirror"
            assert "const answer = 42;" in page.locator(".cm-content").inner_text()
        finally:
            browser.close()


def test_open_shadow_dom_action_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <host-one id="host"></host-one>
                  <script>
                    const root = document.querySelector('#host').attachShadow({ mode: 'open' });
                    root.innerHTML = '<button id="inside">Go</button><span id="status">idle</span>';
                    root.querySelector('#inside').addEventListener('click', () => root.querySelector('#status').textContent = 'clicked');
                  </script>
                </body></html>"""
            )
            result = wave2_core.execute_shadow_dom(page, {"shadow_path": "#host >> #inside", "shadow_action": "click"})
            assert result.success is True
            assert page.evaluate("document.querySelector('#host').shadowRoot.querySelector('#status').textContent") == "clicked"
        finally:
            browser.close()


def test_virtual_list_find_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <div id="list" style="height:80px; overflow:auto">
                    <div style="height:140px">alpha</div>
                    <div style="height:140px">beta target</div>
                  </div>
                </body></html>"""
            )
            result = wave2_core.execute_virtual_list(
                page,
                page.locator("#list"),
                {"target_text": "beta target", "max_steps": 3, "settle_ms": 0},
            )
            assert result.success is True
            assert result.details["found"] is True
        finally:
            browser.close()
