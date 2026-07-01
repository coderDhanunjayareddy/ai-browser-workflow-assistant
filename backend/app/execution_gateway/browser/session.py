"""
Phase C — BrowserSessionManager.

The ONLY owner of Playwright objects. The Execution Gateway / adapter ask the manager
for a session; they never create or hold a browser/context/page directly.

Responsibilities:
  - browser lifecycle (launch / close)
  - browser context
  - page lifecycle
  - tab registry mapping (tab_id -> page)
  - timeout management
  - cleanup
  - crash recovery (recreate a closed page / relaunch a disconnected browser)

Playwright is imported LAZILY inside methods so this module loads without Playwright
installed. Unit tests inject a fake session manager instead of launching a browser.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
import uuid
from typing import Any, Optional

DEFAULT_TIMEOUT_MS: int = 30_000
SCREENSHOT_DIR = os.path.join(tempfile.gettempdir(), "ai_browser_assist_screenshots")

# Records intended window.open() targets WITHOUT changing behaviour (calls through to the
# original and returns its result). Lets the pipeline recover the URL of a popup that the
# browser blocked (e.g. a non-gesture service launcher), so it can navigate there directly.
_WINDOW_OPEN_SHIM = """
(() => {
  try {
    if (window.__aiOpenShim) return; window.__aiOpenShim = true;
    window.__intendedOpens = [];
    const orig = window.open;
    window.open = function(u, t, f) {
      try { if (u) window.__intendedOpens.push(String(u)); } catch (e) {}
      try { return orig ? orig.apply(window, arguments) : null; } catch (e) { return null; }
    };
  } catch (e) {}
})();
"""


class BrowserSession:
    """Wraps the Playwright objects for one execution. Owns its page/context/browser."""

    def __init__(
        self,
        execution_id: str,
        playwright:   Any,
        browser:      Any,
        context:      Any,
        page:         Any,
        *,
        headless:     bool = True,
        timeout_ms:   int = DEFAULT_TIMEOUT_MS,
        created_at:   float = 0.0,
    ) -> None:
        self.execution_id = execution_id
        self._playwright  = playwright
        self.browser      = browser
        self.context      = context
        self.page         = page
        self.headless     = headless
        self.timeout_ms   = timeout_ms
        self.created_at   = created_at
        self.closed       = False
        # tab registry: tab_id -> page
        self._tabs: dict[str, Any] = {"tab-0": page}
        self.active_tab_id = "tab-0"
        self.screenshots: list[str] = []
        self.downloads:   list[str] = []
        # popup / new-window registry (window.open / target=_blank)
        self._popups: list[Any] = []
        self._attach_context_listener()

    # ── popups / new windows ───────────────────────────────────────────────────

    def _attach_context_listener(self) -> None:
        """Register popups (window.open / target=_blank) opened in this context.

        Uses the context 'page' event + page.opener() to tell a real popup (opener set)
        from an explicit context.new_page() (opener None), so the manual register_tab /
        switch_tab API is unaffected. Best-effort: guarded for fake contexts in unit
        tests. The initial page (tab-0) was created before this listener, so it is never
        mistaken for a popup."""
        try:
            self.context.on("page", self._on_new_page)
        except Exception:
            pass

    def _on_new_page(self, page: Any) -> None:
        try:
            if page is None or any(page is p for p in self._popups):
                return
            try:
                opener = page.opener()
            except Exception:
                opener = None
            if opener is not None:          # real popup, NOT an explicit new_page()
                self._popups.append(page)
                self.register_tab(page)     # make it followable (dedup-aware)
        except Exception:
            pass

    def latest_popup(self) -> Any:
        return self._popups[-1] if self._popups else None

    def popup_count(self) -> int:
        return len(self._popups)

    def follow_latest_popup(self) -> Any:
        """Switch the active page to the most recently opened popup (if any).

        Explicit, opt-in — nothing calls this automatically, so existing single-page
        flows are unchanged. Returns the popup page or None."""
        pop = self.latest_popup()
        if pop is None:
            return None
        self.switch_tab(self.register_tab(pop))
        return pop

    def intended_popup_urls(self) -> list[str]:
        """URLs the current page tried to window.open() — even if the popup was blocked.

        Lets a caller navigate directly to a service launcher's target when the browser
        suppressed the popup. Best-effort; read on the session's own thread."""
        try:
            vals = self.ensure_page().evaluate("() => window.__intendedOpens || []")
            return [str(u) for u in vals] if vals else []
        except Exception:
            return []

    # ── crash recovery ─────────────────────────────────────────────────────────

    def ensure_page(self) -> Any:
        """Return a live page, recreating it if the previous one closed/crashed."""
        page = self.page
        try:
            if page is None or page.is_closed():
                page = self.context.new_page()
                self.page = page
                self._tabs[self.active_tab_id] = page
        except Exception:
            # Context/browser may be gone — recreate a page on the existing context.
            page = self.context.new_page()
            self.page = page
            self._tabs[self.active_tab_id] = page
        return page

    # ── tabs / windows ─────────────────────────────────────────────────────────

    def register_tab(self, page: Any) -> str:
        # dedup: a page already registered (e.g. auto-registered popup) keeps its id
        for tid, pg in self._tabs.items():
            if pg is page:
                return tid
        tab_id = f"tab-{len(self._tabs)}"
        self._tabs[tab_id] = page
        return tab_id

    def switch_tab(self, tab_id: str) -> bool:
        page = self._tabs.get(tab_id)
        if page is None:
            return False
        self.page = page
        self.active_tab_id = tab_id
        return True

    def tab_count(self) -> int:
        return len(self._tabs)

    def refresh(self) -> None:
        self.ensure_page().reload()

    # ── screenshots ────────────────────────────────────────────────────────────

    def screenshot(self, label: str = "") -> Optional[str]:
        try:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            fname = f"{self.execution_id}-{label or 'shot'}-{str(uuid.uuid4())[:6]}.png"
            path = os.path.join(SCREENSHOT_DIR, fname)
            self.ensure_page().screenshot(path=path)
            self.screenshots.append(path)
            return path
        except Exception:
            return None

    def latest_screenshot(self) -> Optional[str]:
        return self.screenshots[-1] if self.screenshots else None

    # ── cleanup ────────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        for closer in (
            lambda: self.context.close(),
            lambda: self.browser.close(),
            lambda: self._playwright.stop(),
        ):
            try:
                closer()
            except Exception:
                pass

    def to_dict(self) -> dict[str, Any]:
        url = None
        title = None
        try:
            url = self.page.url
            title = self.page.title()
        except Exception:
            pass
        return {
            "execution_id":  self.execution_id,
            "browser":       "chromium",
            "headless":      self.headless,
            "timeout_ms":    self.timeout_ms,
            "active_tab_id": self.active_tab_id,
            "tab_count":     self.tab_count(),
            "popups":        len(self._popups),
            "current_url":   url,
            "current_title": title,
            "screenshots":   len(self.screenshots),
            "downloads":     list(self.downloads),
            "closed":        self.closed,
            "created_at":    self.created_at,
        }


