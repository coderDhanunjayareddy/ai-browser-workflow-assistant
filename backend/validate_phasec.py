"""
Phase C — Playwright Adapter V1 — Validation Suite.

Minimum 1200 checks: static safety, execution verification, retry verification,
browser-lifecycle verification. Real-browser checks run when chromium is available.
Run: python validate_phasec.py
"""
import sys
import time
import pathlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SECTIONS: list[tuple[str, int, int]] = []

def section(name: str):
    global PASS, FAIL
    SECTIONS.append((name, PASS, FAIL))
    print(f"\n[{name}]")

def check(label: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {label}")

def summary(name: str):
    prev = SECTIONS[-1]
    print(f"  -> {PASS - prev[1]} pass, {FAIL - prev[2]} fail")


# ── imports under test ────────────────────────────────────────────────────────
from app.execution_gateway.browser import errors as berr
from app.execution_gateway.browser import capabilities as caps
from app.execution_gateway.browser import resolver as res
from app.execution_gateway.browser import session as bsession
from app.execution_gateway.browser.session import BrowserSession, BrowserSessionManager
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_gateway.browser.errors import BrowserErrorType
from app.execution_gateway.models import make_command, CommandType, RetryConfig, ExecutionState
from app.execution_gateway import engine as gateway, registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_planning import registry as plan_reg, planner
from app.execution_planning.registry import set_status
from app.execution_planning.models import (
    PlanStatus, ActionType, TargetType, ValidationStrategy, ExecutionMode, make_step, make_plan,
)
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeLocator:
    def __init__(self, page, key): self.page = page; self.key = key
    def click(self, **k): self.page.events.append(("click", self.key))
    def fill(self, t, **k): self.page.events.append(("fill", t))
    def inner_text(self): return self.page.element_text
    def inner_html(self): return self.page.element_html
    def count(self): return self.page.element_count
    def wait_for(self, **k): self.page.events.append(("wait_for",))
    def set_input_files(self, files): self.page.events.append(("upload", files))

class FakeDownload:
    def __init__(self, p): self._p = p; self.suggested_filename = "f.txt"
    def path(self): return self._p
class FakeDLCtx:
    def __init__(self, page): self.page = page
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @property
    def value(self): return FakeDownload(self.page.download_path)

class FakePage:
    def __init__(self, url="https://example.com/p", body="objective satisfied", element_text="ET",
                 element_html="<b>e</b>", element_count=1, download_path="/tmp/f.txt", closed=False):
        self.url = url; self.body = body; self.element_text = element_text
        self.element_html = element_html; self.element_count = element_count
        self.download_path = download_path; self._closed = closed; self.events = []; self.reloaded = False
    def is_closed(self): return self._closed
    def goto(self, url, **k): self.url = url; self.events.append(("goto", url))
    def title(self): return "T"
    def reload(self): self.reloaded = True
    def locator(self, s): return FakeLocator(self, ("locator", s))
    def get_by_test_id(self, v): return FakeLocator(self, ("testid", v))
    def get_by_label(self, v): return FakeLocator(self, ("label", v))
    def get_by_role(self, v, name=None): return FakeLocator(self, ("role", v))
    def inner_text(self, sel): return self.body
    def content(self): return f"<html>{self.body}</html>"
    def wait_for_timeout(self, ms): self.events.append(("wait", ms))
    def evaluate(self, js): self.events.append(("eval", js))
    def expect_download(self, **k): return FakeDLCtx(self)

class FlakyPage(FakePage):
    def __init__(self, exc, fail_times, **kw): super().__init__(**kw); self._exc = exc; self._f = fail_times; self._n = 0
    def goto(self, url, **k):
        self._n += 1
        if self._n <= self._f: raise self._exc
        self.url = url

class FailLocPage(FakePage):
    def __init__(self, exc, **kw): super().__init__(**kw); self._exc = exc
    def locator(self, s): return self._fl()
    def get_by_test_id(self, v): return self._fl()
    def _fl(self):
        exc = self._exc
        class L:
            def click(self, **k): raise exc
            def fill(self, *a, **k): raise exc
        return L()

class FakeSession:
    def __init__(self, page): self.page = page; self.active_tab_id = "tab-0"; self.downloads = []
    def ensure_page(self): return self.page
    def screenshot(self, label=""): return f"/tmp/{label}.png"
    def refresh(self): self.page.reload()

class FakeMgr:
    def __init__(self, page): self.session = FakeSession(page); self.closed = False
    def get_or_create(self, eid, headless=True): return self.session
    def get(self, eid): return self.session
    def close(self, eid): self.closed = True; return True

def _A(page, retry=None):
    return PlaywrightAdapter(execution_id="e1", session_manager=FakeMgr(page),
                             retry_config=retry or RetryConfig(max_retries=2))
def _C(ctype, params=None, expected="", strategy="NONE"):
    return make_command(ctype, "s1", 1, "tgt", parameters=params or {}, expected_result=expected,
                        validation_strategy=strategy)

# Fake playwright objects for BrowserSession lifecycle checks.
class FakePW:
    def __init__(self): self.stopped = False
    def stop(self): self.stopped = True
class FakeBrowser:
    def __init__(self): self.closed = False
    def close(self): self.closed = True
class FakeContext:
    def __init__(self): self.closed = False; self.made = 0; self.timeout = None
    def new_page(self): self.made += 1; return FakePage()
    def set_default_timeout(self, ms): self.timeout = ms
    def close(self): self.closed = True
def _BS(page=None):
    return BrowserSession("e1", FakePW(), FakeBrowser(), FakeContext(), page or FakePage(), created_at=1.0)


def _ready_plan(mission="m-1"):
    auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600, mission_id=mission, task_id="t-1")
    auth_reg.add(auth)
    mission_store.put(Mission(mission, "t", "objective satisfied", MissionState.active, task_ids=["t-1"]))
    plan = planner.create_plan(auth)
    plan_reg.add(plan); set_status(plan.plan_id, PlanStatus.ready)
    return plan_reg.get(plan.plan_id)

def _reset():
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store]:
        m._reset_for_testing()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Package structure
# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
for f in ["app/execution_gateway/browser/__init__.py", "app/execution_gateway/browser/errors.py",
          "app/execution_gateway/browser/capabilities.py", "app/execution_gateway/browser/resolver.py",
          "app/execution_gateway/browser/session.py", "app/execution_gateway/browser/playwright_adapter.py",
          "app/execution_gateway/browser/run.py"]:
    check(f"file exists: {f}", pathlib.Path(f).exists())
