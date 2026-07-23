from __future__ import annotations

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright

from app.execution_gateway.browser import wave4_enterprise


def test_site_adapter_and_optimization_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <div role="textbox" contenteditable="true">Draft</div>
                  <input aria-label="Search Drive">
                  <button aria-label="Compose"></button>
                  <table><tr><td>Cell</td></tr></table>
                  <div data-virtualized="true" aria-rowcount="100"></div>
                </body></html>"""
            )
            adapter = wave4_enterprise.execute_site_adapter(page, {"adapter": "google_workspace"})
            optimized = wave4_enterprise.execute_site_optimization(page, {"adapter": "google_workspace"})
            assert adapter.success is True
            assert adapter.capability_id == "browser.adapters.google_workspace"
            assert adapter.details["discovered_elements"] >= 3
            assert optimized.success is True
            assert "use_rich_text_adapter" in optimized.details["recommendations"]
            assert "use_large_table_navigation" in optimized.details["recommendations"]
        finally:
            browser.close()


def test_auth_handoff_and_enterprise_file_workflow_real_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.set_content(
                """<!doctype html>
                <html><body>
                  <h1>Single sign-on</h1>
                  <p>Enter verification code from your authenticator app.</p>
                  <input autocomplete="one-time-code" aria-label="OTP">
                  <input type="password">
                  <input type="file">
                  <button aria-label="Upload file">Upload</button>
                  <a download href="/file">Download</a>
                </body></html>"""
            )
            sso = wave4_enterprise.execute_sso_auth(page, {"provider": "enterprise"})
            mfa = wave4_enterprise.execute_mfa_handoff(page, {})
            files = wave4_enterprise.execute_enterprise_file_workflow(page, {"workflow": "upload"})
            assert sso.success is True
            assert mfa.success is True
            assert mfa.details["handoff_required"] is True
            assert files.success is True
            assert files.details["candidate_count"] >= 3
        finally:
            browser.close()