class BrowserSessionManager:

    def __init__(self, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, BrowserSession] = {}
        self._timeout_ms = timeout_ms
        self._launched = 0
        self._closed = 0

    def get_or_create(self, execution_id: str, *, headless: bool = True) -> BrowserSession:
        with self._lock:
            existing = self._sessions.get(execution_id)
            if existing is not None and not existing.closed:
                existing.ensure_page()
                return existing
            session = self._launch(execution_id, headless=headless)
            self._sessions[execution_id] = session
            self._launched += 1
            return session

    def _launch(self, execution_id: str, *, headless: bool) -> BrowserSession:
        # Lazy import: only needed when actually launching a real browser.
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        context.set_default_timeout(self._timeout_ms)
        try:
            context.add_init_script(_WINDOW_OPEN_SHIM)   # capture window.open targets (additive)
        except Exception:
            pass
        page = context.new_page()
        return BrowserSession(
            execution_id, pw, browser, context, page,
            headless=headless, timeout_ms=self._timeout_ms, created_at=time.time(),
        )

    def get(self, execution_id: str) -> Optional[BrowserSession]:
        with self._lock:
            return self._sessions.get(execution_id)

    def session_info(self, execution_id: str) -> Optional[dict]:
        s = self.get(execution_id)
        return s.to_dict() if s else None

    def screenshot(self, execution_id: str, label: str = "") -> Optional[str]:
        s = self.get(execution_id)
        return s.screenshot(label) if s else None

    def close(self, execution_id: str) -> bool:
        with self._lock:
            s = self._sessions.pop(execution_id, None)
        if s is None:
            return False
        s.close()
        self._closed += 1
        return True

    def close_all(self) -> int:
        with self._lock:
            ids = list(self._sessions.keys())
        n = 0
        for eid in ids:
            if self.close(eid):
                n += 1
        return n

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for s in self._sessions.values() if not s.closed)

    def stats(self) -> dict:
        with self._lock:
            return {
                "active_sessions": sum(1 for s in self._sessions.values() if not s.closed),
                "total_launched":  self._launched,
                "total_closed":    self._closed,
                "timeout_ms":      self._timeout_ms,
            }

    def _reset_for_testing(self) -> None:
        self.close_all()
        with self._lock:
            self._sessions.clear()
            self._launched = 0
            self._closed = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_manager = BrowserSessionManager()


def get_or_create(execution_id: str, *, headless: bool = True) -> BrowserSession:
    return _manager.get_or_create(execution_id, headless=headless)

def get(execution_id: str) -> Optional[BrowserSession]:
    return _manager.get(execution_id)

def session_info(execution_id: str) -> Optional[dict]:
    return _manager.session_info(execution_id)

def screenshot(execution_id: str, label: str = "") -> Optional[str]:
    return _manager.screenshot(execution_id, label)

def close(execution_id: str) -> bool:
    return _manager.close(execution_id)

def close_all() -> int:
    return _manager.close_all()

def active_count() -> int:
    return _manager.active_count()

def stats() -> dict:
    return _manager.stats()

def _reset_for_testing() -> None:
    _manager._reset_for_testing()