summary("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Error types + sets
# ─────────────────────────────────────────────────────────────────────────────
section("2. Error Types + Sets")
check("12 error types", len(BrowserErrorType) == 12)
for et, v in [(BrowserErrorType.timeout, "TIMEOUT"), (BrowserErrorType.detached_node, "DETACHED_NODE"),
              (BrowserErrorType.stale_handle, "STALE_HANDLE"), (BrowserErrorType.temporary_rendering, "TEMPORARY_RENDERING"),
              (BrowserErrorType.selector_not_found, "SELECTOR_NOT_FOUND"), (BrowserErrorType.invalid_selector, "INVALID_SELECTOR"),
              (BrowserErrorType.navigation_failed, "NAVIGATION_FAILED"), (BrowserErrorType.download_failed, "DOWNLOAD_FAILED"),
              (BrowserErrorType.upload_failed, "UPLOAD_FAILED"), (BrowserErrorType.validation_failed, "VALIDATION_FAILED"),
              (BrowserErrorType.authorization_error, "AUTHORIZATION_ERROR"), (BrowserErrorType.unexpected, "UNEXPECTED_BROWSER_ERROR")]:
    check(f"error {v}", et.value == v)
check("4 retryable", len(berr.RETRYABLE_ERRORS) == 4)
for et in [BrowserErrorType.timeout, BrowserErrorType.detached_node, BrowserErrorType.stale_handle, BrowserErrorType.temporary_rendering]:
    check(f"{et.value} retryable", berr.is_retryable(et) is True)
for et in [BrowserErrorType.selector_not_found, BrowserErrorType.invalid_selector, BrowserErrorType.authorization_error,
           BrowserErrorType.navigation_failed, BrowserErrorType.download_failed, BrowserErrorType.upload_failed,
           BrowserErrorType.validation_failed, BrowserErrorType.unexpected]:
    check(f"{et.value} not retryable", berr.is_retryable(et) is False)
check("retryable/never disjoint", berr.RETRYABLE_ERRORS.isdisjoint(berr.NEVER_RETRY_ERRORS))
summary("2. Error Types + Sets")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Error classification matrix
# ─────────────────────────────────────────────────────────────────────────────
section("3. Error Classification Matrix")
matrix = [
    ("Timeout 30000ms exceeded", BrowserErrorType.timeout, True),
    ("page.goto: Timeout exceeded", BrowserErrorType.timeout, True),
    ("navigating timed out", BrowserErrorType.timeout, True),
    ("element is detached from the DOM", BrowserErrorType.detached_node, True),
    ("node is detached", BrowserErrorType.detached_node, True),
    ("stale element handle reference", BrowserErrorType.stale_handle, True),
    ("rendering not ready, layout not stable", BrowserErrorType.temporary_rendering, True),
    ("temporarily unavailable", BrowserErrorType.temporary_rendering, True),
    ("waiting for selector '.x': no node found", BrowserErrorType.selector_not_found, False),
    ("locator resolved to 0 elements", BrowserErrorType.selector_not_found, False),
    ("could not find element", BrowserErrorType.selector_not_found, False),
    ("element is not attached", BrowserErrorType.selector_not_found, False),
    ("is not a valid selector", BrowserErrorType.invalid_selector, False),
    ("Unsupported selector engine", BrowserErrorType.invalid_selector, False),
    ("malformed selector", BrowserErrorType.invalid_selector, False),
    ("net::ERR_NAME_NOT_RESOLVED", BrowserErrorType.navigation_failed, False),
    ("net::ERR_CONNECTION_REFUSED", BrowserErrorType.navigation_failed, False),
    ("navigation failed because", BrowserErrorType.navigation_failed, False),
    ("download did not complete", BrowserErrorType.download_failed, False),
    ("download failed unexpectedly", BrowserErrorType.download_failed, False),
    ("set_input_files: no such file", BrowserErrorType.upload_failed, False),
    ("file chooser error", BrowserErrorType.upload_failed, False),
    ("403 Forbidden unauthorized", BrowserErrorType.authorization_error, False),
    ("permission denied", BrowserErrorType.authorization_error, False),
    ("validation failed: expected X", BrowserErrorType.validation_failed, False),
    ("some entirely unknown failure", BrowserErrorType.unexpected, False),
]
for msg, et, retry in matrix:
    c = berr.classify(Exception(msg))
    check(f"classify '{msg[:30]}' -> type", c.error_type == et)
    check(f"classify '{msg[:30]}' -> retryable", c.retryable == retry)
    check(f"classify '{msg[:30]}' -> message", c.message == msg)
# type-name timeout
class _TO(Exception): pass
_TO.__name__ = "TimeoutError"
check("TimeoutError name -> timeout", berr.classify(_TO("x")).error_type == BrowserErrorType.timeout)
# to_dict keys
d = berr.classify(Exception("Timeout exceeded")).to_dict()
for k in ["error_type", "retryable", "message", "original_type"]:
    check(f"classification.to_dict {k}", k in d)
check("classify_type explicit", berr.classify_type(BrowserErrorType.selector_not_found).original_type == "explicit")
summary("3. Error Classification Matrix")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Capabilities
# ─────────────────────────────────────────────────────────────────────────────
section("4. Capabilities")
check("11 actions", len(caps.SUPPORTED_ACTIONS) == 11)
for a in ["NAVIGATE", "CLICK", "TYPE", "WAIT", "EXTRACT_TEXT", "EXTRACT_HTML", "UPLOAD",
          "DOWNLOAD", "VALIDATE_URL", "VALIDATE_TEXT", "VALIDATE_EXISTS"]:
    check(f"action {a}", a in caps.SUPPORTED_ACTIONS)
check("priority 8", len(caps.RESOLUTION_PRIORITY) == 8)
check("priority order", caps.RESOLUTION_PRIORITY == ("selector", "testid", "aria_label", "role", "id", "name", "css", "xpath"))
for k in ["multiple_tabs", "new_windows", "page_refresh", "popup_handling", "iframe_basic"]:
    check(f"context {k} true", caps.SUPPORTED_CONTEXT[k] is True)
for k in ["cross_browser", "mobile", "persistent_profile", "drag_and_drop", "cloud_browser"]:
    check(f"unsupported {k} false", caps.UNSUPPORTED_YET[k] is False)
for k in ["download_detection", "download_completion", "file_path_reporting"]:
    check(f"download {k} true", caps.DOWNLOAD_SUPPORT[k] is True)
check("no cloud upload", caps.DOWNLOAD_SUPPORT["cloud_upload"] is False)
for k in ["input_file", "single_file", "multiple_files"]:
    check(f"upload {k} true", caps.UPLOAD_SUPPORT[k] is True)
check("no upload drag/drop", caps.UPLOAD_SUPPORT["drag_and_drop"] is False)
cp = caps.get_capabilities()
for k in ["adapter", "version", "browser", "supported_actions", "resolution_priority",
          "context", "unsupported_yet", "download", "upload", "ai_free"]:
    check(f"capabilities {k}", k in cp)
check("adapter playwright", cp["adapter"] == "playwright")
check("browser chromium", cp["browser"] == "chromium")
check("ai_free true", cp["ai_free"] is True)
summary("4. Capabilities")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Resolver — full priority matrix
# ─────────────────────────────────────────────────────────────────────────────
section("5. Resolver Priority")
page = FakePage()
order = ["selector", "testid", "aria_label", "role", "id", "name", "css", "xpath"]
params = {"selector": "s", "testid": "t", "aria_label": "a", "role": "r", "id": "i", "name": "n", "css": "c", "xpath": "x"}
work = dict(params)
for expected in order:
    r = res.resolve(page, work)
    check(f"priority picks {expected}", r.strategy == expected)
    del work[expected]
# strategy_for
for strat in order:
    check(f"strategy_for {strat}", res.strategy_for({strat: "v"}) == strat)
check("strategy_for none", res.strategy_for({"url": "x"}) is None)
# builder exact values
check("id -> #", res.resolve(page, {"id": "email"}).locator.key == ("locator", "#email"))
check("name -> attr", res.resolve(page, {"name": "q"}).locator.key == ("locator", '[name="q"]'))
check("css", res.resolve(page, {"css": ".b"}).locator.key == ("locator", ".b"))
check("xpath", res.resolve(page, {"xpath": "//a"}).locator.key == ("locator", "xpath=//a"))
check("testid builder", res.resolve(page, {"testid": "go"}).locator.key == ("testid", "go"))
check("aria builder", res.resolve(page, {"aria_label": "Name"}).locator.key == ("label", "Name"))
check("role builder", res.resolve(page, {"role": "button"}).locator.key == ("role", "button"))
try:
    res.resolve(page, {})
    check("no-params raises", False)
except res.ElementResolutionError:
    check("no-params raises", True)
check("empty value skipped", res.resolve(page, {"selector": "", "id": "x"}).strategy == "id")
summary("5. Resolver Priority")

# ─────────────────────────────────────────────────────────────────────────────
# 6. BrowserSession lifecycle
# ─────────────────────────────────────────────────────────────────────────────
section("6. BrowserSession Lifecycle")
s = _BS()
check("initial tab-0", s.active_tab_id == "tab-0")
check("tab count 1", s.tab_count() == 1)
live = FakePage(); s2 = _BS(live)
check("ensure_page live", s2.ensure_page() is live)
closedp = FakePage(closed=True); s3 = _BS(closedp)
check("ensure_page recreates", s3.ensure_page() is not closedp)
s4 = _BS()
tid = s4.register_tab(FakePage())
check("register tab id", tid == "tab-1")
check("tab count 2", s4.tab_count() == 2)
check("switch tab", s4.switch_tab(tid) is True)
check("active tab updated", s4.active_tab_id == tid)
check("switch unknown", s4.switch_tab("z") is False)
p5 = FakePage(); s5 = _BS(p5); s5.refresh()
check("refresh reloads", p5.reloaded is True)
s6 = _BS(); s6.close(); s6.close()
check("close idempotent", s6.closed is True)
check("browser closed", s6.browser.closed is True)
check("context closed", s6.context.closed is True)
check("playwright stopped", s6._playwright.stopped is True)
sd = _BS().to_dict()
for k in ["execution_id", "browser", "headless", "timeout_ms", "active_tab_id", "tab_count",
          "screenshots", "downloads", "closed", "created_at"]:
    check(f"session.to_dict {k}", k in sd)
summary("6. BrowserSession Lifecycle")

# ─────────────────────────────────────────────────────────────────────────────
# 7. BrowserSessionManager
# ─────────────────────────────────────────────────────────────────────────────
section("7. BrowserSessionManager")
mgr = BrowserSessionManager()
launches = {"n": 0}
def _fl(eid, headless=True): launches["n"] += 1; return _BS()
mgr._launch = _fl
sA = mgr.get_or_create("e1")
check("creates session", sA is not None)
check("active 1", mgr.active_count() == 1)
mgr.get_or_create("e1")
check("reuses (1 launch)", launches["n"] == 1)
check("get returns", mgr.get("e1") is sA)
check("get absent none", mgr.get("absent") is None)
check("session_info", mgr.session_info("e1") is not None)
check("session_info absent none", mgr.session_info("absent") is None)
check("close true", mgr.close("e1") is True)
check("get after close none", mgr.get("e1") is None)
check("close again false", mgr.close("e1") is False)
mgr.get_or_create("a"); mgr.get_or_create("b")
check("close_all 2", mgr.close_all() == 2)
for k in ["active_sessions", "total_launched", "total_closed", "timeout_ms"]:
    check(f"mgr.stats {k}", k in mgr.stats())
summary("7. BrowserSessionManager")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Adapter contract
# ─────────────────────────────────────────────────────────────────────────────
section("8. Adapter Contract")
a = _A(FakePage())
check("name playwright", a.name == "playwright")
for ct in CommandType:
    check(f"routing {ct.value}", ct in PlaywrightAdapter.COMMAND_ROUTING)
for meth in ["navigate", "click", "type", "wait", "extract", "validate", "upload", "download", "execute_custom"]:
    check(f"has method {meth}", hasattr(a, meth))
check("dispatch works", a.dispatch(_C(CommandType.navigate, {"url": "https://x.com"})).success is True)
summary("8. Adapter Contract")

# ─────────────────────────────────────────────────────────────────────────────
# 9-13. Adapter actions
# ─────────────────────────────────────────────────────────────────────────────
section("9. Adapter Actions")
# navigate
r = _A(FakePage()).navigate(_C(CommandType.navigate, {"url": "https://x.com"}))
check("navigate success", r.success is True)
check("navigate url", r.output["details"]["url"] == "https://x.com")
check("navigate validation true", r.validation_passed is True)
check("navigate has screenshot key", "screenshot_path" in r.output)
check("navigate attempts 1", r.output["attempts"] == 1)
p = FakePage(); _A(p).navigate(make_command(CommandType.navigate, "s", 1, "https://t.com"))
check("navigate uses target", p.url == "https://t.com")
# click
p = FakePage(); r = _A(p).click(_C(CommandType.click, {"testid": "go"}))
check("click success", r.success is True)
check("click strategy testid", r.output["details"]["strategy"] == "testid")
check("click recorded", ("click", ("testid", "go")) in p.events)
check("click priority", _A(FakePage()).click(_C(CommandType.click, {"selector": "#x", "testid": "t"})).output["details"]["strategy"] == "selector")
# type
p = FakePage(); r = _A(p).type(_C(CommandType.type, {"id": "e", "value": "hi@x.com"}))
check("type success", r.success is True)
check("type length", r.output["details"]["length"] == 8)
check("type filled", ("fill", "hi@x.com") in p.events)
check("type text alias", any(e == ("fill", "abc") for e in (lambda pp: (_A(pp).type(_C(CommandType.type, {"id": "x", "text": "abc"})), pp.events)[1])(FakePage())))
# wait
p = FakePage(); r = _A(p).wait(_C(CommandType.wait, {"ms": 200}))
check("wait duration", r.output["details"]["waited_for"] == "duration")
check("wait recorded", ("wait", 200) in p.events)
check("wait element", _A(FakePage()).wait(_C(CommandType.wait, {"id": "x", "timeout_ms": 100})).output["details"]["waited_for"] == "element")
summary("9. Adapter Actions")

section("10. Adapter Extract")
r = _A(FakePage(element_text="HELLO")).extract(_C(CommandType.extract, {"selector": ".m", "mode": "text"}))
check("extract success", r.success is True)
check("extract text length", r.output["details"]["content_length"] == 5)
check("extract mode text", r.output["details"]["mode"] == "text")
r = _A(FakePage(element_html="<b>x</b>")).extract(_C(CommandType.extract, {"selector": ".m", "mode": "html"}))
check("extract html mode", r.output["details"]["mode"] == "html")
r = _A(FakePage(body="page body words")).extract(_C(CommandType.extract, {"mode": "text"}))
check("extract page strategy", r.output["details"]["strategy"] == "page")
check("extract preview", "page body words" in r.output["details"]["content_preview"])
summary("10. Adapter Extract")

section("11. Adapter Validate")
r = _A(FakePage(url="https://example.com/abc")).validate(_C(CommandType.validate, {"expected_url": "example.com"}, strategy="URL_MATCH"))
check("url match pass", r.validation_passed is True)
check("url match success true", r.success is True)
r = _A(FakePage(url="https://example.com/abc")).validate(_C(CommandType.validate, {"expected_url": "nope.com"}, strategy="URL_MATCH"))
check("url match fail", r.validation_passed is False)
check("url mismatch still dispatched", r.success is True)
r = _A(FakePage(body="answer is 42")).validate(_C(CommandType.validate, {"expected_text": "answer"}, strategy="TEXT_MATCH"))
check("text match pass", r.validation_passed is True)
r = _A(FakePage(body="nothing")).validate(_C(CommandType.validate, {"expected_text": "missing"}, strategy="TEXT_MATCH"))
check("text match fail", r.validation_passed is False)
r = _A(FakePage(element_count=2)).validate(_C(CommandType.validate, {"selector": ".x"}, strategy="DOM_PRESENCE"))
check("exists pass", r.validation_passed is True)
r = _A(FakePage(element_count=0)).validate(_C(CommandType.validate, {"selector": ".x"}, strategy="VALIDATE_EXISTS"))
check("exists fail", r.validation_passed is False)
# validation_strategy aliases
check("VALIDATE_URL alias", _A(FakePage(url="https://a.com")).validate(_C(CommandType.validate, {"expected_url": "a.com"}, strategy="VALIDATE_URL")).validation_passed is True)
check("VALIDATE_TEXT alias", _A(FakePage(body="hello")).validate(_C(CommandType.validate, {"expected_text": "hello"}, strategy="VALIDATE_TEXT")).validation_passed is True)
summary("11. Adapter Validate")

section("12. Adapter Upload/Download/Custom")
p = FakePage(); r = _A(p).upload(_C(CommandType.upload, {"selector": "input", "file": "/a.txt"}))
check("upload single success", r.success is True)
check("upload count 1", r.output["details"]["count"] == 1)
check("upload recorded", ("upload", ["/a.txt"]) in p.events)
r = _A(FakePage()).upload(_C(CommandType.upload, {"selector": "input", "files": ["/a", "/b"]}))
check("upload multiple", r.output["details"]["count"] == 2)
r = _A(FakePage()).upload(_C(CommandType.upload, {"selector": "input"}))
check("upload no files fails", r.success is False)
check("upload error type", r.output["error"]["error_type"] == "UPLOAD_FAILED")
r = _A(FakePage(download_path="/tmp/r.csv")).download(_C(CommandType.download, {"testid": "dl"}))
check("download success", r.success is True)
check("download path", r.output["details"]["download_path"] == "/tmp/r.csv")
p = FakePage(); r = _A(p).execute_custom(_C(CommandType.custom, {"action": "scroll", "dy": 100}))
check("custom scroll success", r.success is True)
check("custom scroll eval", any(e[0] == "eval" for e in p.events))
p = FakePage(); _A(p).execute_custom(_C(CommandType.custom, {"action": "refresh"}))
check("custom refresh", p.reloaded is True)
check("custom noop", _A(FakePage()).execute_custom(_C(CommandType.custom, {})).success is True)
summary("12. Adapter Upload/Download/Custom")

# ─────────────────────────────────────────────────────────────────────────────
# 13. Retry verification
# ─────────────────────────────────────────────────────────────────────────────
section("13. Retry Verification")
# transient retried then success
r = _A(FlakyPage(Exception("Timeout exceeded"), 2), RetryConfig(max_retries=2)).navigate(_C(CommandType.navigate, {"url": "https://x.com"}))
check("transient retried success", r.success is True)
check("transient 3 attempts", r.output["attempts"] == 3)
# transient exhausted -> bounded fail
r = _A(FlakyPage(Exception("Timeout exceeded"), 9), RetryConfig(max_retries=2)).navigate(_C(CommandType.navigate, {"url": "https://x.com"}))
check("transient exhausted fail", r.success is False)
check("transient bounded 3", r.output["attempts"] == 3)
check("transient error type", r.output["error"]["error_type"] == "TIMEOUT")
# terminal never retried
for msg, et in [("waiting for selector: no node found", "SELECTOR_NOT_FOUND"),
                ("is not a valid selector", "INVALID_SELECTOR"),
                ("403 unauthorized", "AUTHORIZATION_ERROR")]:
    r = _A(FailLocPage(Exception(msg)), RetryConfig(max_retries=2)).click(_C(CommandType.click, {"selector": ".x"}))
    check(f"terminal {et} not retried (1 attempt)", r.output["attempts"] == 1)
    check(f"terminal {et} fails", r.success is False)
    check(f"terminal {et} error type", r.output["error"]["error_type"] == et)
    check(f"terminal {et} not retryable", r.output["error"]["retryable"] is False)
# zero-retry config: one attempt even for transient
r = _A(FlakyPage(Exception("Timeout exceeded"), 9), RetryConfig(max_retries=0)).navigate(_C(CommandType.navigate, {"url": "u"}))
check("zero-retry one attempt", r.output["attempts"] == 1)
# screenshot + error in output on failure
r = _A(FailLocPage(Exception("no node found"))).click(_C(CommandType.click, {"selector": ".x"}))
check("failure has error", "error" in r.output)
check("failure has screenshot", r.output["screenshot_path"] is not None)
check("failure validation false", r.validation_passed is False)
summary("13. Retry Verification")

# ─────────────────────────────────────────────────────────────────────────────
# 14. Gateway-unchanged execution verification (fake browser)
# ─────────────────────────────────────────────────────────────────────────────
section("14. Execution Verification (gateway unchanged)")
def _run_fake(plan, page):
    ad = PlaywrightAdapter(session_manager=FakeMgr(page))
    rec = gateway.start(plan.plan_id, auto_run=False, adapter=ad, retry_config=RetryConfig(max_retries=0))
    ad.execution_id = rec.execution_id
    return gateway.resume(rec.execution_id, adapter=ad)
_reset()
plan = _ready_plan()
rec = _run_fake(plan, FakePage(body="the objective satisfied now"))
check("execution completed", rec.state == ExecutionState.completed)
check("adapter_name playwright", rec.adapter_name == "playwright")
check("3 steps", rec.completed_steps == 3)
check("command types", [s.command_type for s in rec.step_executions] == ["NAVIGATE", "EXTRACT", "VALIDATE"])
check("audit 3", audit.count_for_execution(rec.execution_id) == 3)
check("analytics completed", ganal.get_analytics()["executions_completed"] == 1)
# validation failure path
_reset()
plan = _ready_plan()
rec = _run_fake(plan, FakePage(body="unrelated content"))
check("validation failure -> failed", rec.state == ExecutionState.failed)
check("validate step failed", rec.step_executions[-1].validation_passed is False)
check("rollback simulated", len(rec.rollback_history) >= 1)
# revoked auth blocks
_reset()
plan = _ready_plan()
auth_reg.revoke(plan.authorization_id, reason="t")
from app.execution_gateway.engine import GatewayError
try:
    gateway.start(plan.plan_id, auto_run=False)
    check("revoked blocks start", False)
except GatewayError:
    check("revoked blocks start", True)
summary("14. Execution Verification (gateway unchanged)")

# ─────────────────────────────────────────────────────────────────────────────
# 15. REST endpoints (additive, non-breaking)
# ─────────────────────────────────────────────────────────────────────────────
section("15. REST Endpoints")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
routes = {r.path for r in app.routes}
check("session route", "/gateway/browser/session/{execution_id}" in routes)
check("screenshot route", "/gateway/browser/screenshot/{execution_id}" in routes)
# existing gateway routes unchanged (no breaking changes)
for p in ["/gateway/start/{plan_id}", "/gateway/pause/{execution_id}", "/gateway/resume/{execution_id}",
          "/gateway/abort/{execution_id}", "/gateway/status/{execution_id}", "/gateway/history/{execution_id}",
          "/gateway/analytics", "/gateway/inspect/{execution_id}"]:
    check(f"existing route preserved {p}", p in routes)
check("session 404 when none", client.get("/gateway/browser/session/no-such").status_code == 404)
check("screenshot 404 when none", client.get("/gateway/browser/screenshot/no-such").status_code == 404)
summary("15. REST Endpoints")

# ─────────────────────────────────────────────────────────────────────────────
# 16. Static safety verification
# ─────────────────────────────────────────────────────────────────────────────
section("16. Static Safety Verification")
# Forbidden: OTHER automation stacks, vision/OCR/LLM, self-healing. Playwright IS allowed.
# Real-usage signals only (imports / calls). The "no self-healing / no Vision / no OCR"
# CONSTRAINT docstrings legitimately name these — so we forbid importing/calling them,
# never the bare prose substring.
forbidden = [
    "import selenium", "from selenium", "selenium.webdriver",
    "import pyppeteer", "from pyppeteer", "puppeteer.launch",
    "import cv2", "cv2.imread", "cv2.imshow", "import pytesseract", "pytesseract.",
    "import easyocr", "easyocr.reader",
    "import openai", "from openai", "openai.", "import anthropic", "from anthropic",
    "import torch", "import transformers", "self_heal(", "def self_heal",
    "vision_model(", ".ocr(", "call_llm(", ".generate_text(",
]
browser_sources = list(pathlib.Path("app/execution_gateway/browser").rglob("*.py"))
check("browser pkg >= 7 modules", len(browser_sources) >= 7)
for src in browser_sources:
    text = src.read_text(encoding="utf-8", errors="replace").lower()
    for fb in forbidden:
        check(f"NO '{fb}' in {src.name}", fb.lower() not in text)
# Playwright imported LAZILY only in session.py (inside a method, indented)
session_src = pathlib.Path("app/execution_gateway/browser/session.py").read_text(encoding="utf-8")
check("session imports playwright lazily", "        from playwright.sync_api import sync_playwright" in session_src)
check("session no top-level playwright import",
      not any(l.startswith("from playwright") or l.startswith("import playwright")
              for l in session_src.splitlines()))
# adapter does NOT import playwright at all (talks to session manager)
adapter_src = pathlib.Path("app/execution_gateway/browser/playwright_adapter.py").read_text(encoding="utf-8")
check("adapter never imports playwright", "import playwright" not in adapter_src and "from playwright" not in adapter_src)
# no AI / self-healing in adapter
check("adapter ai-free", "self_heal" not in adapter_src.lower() and "vision" not in adapter_src.lower())
summary("16. Static Safety Verification")

# ─────────────────────────────────────────────────────────────────────────────
# 17. Phase B unchanged verification
# ─────────────────────────────────────────────────────────────────────────────
section("17. Phase B Unchanged Verification")
# The gateway/dispatcher/runner/engines still exist and behave as Phase B.
from app.execution_gateway import dispatcher as edisp, runner as erunner, validation as eval_eng
from app.execution_gateway import retry_engine, rollback_engine
from app.execution_gateway.mock_adapter import MockBrowserAdapter
check("dispatcher import", edisp is not None)
check("runner import", erunner is not None)
check("validation import", eval_eng is not None)
check("retry engine import", retry_engine is not None)
check("rollback engine import", rollback_engine is not None)
check("mock adapter still exists", MockBrowserAdapter().name == "mock")
# mock still works through the gateway (Phase B path intact)
_reset()
plan = _ready_plan(mission="m-mock")
rec = gateway.start(plan.plan_id)   # default mock adapter, auto_run
check("mock path completes", rec.state == ExecutionState.completed)
check("mock adapter name", rec.adapter_name == "mock")
# retry engine signature unchanged
check("retry engine should_retry", retry_engine.should_retry(1, RetryConfig(max_retries=2), dispatch_failed=True, validation_failed=False) is True)
# dispatcher mapping unchanged (8 action types)
check("dispatcher action map 8", len(edisp.ACTION_TO_COMMAND) == 8)
summary("17. Phase B Unchanged Verification")

# ─────────────────────────────────────────────────────────────────────────────
# 18a. classify_type for every error type
# ─────────────────────────────────────────────────────────────────────────────
section("18a. classify_type — all types")
for et in BrowserErrorType:
    c = berr.classify_type(et, f"msg for {et.value}")
    check(f"classify_type {et.value} type", c.error_type == et)
    check(f"classify_type {et.value} retryable", c.retryable == berr.is_retryable(et))
    check(f"classify_type {et.value} original explicit", c.original_type == "explicit")
    check(f"classify_type {et.value} message", c.message == f"msg for {et.value}")
    cd = c.to_dict()
    check(f"classify_type {et.value} dict type", cd["error_type"] == et.value)
    check(f"classify_type {et.value} dict retryable", cd["retryable"] == berr.is_retryable(et))
summary("18a. classify_type — all types")

# ─────────────────────────────────────────────────────────────────────────────
# 18b. Extended classification matrix
# ─────────────────────────────────────────────────────────────────────────────
section("18b. Extended Classification")
ext = [
    ("Timeout 5000ms exceeded waiting", BrowserErrorType.timeout, True),
    ("operation timed out", BrowserErrorType.timeout, True),
    ("iframe node is detached", BrowserErrorType.detached_node, True),
    ("the element is detached from document", BrowserErrorType.detached_node, True),
    ("stale handle to element", BrowserErrorType.stale_handle, True),
    ("element handle is stale now", BrowserErrorType.stale_handle, True),
    ("layout not stable yet", BrowserErrorType.temporary_rendering, True),
    ("page rendering not ready", BrowserErrorType.temporary_rendering, True),
    ("Element is temporarily covered", BrowserErrorType.temporary_rendering, True),
    ("waiting for selector \"#x\"", BrowserErrorType.selector_not_found, False),
    ("no node found for selector", BrowserErrorType.selector_not_found, False),
    ("locator resolved to 0 elements found", BrowserErrorType.selector_not_found, False),
    ("could not find the button", BrowserErrorType.selector_not_found, False),
    ("xyz is not a valid selector expression", BrowserErrorType.invalid_selector, False),
    ("syntaxerror in selector", BrowserErrorType.invalid_selector, False),
    ("unsupported selector strategy", BrowserErrorType.invalid_selector, False),
    ("net::ERR_ABORTED at navigation", BrowserErrorType.navigation_failed, False),
    ("err_connection_timed... navigation failed", BrowserErrorType.navigation_failed, False),
    ("download did not start", BrowserErrorType.download_failed, False),
    ("the download error occurred", BrowserErrorType.download_failed, False),
    ("upload failed for input", BrowserErrorType.upload_failed, False),
    ("set_input_files raised", BrowserErrorType.upload_failed, False),
    ("request unauthorized 401", BrowserErrorType.authorization_error, False),
    ("access forbidden by policy", BrowserErrorType.authorization_error, False),
    ("assertion failed: expected value", BrowserErrorType.validation_failed, False),
    ("completely novel issue", BrowserErrorType.unexpected, False),
    ("strange internal browser glitch", BrowserErrorType.unexpected, False),
]
for msg, et, retry in ext:
    c = berr.classify(Exception(msg))
    check(f"ext classify '{msg[:28]}' type", c.error_type == et)
    check(f"ext classify '{msg[:28]}' retry", c.retryable == retry)
    check(f"ext classify '{msg[:28]}' in never/retry set",
          (et in berr.RETRYABLE_ERRORS) == retry)
summary("18b. Extended Classification")

# ─────────────────────────────────────────────────────────────────────────────
# 18c. Resolver builder matrix (8 strategies x many values)
# ─────────────────────────────────────────────────────────────────────────────
section("18c. Resolver Builder Matrix")
values = ["a", "btn1", "submit-go", "field_2", "x.y", "abc123", "Name", "role-x", "q", "main"]
pg = FakePage()
for v in values:
    cases = {
        "selector": ("locator", v),
        "testid":   ("testid", v),
        "aria_label": ("label", v),
        "role":     ("role", v),
        "id":       ("locator", f"#{v}"),
        "name":     ("locator", f'[name="{v}"]'),
        "css":      ("locator", v),
        "xpath":    ("locator", f"xpath={v}"),
    }
    for strat, expected_key in cases.items():
        r = res.resolve(pg, {strat: v})
        check(f"resolve {strat}={v} strategy", r.strategy == strat)
        check(f"resolve {strat}={v} key", r.locator.key == expected_key)
        check(f"resolve {strat}={v} value", r.value == v)
summary("18c. Resolver Builder Matrix")

# ─────────────────────────────────────────────────────────────────────────────
# 18d. AdapterResult shape for all 9 methods
# ─────────────────────────────────────────────────────────────────────────────
section("18d. AdapterResult Shape")
method_cases = [
    ("navigate",       {"url": "https://x.com"}, "NONE"),
    ("click",          {"selector": ".b"}, "NONE"),
    ("type",           {"id": "e", "value": "hi"}, "NONE"),
    ("wait",           {"ms": 10}, "NONE"),
    ("extract",        {"selector": ".m", "mode": "text"}, "NONE"),
    ("validate",       {"selector": ".x"}, "DOM_PRESENCE"),
    ("upload",         {"selector": "input", "file": "/a"}, "NONE"),
    ("download",       {"testid": "dl"}, "NONE"),
    ("execute_custom", {"action": "noop"}, "NONE"),
]
ctype_for = {"navigate": CommandType.navigate, "click": CommandType.click, "type": CommandType.type,
             "wait": CommandType.wait, "extract": CommandType.extract, "validate": CommandType.validate,
             "upload": CommandType.upload, "download": CommandType.download, "execute_custom": CommandType.custom}
for mname, params, strat in method_cases:
    ad = _A(FakePage())
    result = getattr(ad, mname)(_C(ctype_for[mname], params, strategy=strat))
    check(f"{mname} success bool", isinstance(result.success, bool))
    check(f"{mname} success true", result.success is True)
    check(f"{mname} duration >= 0", result.duration_ms >= 0.0)
    check(f"{mname} logs list", isinstance(result.logs, list))
    check(f"{mname} output dict", isinstance(result.output, dict))
    check(f"{mname} validation bool", isinstance(result.validation_passed, bool))
    check(f"{mname} message str", isinstance(result.message, str))
    check(f"{mname} output details", "details" in result.output)
    check(f"{mname} output attempts", "attempts" in result.output)
    check(f"{mname} output phase", "phase" in result.output)
    check(f"{mname} output screenshot key", "screenshot_path" in result.output)
summary("18d. AdapterResult Shape")

# ─────────────────────────────────────────────────────────────────────────────
# 18e. Command routing to adapter methods
# ─────────────────────────────────────────────────────────────────────────────
section("18e. Command Routing")
routing_expected = {
    CommandType.navigate: "navigate", CommandType.click: "click", CommandType.type: "type",
    CommandType.wait: "wait", CommandType.extract: "extract", CommandType.validate: "validate",
    CommandType.upload: "upload", CommandType.download: "download", CommandType.custom: "execute_custom",
}
for ct, mname in routing_expected.items():
    check(f"routing {ct.value} -> {mname}", PlaywrightAdapter.COMMAND_ROUTING[ct] == mname)
summary("18e. Command Routing")

# ─────────────────────────────────────────────────────────────────────────────
# 18f. Validate matrix (url / text / exists)
# ─────────────────────────────────────────────────────────────────────────────
section("18f. Validate Matrix")
url_cases = [("https://a.com/x", "a.com", True), ("https://a.com/x", "x", True),
             ("https://a.com/x", "b.com", False), ("https://a.com/x", "", False),
             ("https://shop.io/p?id=3", "shop.io", True), ("https://shop.io/p", "id=3", False)]
for url, exp, ok in url_cases:
    r = _A(FakePage(url=url)).validate(_C(CommandType.validate, {"expected_url": exp}, strategy="URL_MATCH"))
    check(f"url '{url}' vs '{exp}'", r.validation_passed is ok)
    check(f"url '{url}' dispatch ok", r.success is True)
text_cases = [("hello world", "hello", True), ("hello world", "world", True),
              ("hello world", "bye", False), ("data 42 here", "42", True),
              ("nothing", "", False), ("Multi Word Title", "Word", True)]
for body, exp, ok in text_cases:
    r = _A(FakePage(body=body)).validate(_C(CommandType.validate, {"expected_text": exp}, strategy="TEXT_MATCH"))
    check(f"text '{body}' vs '{exp}'", r.validation_passed is ok)
exists_cases = [(0, False), (1, True), (2, True), (5, True)]
for cnt, ok in exists_cases:
    r = _A(FakePage(element_count=cnt)).validate(_C(CommandType.validate, {"selector": ".x"}, strategy="VALIDATE_EXISTS"))
    check(f"exists count {cnt}", r.validation_passed is ok)
summary("18f. Validate Matrix")

# ─────────────────────────────────────────────────────────────────────────────
# 18g. Retry matrix per error type
# ─────────────────────────────────────────────────────────────────────────────
section("18g. Retry Matrix Per Type")
type_msg = {
    BrowserErrorType.timeout: "Timeout exceeded",
    BrowserErrorType.detached_node: "element is detached",
    BrowserErrorType.stale_handle: "stale element handle",
    BrowserErrorType.temporary_rendering: "rendering not ready",
    BrowserErrorType.selector_not_found: "no node found",
    BrowserErrorType.invalid_selector: "is not a valid selector",
    BrowserErrorType.navigation_failed: "net::ERR_NAME_NOT_RESOLVED",
    BrowserErrorType.download_failed: "download did not complete",
    BrowserErrorType.upload_failed: "upload failed",
    BrowserErrorType.authorization_error: "forbidden",
    BrowserErrorType.validation_failed: "assertion failed expected",
    BrowserErrorType.unexpected: "weird glitch zzz",
}
for et, msg in type_msg.items():
    # click always raises this error; retryable -> 3 attempts, terminal -> 1 attempt
    r = _A(FailLocPage(Exception(msg)), RetryConfig(max_retries=2)).click(_C(CommandType.click, {"selector": ".x"}))
    expected_attempts = 3 if berr.is_retryable(et) else 1
    check(f"retry {et.value} attempts", r.output["attempts"] == expected_attempts)
    check(f"retry {et.value} failed", r.success is False)
    check(f"retry {et.value} error type", r.output["error"]["error_type"] == et.value)
    check(f"retry {et.value} retryable flag", r.output["error"]["retryable"] == berr.is_retryable(et))
summary("18g. Retry Matrix Per Type")

# ─────────────────────────────────────────────────────────────────────────────
# 18h. Capabilities exhaustive
# ─────────────────────────────────────────────────────────────────────────────
section("18h. Capabilities Exhaustive")
cp = caps.get_capabilities()
for a in caps.SUPPORTED_ACTIONS:
    check(f"cap action listed {a}", a in cp["supported_actions"])
for p in caps.RESOLUTION_PRIORITY:
    check(f"cap priority listed {p}", p in cp["resolution_priority"])
for k, v in caps.SUPPORTED_CONTEXT.items():
    check(f"cap context {k}", cp["context"][k] == v)
for k, v in caps.UNSUPPORTED_YET.items():
    check(f"cap unsupported {k}", cp["unsupported_yet"][k] == v)
for k, v in caps.DOWNLOAD_SUPPORT.items():
    check(f"cap download {k}", cp["download"][k] == v)
for k, v in caps.UPLOAD_SUPPORT.items():
    check(f"cap upload {k}", cp["upload"][k] == v)
check("cap headless default", cp["headless_default"] is True)
check("cap version 1.0", cp["version"] == "1.0")
summary("18h. Capabilities Exhaustive")

# ─────────────────────────────────────────────────────────────────────────────
# 18i. Gateway-unchanged repeated runs (fake browser)
# ─────────────────────────────────────────────────────────────────────────────
section("18i. Gateway Unchanged — Repeated Runs")
for i in range(12):
    _reset()
    plan = _ready_plan(mission=f"m-rep-{i}")
    rec = _run_fake(plan, FakePage(body="objective satisfied yes"))
    check(f"run {i} completed", rec.state == ExecutionState.completed)
    check(f"run {i} playwright", rec.adapter_name == "playwright")
    check(f"run {i} 3 steps", rec.completed_steps == 3)
    check(f"run {i} audit", audit.count_for_execution(rec.execution_id) == 3)
summary("18i. Gateway Unchanged — Repeated Runs")

# ─────────────────────────────────────────────────────────────────────────────
# 18j. Action parameter variations
# ─────────────────────────────────────────────────────────────────────────────
section("18j. Action Parameter Variations")
# navigate wait_until variations
for wu in ["load", "domcontentloaded", "networkidle"]:
    r = _A(FakePage()).navigate(_C(CommandType.navigate, {"url": "https://x.com", "wait_until": wu}))
    check(f"navigate wait_until {wu}", r.output["details"]["wait_until"] == wu)
# click across all resolution strategies
for strat in ["selector", "testid", "aria_label", "role", "id", "name", "css", "xpath"]:
    r = _A(FakePage()).click(_C(CommandType.click, {strat: "v"}))
    check(f"click via {strat} success", r.success is True)
    check(f"click via {strat} strategy", r.output["details"]["strategy"] == strat)
# type lengths
for txt in ["", "a", "hello", "a very long input string here"]:
    r = _A(FakePage()).type(_C(CommandType.type, {"id": "e", "value": txt}))
    check(f"type len {len(txt)}", r.output["details"]["length"] == len(txt))
# extract modes via element + page
for mode in ["text", "html"]:
    r = _A(FakePage()).extract(_C(CommandType.extract, {"selector": ".m", "mode": mode}))
    check(f"extract element {mode}", r.output["details"]["mode"] == mode)
    r2 = _A(FakePage()).extract(_C(CommandType.extract, {"mode": mode}))
    check(f"extract page {mode} strategy", r2.output["details"]["strategy"] == "page")
# upload counts
for files in [["/a"], ["/a", "/b"], ["/a", "/b", "/c"]]:
    r = _A(FakePage()).upload(_C(CommandType.upload, {"selector": "input", "files": files}))
    check(f"upload {len(files)} files", r.output["details"]["count"] == len(files))
# wait durations
for ms in [10, 100, 500, 1000]:
    p = FakePage(); _A(p).wait(_C(CommandType.wait, {"ms": ms}))
    check(f"wait {ms}", ("wait", ms) in p.events)
# custom actions
for act in ["scroll", "refresh", "noop", "unknownthing"]:
    r = _A(FakePage()).execute_custom(_C(CommandType.custom, {"action": act}))
    check(f"custom {act} success", r.success is True)
summary("18j. Action Parameter Variations")

# ─────────────────────────────────────────────────────────────────────────────
# 19. Real browser execution verification (bonus; guarded)
# ─────────────────────────────────────────────────────────────────────────────
section("19. Real Browser Execution")
chromium_ok = False
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _b = _p.chromium.launch(headless=True); _b.close()
    chromium_ok = True
except Exception as _e:
    print(f"  (chromium unavailable — real-browser checks skipped: {str(_e)[:60]})")

if chromium_ok:
    import socket, threading, http.server, socketserver
    HTML = b"<!doctype html><html><head><title>V</title></head><body><h1 id='h'>Welcome RB</h1><p data-testid='p'>content</p></body></html>"
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML))); self.end_headers(); self.wfile.write(HTML)
        def log_message(self, *a): pass
    _s = socket.socket(); _s.bind(("127.0.0.1", 0)); _port = _s.getsockname()[1]; _s.close()
    _httpd = socketserver.TCPServer(("127.0.0.1", _port), _H)
    threading.Thread(target=_httpd.serve_forever, daemon=True).start()
    URL = f"http://127.0.0.1:{_port}/"
    from app.execution_gateway.browser import run as brun, session as bs
    _reset(); bs._reset_for_testing()
    auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600, mission_id="m-rb", task_id="t-1")
    auth_reg.add(auth); mission_store.put(Mission("m-rb", "t", "obj", MissionState.active, task_ids=["t-1"]))
    steps = [
        make_step(1, ActionType.navigate, TargetType.url, URL, parameters={"url": URL}),
        make_step(2, ActionType.extract, TargetType.region, "h", parameters={"id": "h", "mode": "text"}),
        make_step(3, ActionType.validate, TargetType.element, "p", parameters={"testid": "p"}, validation_strategy=ValidationStrategy.dom_presence),
        make_step(4, ActionType.validate, TargetType.page, "text", parameters={"expected_text": "Welcome RB"}, expected_result="Welcome RB", validation_strategy=ValidationStrategy.text_match),
    ]
    plan = make_plan(auth.authorization_id, mission_id="m-rb", task_id="t-1", created_at=time.time(),
                     execution_mode=ExecutionMode.sequential, steps=steps, estimated_duration_ms=0,
                     rollback_supported=True, confidence=0.9)
    plan_reg.add(plan); set_status(plan.plan_id, PlanStatus.ready)
    rec = brun.execute_plan_with_browser(plan.plan_id, headless=True)
    check("real exec completed", rec.state == ExecutionState.completed)
    check("real 4 steps", rec.completed_steps == 4)
    check("real adapter playwright", rec.adapter_name == "playwright")
    check("real navigate ok", rec.step_executions[0].outcome.value == "SUCCESS")
    check("real extract content", "Welcome RB" in rec.step_executions[1].output["details"]["content_preview"])
    check("real dom presence pass", rec.step_executions[2].validation_passed is True)
    check("real text match pass", rec.step_executions[3].validation_passed is True)
    check("real audit 4", audit.count_for_execution(rec.execution_id) == 4)
    # missing element terminal, not retried, bounded
    _reset(); bs._reset_for_testing()
    auth_reg.add(auth); mission_store.put(Mission("m-rb2", "t", "obj", MissionState.active, task_ids=["t-1"]))
    auth2 = make_authorization("ctr-2", True, "ok", "HIGH", time.time() + 3600, mission_id="m-rb2", task_id="t-1")
    auth_reg.add(auth2)
    steps2 = [
        make_step(1, ActionType.navigate, TargetType.url, URL, parameters={"url": URL}),
        make_step(2, ActionType.click, TargetType.element, "ghost", parameters={"selector": "#nope", "timeout_ms": 700}),
    ]
    plan2 = make_plan(auth2.authorization_id, mission_id="m-rb2", task_id="t-1", created_at=time.time(),
                      execution_mode=ExecutionMode.sequential, steps=steps2, estimated_duration_ms=0,
                      rollback_supported=True, confidence=0.9)
    plan_reg.add(plan2); set_status(plan2.plan_id, PlanStatus.ready)
    rec2 = brun.execute_plan_with_browser(plan2.plan_id, headless=True)
    check("real missing-element failed", rec2.state == ExecutionState.failed)
    check("real nav before failure ok", rec2.step_executions[0].outcome.value == "SUCCESS")
    check("real rollback simulated", len(rec2.rollback_history) >= 1)
    _httpd.shutdown(); bs._reset_for_testing()
summary("18. Real Browser Execution")

# ── Final tally ───────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"PHASE C VALIDATION: {PASS}/{total} checks passed")
print("  ALL CHECKS PASSED" if FAIL == 0 else f"  FAILURES: {FAIL}")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
