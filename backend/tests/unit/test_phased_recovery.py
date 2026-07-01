"""Phase D — Unit tests: recovery.py (RecoveryEngine, deterministic)."""
import pytest
from app.execution_gateway.browser import recovery as rec
from app.execution_gateway.browser import failure_classes as fc
from app.execution_gateway.browser.failure_classes import FailureCategory, RecoveryAction


class FakeLocator:
    def __init__(self, page): self.page = page
    def scroll_into_view_if_needed(self, **k): self.page.events.append("scroll_into_view")


class FakePage:
    def __init__(self): self.events = []; self.url = "https://x/p"
    def is_closed(self): return False
    def wait_for_timeout(self, ms): self.events.append(("wait", ms))
    def wait_for_load_state(self, state, timeout=None): self.events.append(("networkidle", state))
    def inner_text(self, sel): self.events.append("reread"); return "body"
    def evaluate(self, js): self.events.append("evaluate")
    def locator(self, s): return FakeLocator(self)
    def get_by_test_id(self, v): return FakeLocator(self)


class FakeSession:
    def __init__(self, page=None, context=None):
        self.page = page or FakePage(); self.context = context; self.reloaded = False
    def ensure_page(self): return self.page
    def refresh(self): self.reloaded = True


class _Cmd:
    def __init__(self, params=None): self.parameters = params or {}


def _analysis(category):
    # build a FailureAnalysis with the right profile via a representative message
    msgs = {
        FailureCategory.element_not_found: ("no node found", "click"),
        FailureCategory.element_hidden: ("element is hidden", "click"),
        FailureCategory.detached_element: ("element is detached", "click"),
        FailureCategory.navigation_timeout: ("Timeout exceeded", "navigate"),
        FailureCategory.validation_failure: ("validation failed", "validate"),
        FailureCategory.unexpected_popup: ("unexpected popup", "click"),
        FailureCategory.page_crash: ("target closed", "click"),
        FailureCategory.network_idle_timeout: ("waiting for networkidle", "navigate"),
    }
    msg, phase = msgs[category]
    a = fc.classify_failure(Exception(msg), phase=phase)
    assert a.category == category, f"{a.category} != {category}"
    return a


class TestRecoveryActions:
    def test_element_not_found_waits(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.element_not_found), session, _Cmd({"testid": "x"}))
        assert "WAIT" in r.actions or "REFRESH_LOCATOR" in r.actions
        assert any(e[0] == "wait" for e in page.events if isinstance(e, tuple))

    def test_element_hidden_scrolls(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.element_hidden), session, _Cmd({"testid": "x"}))
        assert "SCROLL_INTO_VIEW" in r.actions
        assert "scroll_into_view" in page.events

    def test_detached_requeries(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.detached_element), session, _Cmd())
        assert "REQUERY" in r.actions

    def test_navigation_timeout_waits_networkidle(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.navigation_timeout), session, _Cmd())
        assert "WAIT_NETWORK_IDLE" in r.actions
        assert any(e[0] == "networkidle" for e in page.events if isinstance(e, tuple))

    def test_validation_rereads(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.validation_failure), session, _Cmd())
        assert "REREAD_PAGE" in r.actions

    def test_page_crash_reloads(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.page_crash), session, _Cmd())
        assert "RELOAD_PAGE" in r.actions
        assert session.reloaded is True

    def test_popup_dismissed(self):
        page = FakePage()
        class Ctx:
            def __init__(self, pages): self.pages = pages
        extra = FakePage()
        session = FakeSession(page, context=Ctx([page, extra]))
        r = rec.recover(_analysis(FailureCategory.unexpected_popup), session, _Cmd())
        assert "DISMISS_POPUP" in r.actions


class TestRecoveryResult:
    def test_recovered_flag(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.element_hidden), session, _Cmd({"testid": "x"}))
        assert r.recovered is True

    def test_to_dict(self):
        page = FakePage(); session = FakeSession(page)
        r = rec.recover(_analysis(FailureCategory.element_hidden), session, _Cmd({"testid": "x"}))
        d = r.to_dict()
        for k in ["category", "actions", "recovered", "notes"]:
            assert k in d

    def test_recovery_never_raises_on_bad_session(self):
        # session.ensure_page raises → recovery does not crash
        class BadSession:
            def ensure_page(self): raise RuntimeError("boom")
        r = rec.recover(_analysis(FailureCategory.element_hidden), BadSession(), _Cmd({"testid": "x"}))
        assert r.recovered is False

    def test_permanent_no_recovery_action(self):
        # invalid selector is permanent → recommended_recovery NONE → no concrete action
        a = fc.classify_failure(Exception("is not a valid selector"), phase="click")
        page = FakePage()
        r = rec.recover(a, FakeSession(page), _Cmd())
        assert r.recovered is False
        assert r.actions == []
