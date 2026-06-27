"""Phase C — Unit tests: session.py (BrowserSession + BrowserSessionManager)."""
import pytest
from app.execution_gateway.browser.session import BrowserSession, BrowserSessionManager


class FakePage:
    def __init__(self, closed=False): self._closed = closed; self.url = "about:blank"; self.reloaded = False
    def is_closed(self): return self._closed
    def reload(self): self.reloaded = True
    def title(self): return "Fake"
    def screenshot(self, path=None): return None


class FakeContext:
    def __init__(self): self.pages_created = 0; self.closed = False
    def new_page(self): self.pages_created += 1; return FakePage()
    def set_default_timeout(self, ms): self.timeout = ms
    def close(self): self.closed = True


class FakeBrowser:
    def __init__(self): self.closed = False
    def close(self): self.closed = True


class FakePW:
    def __init__(self): self.stopped = False
    def stop(self): self.stopped = True


def _session(page=None):
    return BrowserSession("e1", FakePW(), FakeBrowser(), FakeContext(),
                          page or FakePage(), created_at=1.0)


class TestBrowserSession:
    def test_initial_tab(self):
        s = _session()
        assert s.active_tab_id == "tab-0"
        assert s.tab_count() == 1

    def test_ensure_page_live(self):
        p = FakePage()
        s = _session(p)
        assert s.ensure_page() is p

    def test_ensure_page_recreates_closed(self):
        closed = FakePage(closed=True)
        s = _session(closed)
        new = s.ensure_page()
        assert new is not closed
        assert s.page is new

    def test_register_tab(self):
        s = _session()
        tid = s.register_tab(FakePage())
        assert tid == "tab-1"
        assert s.tab_count() == 2

    def test_switch_tab(self):
        s = _session()
        tid = s.register_tab(FakePage())
        assert s.switch_tab(tid) is True
        assert s.active_tab_id == tid

    def test_switch_unknown_tab(self):
        assert _session().switch_tab("nope") is False

    def test_refresh(self):
        p = FakePage()
        s = _session(p)
        s.refresh()
        assert p.reloaded is True

    def test_close_idempotent(self):
        s = _session()
        s.close()
        s.close()
        assert s.closed is True
        assert s.browser.closed is True
        assert s.context.closed is True

    def test_to_dict(self):
        d = _session().to_dict()
        for k in ["execution_id", "browser", "headless", "timeout_ms", "active_tab_id",
                  "tab_count", "screenshots", "downloads", "closed", "created_at"]:
            assert k in d
        assert d["browser"] == "chromium"


class TestSessionManager:
    def test_get_or_create_launches(self):
        mgr = BrowserSessionManager()
        # override _launch to avoid real playwright
        mgr._launch = lambda eid, headless=True: _session()
        s = mgr.get_or_create("e1")
        assert s is not None
        assert mgr.active_count() == 1

    def test_get_or_create_reuses(self):
        mgr = BrowserSessionManager()
        launches = {"n": 0}
        def fake_launch(eid, headless=True):
            launches["n"] += 1
            return _session()
        mgr._launch = fake_launch
        mgr.get_or_create("e1")
        mgr.get_or_create("e1")
        assert launches["n"] == 1   # reused

    def test_get(self):
        mgr = BrowserSessionManager()
        mgr._launch = lambda eid, headless=True: _session()
        s = mgr.get_or_create("e1")
        assert mgr.get("e1") is s
        assert mgr.get("absent") is None

    def test_session_info(self):
        mgr = BrowserSessionManager()
        mgr._launch = lambda eid, headless=True: _session()
        mgr.get_or_create("e1")
        assert mgr.session_info("e1") is not None
        assert mgr.session_info("absent") is None

    def test_close(self):
        mgr = BrowserSessionManager()
        mgr._launch = lambda eid, headless=True: _session()
        mgr.get_or_create("e1")
        assert mgr.close("e1") is True
        assert mgr.get("e1") is None
        assert mgr.close("e1") is False

    def test_close_all(self):
        mgr = BrowserSessionManager()
        mgr._launch = lambda eid, headless=True: _session()
        mgr.get_or_create("e1"); mgr.get_or_create("e2")
        assert mgr.close_all() == 2

    def test_stats(self):
        mgr = BrowserSessionManager()
        mgr._launch = lambda eid, headless=True: _session()
        mgr.get_or_create("e1")
        s = mgr.stats()
        for k in ["active_sessions", "total_launched", "total_closed", "timeout_ms"]:
            assert k in s
        assert s["total_launched"] == 1
