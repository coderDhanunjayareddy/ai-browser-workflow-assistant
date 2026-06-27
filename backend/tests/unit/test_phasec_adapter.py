"""Phase C — Unit tests: playwright_adapter.py (actions, validation, up/download, retry).

Uses fully fake page/session objects — no real browser. Validates that the adapter
implements the existing contract and maps browser errors into the retry system.
"""
import pytest
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_gateway.models import make_command, CommandType, RetryConfig


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeLocator:
    def __init__(self, page, key): self.page = page; self.key = key
    def click(self, **k): self.page.events.append(("click", self.key))
    def fill(self, text, **k): self.page.events.append(("fill", text))
    def inner_text(self): return self.page.element_text
    def inner_html(self): return self.page.element_html
    def count(self): return self.page.element_count
    def wait_for(self, **k): self.page.events.append(("wait_for", self.key))
    def set_input_files(self, files): self.page.events.append(("upload", files))


class FakeDownload:
    def __init__(self, path): self._path = path; self.suggested_filename = "file.txt"
    def path(self): return self._path


class FakeDownloadCtx:
    def __init__(self, page): self.page = page
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @property
    def value(self): return FakeDownload(self.page.download_path)


class FakePage:
    def __init__(self, *, url="https://example.com/page", body="Welcome here",
                 element_text="ELEM TEXT", element_html="<b>e</b>", element_count=1,
                 download_path="/tmp/file.txt"):
        self.url = url; self.body = body
        self.element_text = element_text; self.element_html = element_html
        self.element_count = element_count; self.download_path = download_path
        self.events = []
    def is_closed(self): return False
    def goto(self, url, **k): self.url = url; self.events.append(("goto", url))
    def title(self): return "Title"
    def locator(self, sel): return FakeLocator(self, ("locator", sel))
    def get_by_test_id(self, v): return FakeLocator(self, ("testid", v))
    def get_by_label(self, v): return FakeLocator(self, ("label", v))
    def get_by_role(self, v, name=None): return FakeLocator(self, ("role", v))
    def inner_text(self, sel): return self.body
    def content(self): return f"<html>{self.body}</html>"
    def wait_for_timeout(self, ms): self.events.append(("wait_timeout", ms))
    def evaluate(self, js): self.events.append(("eval", js))
    def expect_download(self, **k): return FakeDownloadCtx(self)


class FlakyPage(FakePage):
    """Raises a given exception for the first `fail_times` goto calls, then succeeds."""
    def __init__(self, exc, fail_times, **kw):
        super().__init__(**kw); self._exc = exc; self._fail = fail_times; self._n = 0
    def goto(self, url, **k):
        self._n += 1
        if self._n <= self._fail:
            raise self._exc
        self.url = url


class FailingLocatorPage(FakePage):
    """Locator.click always raises a given exception (terminal-error tests)."""
    def __init__(self, exc, **kw): super().__init__(**kw); self._exc = exc
    def locator(self, sel): return self._fail_locator()
    def get_by_test_id(self, v): return self._fail_locator()
    def _fail_locator(self):
        exc = self._exc
        class L:
            def click(self, **k): raise exc
            def fill(self, *a, **k): raise exc
        return L()


class FakeSession:
    def __init__(self, page):
        self.page = page; self.active_tab_id = "tab-0"; self.downloads = []
    def ensure_page(self): return self.page
    def screenshot(self, label=""): return f"/tmp/{label}.png"
    def refresh(self): self.page.events.append(("refresh",))


class FakeMgr:
    def __init__(self, page): self.session = FakeSession(page); self.closed = False
    def get_or_create(self, eid, headless=True): return self.session
    def get(self, eid): return self.session
    def close(self, eid): self.closed = True; return True


def _adapter(page, retry_config=None):
    return PlaywrightAdapter(execution_id="e1", session_manager=FakeMgr(page),
                             retry_config=retry_config or RetryConfig(max_retries=2))


def _cmd(ctype, params=None, expected="", strategy="NONE"):
    return make_command(ctype, "s1", 1, "target", parameters=params or {},
                        expected_result=expected, validation_strategy=strategy)


# ── Actions ───────────────────────────────────────────────────────────────────

