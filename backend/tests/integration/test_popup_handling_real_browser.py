"""
Phase F (dry-run hardening) — Popup / new-window handling (real chromium).

Motivated by the spectropy.com certification dry run: a service launched via
window.open / target=_blank (the "Spectropy OS" launcher) was orphaned because the
browser session did not register popups. The additive fix registers popups opened by a
managed page and exposes follow_latest_popup(). This test certifies that behaviour and
that the EXISTING manual tab API is unaffected.

Skips automatically if Playwright/chromium is unavailable.
"""
import socket
import threading
import http.server
import socketserver
import time

import pytest

pytest.importorskip("playwright")

from app.execution_gateway.browser import session as bsession

POPUP_TARGET = b"<!doctype html><html><head><title>PopupTarget</title></head><body><h1 id='p'>Popup Target Page</h1></body></html>"
HOST = b"""<!doctype html><html><head><title>Host</title></head><body>
  <h1>Host</h1>
  <a id="blank" href="/target" target="_blank" rel="opener">Open blank</a>
  <a id="blank_noopener" href="/target" target="_blank">Open blank (noopener)</a>
  <button id="winopen" onclick="window.open('/target')">window.open</button>
</body></html>"""


class _H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = POPUP_TARGET if self.path.startswith("/target") else HOST
        self.send_response(200); self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *a): pass


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    httpd = socketserver.TCPServer(("127.0.0.1", port), _H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


@pytest.fixture(scope="module")
def chromium_ok():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True); b.close()
        return True
    except Exception as e:  # pragma: no cover
        pytest.skip(f"chromium unavailable: {e}")


@pytest.fixture(autouse=True)
def _clean():
    bsession._reset_for_testing()
    yield
    bsession._reset_for_testing()


def test_target_blank_with_opener_registered(server, chromium_ok):
    # target=_blank that RETAINS the opener (rel=opener) is a followable popup, like the
    # spectropy.com "Spectropy OS" launcher (window.open with a retained opener).
    sess = bsession.get_or_create("popup-blank", headless=True)
    try:
        page = sess.ensure_page()
        page.goto(server + "/")
        assert sess.popup_count() == 0
        page.locator("#blank").click()
        time.sleep(1)
        assert sess.popup_count() >= 1
        assert sess.tab_count() >= 2
        pop = sess.follow_latest_popup()
        assert pop is not None
        pop.wait_for_load_state("load", timeout=10000)
        assert "/target" in pop.url
        assert "Popup Target" in sess.ensure_page().inner_text("body")
    finally:
        bsession.close("popup-blank")


def test_window_open_popup_registered(server, chromium_ok):
    sess = bsession.get_or_create("popup-winopen", headless=True)
    try:
        page = sess.ensure_page()
        page.goto(server + "/")
        page.locator("#winopen").click()   # gesture-driven window.open
        time.sleep(1)
        assert sess.popup_count() >= 1
        assert "popups" in sess.to_dict() and sess.to_dict()["popups"] >= 1
    finally:
        bsession.close("popup-winopen")


def test_blocked_popup_url_captured(server, chromium_ok):
    # A non-gesture window.open is blocked by the browser (no popup Page is created), but
    # the intended URL is still captured so the pipeline can navigate directly.
    sess = bsession.get_or_create("popup-blocked", headless=True)
    try:
        page = sess.ensure_page()
        page.goto(server + "/")
        # call window.open OUTSIDE a user gesture -> blocked, returns null
        blocked = page.evaluate(
            "() => { const w = window.open('/target'); return w === null; }")
        urls = sess.intended_popup_urls()
        assert any("/target" in u for u in urls), urls
        # whether or not Chromium blocked it, the intended URL was recorded
    finally:
        bsession.close("popup-blocked")


def test_manual_tab_api_unaffected(server, chromium_ok):
    # regression: explicit context.new_page()+register_tab still behaves exactly as before
    sess = bsession.get_or_create("popup-manual", headless=True)
    try:
        sess.ensure_page().goto(server + "/")
        assert sess.tab_count() == 1
        assert sess.popup_count() == 0          # new_page() is NOT a popup
        p2 = sess.context.new_page()
        p2.goto(server + "/target")
        tid = sess.register_tab(p2)
        assert sess.tab_count() == 2
        assert sess.popup_count() == 0
        assert sess.switch_tab(tid) is True
        assert sess.active_tab_id == tid
        # dedup: re-registering the same page returns the same id, no new tab
        assert sess.register_tab(p2) == tid
        assert sess.tab_count() == 2
    finally:
        bsession.close("popup-manual")