class TestNavigate:
    def test_success(self):
        a = _adapter(FakePage())
        r = a.navigate(_cmd(CommandType.navigate, {"url": "https://x.com"}))
        assert r.success is True
        assert r.output["details"]["url"] == "https://x.com"

    def test_uses_target_when_no_url_param(self):
        p = FakePage()
        a = _adapter(p)
        r = a.navigate(make_command(CommandType.navigate, "s1", 1, "https://t.com"))
        assert p.url == "https://t.com"

    def test_validation_passed_true(self):
        a = _adapter(FakePage())
        assert a.navigate(_cmd(CommandType.navigate, {"url": "u"})).validation_passed is True


class TestClick:
    def test_success(self):
        p = FakePage(); a = _adapter(p)
        r = a.click(_cmd(CommandType.click, {"testid": "go"}))
        assert r.success is True
        assert r.output["details"]["strategy"] == "testid"
        assert ("click", ("testid", "go")) in p.events

    def test_resolution_priority(self):
        a = _adapter(FakePage())
        r = a.click(_cmd(CommandType.click, {"selector": "#x", "testid": "t"}))
        assert r.output["details"]["strategy"] == "selector"


class TestType:
    def test_success(self):
        p = FakePage(); a = _adapter(p)
        r = a.type(_cmd(CommandType.type, {"id": "email", "value": "hi@x.com"}))
        assert r.success is True
        assert r.output["details"]["length"] == 8
        assert ("fill", "hi@x.com") in p.events

    def test_text_alias(self):
        p = FakePage(); a = _adapter(p)
        a.type(_cmd(CommandType.type, {"id": "x", "text": "abc"}))
        assert ("fill", "abc") in p.events


class TestWait:
    def test_duration_wait(self):
        p = FakePage(); a = _adapter(p)
        r = a.wait(_cmd(CommandType.wait, {"ms": 250}))
        assert r.success is True
        assert r.output["details"]["waited_for"] == "duration"
        assert ("wait_timeout", 250) in p.events

    def test_element_wait(self):
        p = FakePage(); a = _adapter(p)
        r = a.wait(_cmd(CommandType.wait, {"id": "x", "timeout_ms": 1000}))
        assert r.output["details"]["waited_for"] == "element"


class TestExtract:
    def test_element_text(self):
        a = _adapter(FakePage(element_text="HELLO"))
        r = a.extract(_cmd(CommandType.extract, {"selector": ".m", "mode": "text"}))
        assert r.success is True
        assert r.output["details"]["content_length"] == 5

    def test_element_html(self):
        a = _adapter(FakePage(element_html="<b>x</b>"))
        r = a.extract(_cmd(CommandType.extract, {"selector": ".m", "mode": "html"}))
        assert r.output["details"]["mode"] == "html"

    def test_page_text_when_no_selector(self):
        a = _adapter(FakePage(body="page body text"))
        r = a.extract(_cmd(CommandType.extract, {"mode": "text"}))
        assert r.output["details"]["strategy"] == "page"
        assert "page body text" in r.output["details"]["content_preview"]


class TestValidate:
    def test_url_match_pass(self):
        a = _adapter(FakePage(url="https://example.com/abc"))
        r = a.validate(_cmd(CommandType.validate, {"expected_url": "example.com"}, strategy="URL_MATCH"))
        assert r.validation_passed is True

    def test_url_match_fail(self):
        a = _adapter(FakePage(url="https://example.com/abc"))
        r = a.validate(_cmd(CommandType.validate, {"expected_url": "other.com"}, strategy="URL_MATCH"))
        assert r.validation_passed is False
        assert r.success is True   # dispatch succeeded; validation failed

    def test_text_match_pass(self):
        a = _adapter(FakePage(body="the answer is 42"))
        r = a.validate(_cmd(CommandType.validate, {"expected_text": "answer"}, strategy="TEXT_MATCH"))
        assert r.validation_passed is True

    def test_text_match_fail(self):
        a = _adapter(FakePage(body="nothing here"))
        r = a.validate(_cmd(CommandType.validate, {"expected_text": "missing"}, strategy="TEXT_MATCH"))
        assert r.validation_passed is False

    def test_exists_pass(self):
        a = _adapter(FakePage(element_count=2))
        r = a.validate(_cmd(CommandType.validate, {"selector": ".x"}, strategy="DOM_PRESENCE"))
        assert r.validation_passed is True

    def test_exists_fail(self):
        a = _adapter(FakePage(element_count=0))
        r = a.validate(_cmd(CommandType.validate, {"selector": ".x"}, strategy="VALIDATE_EXISTS"))
        assert r.validation_passed is False


class TestUploadDownload:
    def test_upload_single(self):
        p = FakePage(); a = _adapter(p)
        r = a.upload(_cmd(CommandType.upload, {"selector": "input[type=file]", "file": "/tmp/a.txt"}))
        assert r.success is True
        assert r.output["details"]["count"] == 1
        assert ("upload", ["/tmp/a.txt"]) in p.events

    def test_upload_multiple(self):
        p = FakePage(); a = _adapter(p)
        r = a.upload(_cmd(CommandType.upload, {"selector": "input", "files": ["/a", "/b"]}))
        assert r.output["details"]["count"] == 2

    def test_upload_no_files_fails(self):
        a = _adapter(FakePage())
        r = a.upload(_cmd(CommandType.upload, {"selector": "input"}))
        assert r.success is False
        assert r.output["error"]["error_type"] == "UPLOAD_FAILED"

    def test_download(self):
        a = _adapter(FakePage(download_path="/tmp/report.csv"))
        r = a.download(_cmd(CommandType.download, {"testid": "dl"}))
        assert r.success is True
        assert r.output["details"]["download_path"] == "/tmp/report.csv"


class TestCustom:
    def test_scroll(self):
        p = FakePage(); a = _adapter(p)
        r = a.execute_custom(_cmd(CommandType.custom, {"action": "scroll", "dy": 200}))
        assert r.success is True
        assert any(e[0] == "eval" for e in p.events)

    def test_refresh(self):
        p = FakePage(); a = _adapter(p)
        r = a.execute_custom(_cmd(CommandType.custom, {"action": "refresh"}))
        assert ("refresh",) in p.events

    def test_noop(self):
        a = _adapter(FakePage())
        r = a.execute_custom(_cmd(CommandType.custom, {}))
        assert r.success is True


# ── Retry mapping (transient retried, terminal not) ──────────────────────────

class TestRetryMapping:
    def test_transient_timeout_retried_then_succeeds(self):
        # fail twice with timeout, succeed on 3rd → within max_retries=2 (3 attempts)
        page = FlakyPage(Exception("Timeout 30000ms exceeded"), fail_times=2)
        a = _adapter(page, RetryConfig(max_retries=2))
        r = a.navigate(_cmd(CommandType.navigate, {"url": "https://x.com"}))
        assert r.success is True
        assert r.output["attempts"] == 3

    def test_transient_exhausted_fails(self):
        page = FlakyPage(Exception("Timeout exceeded"), fail_times=5)
        a = _adapter(page, RetryConfig(max_retries=2))
        r = a.navigate(_cmd(CommandType.navigate, {"url": "https://x.com"}))
        assert r.success is False
        assert r.output["attempts"] == 3   # bounded — never infinite
        assert r.output["error"]["error_type"] == "TIMEOUT"

    def test_terminal_missing_element_not_retried(self):
        page = FailingLocatorPage(Exception("waiting for selector: no node found"))
        a = _adapter(page, RetryConfig(max_retries=2))
        r = a.click(_cmd(CommandType.click, {"selector": ".x"}))
        assert r.success is False
        assert r.output["attempts"] == 1   # NOT retried
        assert r.output["error"]["error_type"] == "SELECTOR_NOT_FOUND"

    def test_terminal_invalid_selector_not_retried(self):
        page = FailingLocatorPage(Exception("is not a valid selector"))
        a = _adapter(page, RetryConfig(max_retries=2))
        r = a.click(_cmd(CommandType.click, {"selector": ".x"}))
        assert r.output["attempts"] == 1
        assert r.output["error"]["error_type"] == "INVALID_SELECTOR"

    def test_error_recorded_in_output(self):
        page = FailingLocatorPage(Exception("no node found"))
        a = _adapter(page)
        r = a.click(_cmd(CommandType.click, {"selector": ".x"}))
        assert "error" in r.output
        assert r.output["error"]["retryable"] is False

    def test_screenshot_on_failure(self):
        page = FailingLocatorPage(Exception("no node found"))
        a = _adapter(page)
        r = a.click(_cmd(CommandType.click, {"selector": ".x"}))
        assert r.output["screenshot_path"] is not None


class TestContract:
    def test_name(self):
        assert _adapter(FakePage()).name == "playwright"

    def test_dispatch_routes(self):
        p = FakePage(); a = _adapter(p)
        r = a.dispatch(_cmd(CommandType.navigate, {"url": "https://x.com"}))
        assert r.success is True

    def test_screenshot_param(self):
        a = _adapter(FakePage())
        r = a.navigate(_cmd(CommandType.navigate, {"url": "u", "screenshot": True}))
        assert r.output["screenshot_path"] is not None
