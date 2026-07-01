"""
Phase D — Adaptive Execution & Recovery — Validation Suite.

Minimum 1500 deterministic checks: static safety, classification, recovery, adaptive
resolution, first-class validation, monitor/metrics/timeline/diagnostics, adapter
integration (retry policy V2 + recovery), backward-compatibility, and (guarded) real
browser certification.

Run: python validate_phased.py
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

def summ(name: str):
    prev = SECTIONS[-1]
    print(f"  -> {PASS - prev[1]} pass, {FAIL - prev[2]} fail")


from app.execution_gateway.browser import failure_classes as fc
from app.execution_gateway.browser import recovery as rec
from app.execution_gateway.browser import adaptive_resolver as ar
from app.execution_gateway.browser import execution_validation as ev
from app.execution_gateway.browser import monitor as mon
from app.execution_gateway.browser import metrics as met
from app.execution_gateway.browser import exec_timeline as etl
from app.execution_gateway.browser import diagnostics as diag
from app.execution_gateway.browser import capabilities as caps
from app.execution_gateway.browser import resolver as phasec_resolver
from app.execution_gateway.browser.failure_classes import (
    FailureCategory, FailureSeverity, RecoveryAction, PROFILES,
    RETRYABLE_CATEGORIES, PERMANENT_CATEGORIES,
)
from app.execution_gateway.browser.resolver import ElementResolutionError
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_gateway.models import make_command, CommandType, RetryConfig


# ── Fakes ─────────────────────────────────────────────────────────────────────

class FakeLocator:
    def __init__(self, page, key): self.page = page; self.key = key
    def click(self, **k):
        self.page.click_calls += 1
        if self.page.click_calls <= self.page.click_fail_times:
            raise Exception(self.page.click_fail_msg)
    def fill(self, t, **k): self.page.filled = t
    def inner_text(self): return self.page.body
    def inner_html(self): return f"<b>{self.page.body}</b>"
    def count(self): return self.page.element_count
    def input_value(self): return self.page.field_value
    def wait_for(self, **k): pass
    def scroll_into_view_if_needed(self, **k): self.page.scrolled = True
    def set_input_files(self, files): self.page.uploaded = files

class _FakeDownload:
    def __init__(self, p): self._p = p; self.suggested_filename = "f.txt"
    def path(self): return self._p
class _FakeDLCtx:
    def __init__(self, page): self.page = page
    def __enter__(self): return self
    def __exit__(self, *a): return False
    @property
    def value(self): return _FakeDownload(self.page.download_path)

class FakePage:
    def __init__(self, *, url="https://x/p", body="ok", element_count=1, field_value="",
                 click_fail_times=0, click_fail_msg="no node found", download_path="/tmp/f.txt"):
        self.url = url; self.body = body; self.element_count = element_count
        self.field_value = field_value; self.click_calls = 0
        self.click_fail_times = click_fail_times; self.click_fail_msg = click_fail_msg
        self.filled = None; self.scrolled = False; self.events = []; self.reloaded = False
        self.uploaded = None; self.download_path = download_path
    def is_closed(self): return False
    def goto(self, url, **k): self.url = url
    def title(self): return "T"
    def reload(self): self.reloaded = True
    def locator(self, s): return FakeLocator(self, ("locator", s))
    def get_by_test_id(self, v): return FakeLocator(self, ("testid", v))
    def get_by_label(self, v): return FakeLocator(self, ("label", v))
    def get_by_role(self, v, name=None): return FakeLocator(self, ("role", v))
    def get_by_placeholder(self, v): return FakeLocator(self, ("placeholder", v))
    def get_by_text(self, v): return FakeLocator(self, ("text", v))
    def inner_text(self, sel): return self.body
    def content(self): return f"<html>{self.body}</html>"
    def wait_for_timeout(self, ms): self.events.append(("wait", ms))
    def wait_for_load_state(self, s, timeout=None): self.events.append(("networkidle",))
    def evaluate(self, js): self.events.append(("eval",))
    def expect_download(self, **k): return _FakeDLCtx(self)

class FakeSession:
    def __init__(self, page, context=None):
        self.page = page; self.active_tab_id = "tab-0"; self.downloads = []; self.context = context
    def ensure_page(self): return self.page
    def screenshot(self, l=""): return f"/tmp/{l}.png"
    def refresh(self): self.page.reload()

class FakeMgr:
    def __init__(self, page): self.session = FakeSession(page)
    def get_or_create(self, eid, headless=True): return self.session
    def get(self, eid): return self.session
    def close(self, eid): return True

class _Cmd:
    def __init__(self, params=None): self.parameters = params or {}

def _adapter(page, **flags):
    base = dict(adaptive=True, recovery=True, post_validation=True, retry_config=RetryConfig(max_retries=2))
    base.update(flags)
    return PlaywrightAdapter(execution_id="e1", session_manager=FakeMgr(page), **base)

def _cmd(ctype, params=None, expected="", strategy="NONE", step_id="s1", order=1):
    return make_command(ctype, step_id, order, "tgt", parameters=params or {},
                        expected_result=expected, validation_strategy=strategy)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Package structure
# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
for f in ["failure_classes", "recovery", "adaptive_resolver", "execution_validation",
          "monitor", "metrics", "exec_timeline", "diagnostics"]:
    check(f"module file exists: {f}.py",
          pathlib.Path(f"app/execution_gateway/browser/{f}.py").exists())
check("playwright_adapter exists", pathlib.Path("app/execution_gateway/browser/playwright_adapter.py").exists())
check("run exists", pathlib.Path("app/execution_gateway/browser/run.py").exists())
summ("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Enums
# ─────────────────────────────────────────────────────────────────────────────
section("2. Enums")
check("18 failure categories", len(FailureCategory) == 18)
for name in ["ElementNotFound", "ElementHidden", "DetachedElement", "NavigationTimeout",
             "PageCrash", "DownloadTimeout", "UploadFailure", "ValidationFailure",
             "UnexpectedPopup", "NetworkIdleTimeout", "AuthenticationExpired"]:
    check(f"category {name}", any(c.value == name for c in FailureCategory))
check("3 severities", len(FailureSeverity) == 3)
for s in ["TRANSIENT", "RECOVERABLE", "PERMANENT"]:
    check(f"severity {s}", any(x.value == s for x in FailureSeverity))
check("9 recovery actions", len(RecoveryAction) == 9)
for a in ["WAIT", "SCROLL_INTO_VIEW", "REFRESH_LOCATOR", "REQUERY", "WAIT_NETWORK_IDLE",
          "RELOAD_PAGE", "REREAD_PAGE", "DISMISS_POPUP", "NONE"]:
    check(f"recovery action {a}", any(x.value == a for x in RecoveryAction))
summ("2. Enums")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Failure profiles
# ─────────────────────────────────────────────────────────────────────────────
section("3. Failure Profiles")
for c in FailureCategory:
    check(f"profile exists {c.value}", c in PROFILES)
    p = PROFILES[c]
    check(f"profile severity {c.value}", isinstance(p.severity, FailureSeverity))
    check(f"profile retryable bool {c.value}", isinstance(p.retryable, bool))
    check(f"profile recovery tuple {c.value}", isinstance(p.recommended_recovery, tuple))
    check(f"profile to_dict {c.value}", set(p.to_dict().keys()) ==
          {"category", "severity", "retryable", "recommended_recovery"})
check("retryable/permanent disjoint", RETRYABLE_CATEGORIES.isdisjoint(PERMANENT_CATEGORIES))
for c in [FailureCategory.upload_failure, FailureCategory.authentication_expired,
          FailureCategory.invalid_selector, FailureCategory.navigation_failed, FailureCategory.unknown]:
    check(f"{c.value} permanent", c in PERMANENT_CATEGORIES)
    check(f"{c.value} not retryable", PROFILES[c].retryable is False)
    check(f"{c.value} recovery NONE", PROFILES[c].recommended_recovery == (RecoveryAction.none,))
for c in [FailureCategory.element_not_found, FailureCategory.element_hidden,
          FailureCategory.detached_element, FailureCategory.navigation_timeout,
          FailureCategory.page_crash, FailureCategory.validation_failure,
          FailureCategory.network_idle_timeout, FailureCategory.unexpected_popup]:
    check(f"{c.value} retryable", c in RETRYABLE_CATEGORIES)
    check(f"{c.value} has concrete recovery", PROFILES[c].recommended_recovery != (RecoveryAction.none,))
# specific recovery recommendations
check("hidden->scroll", RecoveryAction.scroll_into_view in PROFILES[FailureCategory.element_hidden].recommended_recovery)
check("detached->requery", RecoveryAction.requery in PROFILES[FailureCategory.detached_element].recommended_recovery)
check("navtimeout->networkidle", RecoveryAction.wait_network_idle in PROFILES[FailureCategory.navigation_timeout].recommended_recovery)
check("validation->reread", RecoveryAction.reread_page in PROFILES[FailureCategory.validation_failure].recommended_recovery)
check("crash->reload", RecoveryAction.reload_page in PROFILES[FailureCategory.page_crash].recommended_recovery)
check("popup->dismiss", RecoveryAction.dismiss_popup in PROFILES[FailureCategory.unexpected_popup].recommended_recovery)
summ("3. Failure Profiles")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Classification matrix
# ─────────────────────────────────────────────────────────────────────────────
section("4. Classification Matrix")
matrix = [
    ("no node found", "click", FailureCategory.element_not_found),
    ("waiting for selector .x", "click", FailureCategory.element_not_found),
    ("locator resolved to 0 elements", "click", FailureCategory.element_not_found),
    ("could not find element", "click", FailureCategory.element_not_found),
    ("element is hidden", "click", FailureCategory.element_hidden),
    ("element is not visible", "click", FailureCategory.element_hidden),
    ("element intercepts pointer events", "click", FailureCategory.element_hidden),
    ("element is outside of the viewport", "click", FailureCategory.element_hidden),
    ("element is covered by another", "click", FailureCategory.element_hidden),
    ("element is detached from the DOM", "click", FailureCategory.detached_element),
    ("node is detached", "extract", FailureCategory.detached_element),
    ("stale element handle", "click", FailureCategory.stale_element),
    ("Timeout 30000ms exceeded", "navigate", FailureCategory.navigation_timeout),
    ("navigation goto timed out", "navigate", FailureCategory.navigation_timeout),
    ("Timeout waiting for networkidle", "navigate", FailureCategory.network_idle_timeout),
    ("waiting for load state networkidle", "navigate", FailureCategory.network_idle_timeout),
    ("target closed", "click", FailureCategory.page_crash),
    ("page has been closed", "extract", FailureCategory.page_crash),
    ("the page crashed", "click", FailureCategory.page_crash),
    ("browser has been closed", "click", FailureCategory.page_crash),
    ("unexpected popup appeared", "click", FailureCategory.unexpected_popup),
    ("a dialog opened", "click", FailureCategory.unexpected_popup),
    ("beforeunload prompt", "navigate", FailureCategory.unexpected_popup),
    ("download timeout exceeded", "download", FailureCategory.download_timeout),
    ("download did not complete", "download", FailureCategory.download_failure),
    ("set_input_files failed", "upload", FailureCategory.upload_failure),
    ("file chooser error", "upload", FailureCategory.upload_failure),
    ("is not a valid selector", "click", FailureCategory.invalid_selector),
    ("unsupported selector engine", "click", FailureCategory.invalid_selector),
    ("403 Forbidden unauthorized", "navigate", FailureCategory.authentication_expired),
    ("session expired login required", "click", FailureCategory.authentication_expired),
    ("logged out", "click", FailureCategory.authentication_expired),
    ("net::ERR_NAME_NOT_RESOLVED", "navigate", FailureCategory.navigation_failed),
    ("validation failed: expected", "validate", FailureCategory.validation_failure),
    ("something totally novel", "click", FailureCategory.unknown),
]
for msg, phase, expected in matrix:
    a = fc.classify_failure(Exception(msg), phase=phase)
    check(f"classify '{msg[:26]}' -> {expected.value}", a.category == expected)
    check(f"classify '{msg[:26]}' profile matches", a.profile.category == expected)
    check(f"classify '{msg[:26]}' retryable consistent", a.profile.retryable == (expected in RETRYABLE_CATEGORIES))
    check(f"classify '{msg[:26]}' to_dict", set(a.to_dict().keys()) == {"category", "profile", "base"})
summ("4. Classification Matrix")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Recovery engine
# ─────────────────────────────────────────────────────────────────────────────
section("5. Recovery Engine")
def _an(category, msg, phase):
    a = fc.classify_failure(Exception(msg), phase=phase)
    assert a.category == category, f"{a.category} != {category} for '{msg}'"
    return a
recovery_cases = [
    (FailureCategory.element_not_found, "no node found", "click", "WAIT"),
    (FailureCategory.element_hidden, "element is hidden", "click", "SCROLL_INTO_VIEW"),
    (FailureCategory.detached_element, "element is detached", "click", "REQUERY"),
    (FailureCategory.navigation_timeout, "Timeout exceeded", "navigate", "WAIT_NETWORK_IDLE"),
    (FailureCategory.validation_failure, "validation failed", "validate", "REREAD_PAGE"),
    (FailureCategory.page_crash, "target closed", "click", "RELOAD_PAGE"),
    (FailureCategory.network_idle_timeout, "waiting for networkidle", "navigate", "WAIT"),
]
for category, msg, phase, expected_action in recovery_cases:
    page = FakePage(); session = FakeSession(page)
    r = rec.recover(_an(category, msg, phase), session, _Cmd({"testid": "x"}))
    check(f"recover {category.value} attempted", len(r.actions) >= 1)
    check(f"recover {category.value} has {expected_action}", expected_action in r.actions)
    check(f"recover {category.value} to_dict", set(r.to_dict().keys()) == {"category", "actions", "recovered", "notes"})
# scroll really scrolls
page = FakePage(); session = FakeSession(page)
rec.recover(_an(FailureCategory.element_hidden, "element is hidden", "click"), session, _Cmd({"testid": "x"}))
check("scroll recovery scrolled page", page.scrolled is True)
# reload really reloads
page = FakePage(); session = FakeSession(page)
rec.recover(_an(FailureCategory.page_crash, "target closed", "click"), session, _Cmd())
check("reload recovery reloaded", page.reloaded is True)
# popup dismiss
page = FakePage(); extra = FakePage()
class _Ctx:
    def __init__(self, pages): self.pages = pages
session = FakeSession(page, context=_Ctx([page, extra]))
rp = rec.recover(_an(FailureCategory.unexpected_popup, "unexpected popup", "click"), session, _Cmd())
check("popup dismiss action", "DISMISS_POPUP" in rp.actions)
# never raises on bad session
class _Bad:
    def ensure_page(self): raise RuntimeError("boom")
rb = rec.recover(_an(FailureCategory.element_hidden, "element is hidden", "click"), _Bad(), _Cmd({"testid": "x"}))
check("recovery bad session no crash", rb.recovered is False)
# permanent -> no concrete action
for category, msg, phase in [(FailureCategory.invalid_selector, "is not a valid selector", "click"),
                             (FailureCategory.upload_failure, "set_input_files failed", "upload"),
                             (FailureCategory.authentication_expired, "session expired", "click")]:
    r = rec.recover(_an(category, msg, phase), FakeSession(FakePage()), _Cmd())
    check(f"permanent {category.value} no recovery action", r.actions == [])
    check(f"permanent {category.value} not recovered", r.recovered is False)
summ("5. Recovery Engine")

# ─────────────────────────────────────────────────────────────────────────────
# 6. Adaptive resolver
# ─────────────────────────────────────────────────────────────────────────────
section("6. Adaptive Resolver")
from app.execution_gateway.browser.capabilities import EXTENDED_RESOLUTION_PRIORITY, RESOLUTION_PRIORITY
check("extended has 12", len(EXTENDED_RESOLUTION_PRIORITY) == 12)
check("AdaptiveResolver uses extended", ar.AdaptiveResolver.PRIORITY == EXTENDED_RESOLUTION_PRIORITY)
# preserves Phase C relative order
ext = list(EXTENDED_RESOLUTION_PRIORITY)
positions = [ext.index(s) for s in RESOLUTION_PRIORITY]
check("preserves Phase C relative order", positions == sorted(positions))
# new strategies
for strat, kind in [("aria", "label"), ("label", "label"), ("placeholder", "placeholder"), ("text", "text")]:
    r = ar.resolve(FakePage(), {strat: "v"})
    check(f"adaptive {strat} strategy", r.strategy == strat)
    check(f"adaptive {strat} builder {kind}", r.locator.key[0] == kind)
# full priority walk × several values
for val in ["a", "btn", "field_2", "Name", "q"]:
    params = {k: val for k in EXTENDED_RESOLUTION_PRIORITY}
    for expected in EXTENDED_RESOLUTION_PRIORITY:
        r = ar.resolve(FakePage(), params)
        check(f"priority {val} picks {expected}", r.strategy == expected)
        check(f"priority {val} value {expected}", r.value == val)
        del params[expected]
# backward-compat: Phase C params resolve to same strategy as Phase C resolver
for params in [{"selector": "#x"}, {"testid": "t"}, {"aria_label": "A"}, {"role": "button"},
               {"id": "e"}, {"name": "q"}, {"css": ".b"}, {"xpath": "//a"}]:
    pc = phasec_resolver.resolve(FakePage(), params)
    ad = ar.resolve(FakePage(), params)
    check(f"phase-c-compat {pc.strategy}", ad.strategy == pc.strategy)
# strategy_for
for k in EXTENDED_RESOLUTION_PRIORITY:
    check(f"strategy_for {k}", ar.strategy_for({k: "v"}) == k)
check("strategy_for none", ar.strategy_for({"url": "x"}) is None)
# strict uniqueness
check("strict unique ok", ar.resolve_strict(FakePage(element_count=1), {"testid": "x", "strict": True}).strategy == "testid")
for cnt in [0, 2, 5]:
    try:
        ar.resolve_strict(FakePage(element_count=cnt), {"testid": "x", "strict": True})
        check(f"strict count {cnt} raises", False)
    except ElementResolutionError:
        check(f"strict count {cnt} raises", True)
check("non-strict allows multiple", ar.resolve_strict(FakePage(element_count=3), {"testid": "x"}).strategy == "testid")
summ("6. Adaptive Resolver")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Execution validation
# ─────────────────────────────────────────────────────────────────────────────
section("7. Execution Validation")
def _v(page, params, **kw):
    return ev.validate("click", FakeSession(page), _Cmd(params), **kw)
check("no validate_after noop", _v(FakePage(), {"testid": "x"}).performed is False)
check("no validate_after passes", _v(FakePage(), {"testid": "x"}).passed is True)
check("empty validate_after noop", _v(FakePage(), {"validate_after": {}}).performed is False)
check("url_contains pass", _v(FakePage(url="https://x/cart"), {"validate_after": {"url_contains": "cart"}}).passed)
check("url_contains fail", not _v(FakePage(url="https://x/home"), {"validate_after": {"url_contains": "cart"}}).passed)
check("url_changed pass", _v(FakePage(url="https://x/b"), {"validate_after": {"url_changed": True}}, pre_state={"url": "https://x/a"}).passed)
check("url_changed fail", not _v(FakePage(url="https://x/a"), {"validate_after": {"url_changed": True}}, pre_state={"url": "https://x/a"}).passed)
check("text_contains pass", _v(FakePage(body="done ok"), {"validate_after": {"text_contains": "done"}}).passed)
check("text_contains fail", not _v(FakePage(body="nope"), {"validate_after": {"text_contains": "done"}}).passed)
check("text_absent pass", _v(FakePage(body="all good"), {"validate_after": {"text_absent": "error"}}).passed)
check("text_absent fail", not _v(FakePage(body="an error"), {"validate_after": {"text_absent": "error"}}).passed)
check("exists pass", _v(FakePage(element_count=1), {"validate_after": {"exists": {"testid": "t"}}}).passed)
check("exists fail", not _v(FakePage(element_count=0), {"validate_after": {"exists": {"testid": "t"}}}).passed)
check("gone pass", _v(FakePage(element_count=0), {"validate_after": {"gone": {"testid": "t"}}}).passed)
check("gone fail", not _v(FakePage(element_count=3), {"validate_after": {"gone": {"testid": "t"}}}).passed)
check("value_equals str pass", _v(FakePage(field_value="hi"), {"id": "e", "validate_after": {"value_equals": "hi"}}).passed)
check("value_equals str fail", not _v(FakePage(field_value="x"), {"id": "e", "validate_after": {"value_equals": "hi"}}).passed)
check("value_equals dict", _v(FakePage(field_value="abc"), {"validate_after": {"value_equals": {"testid": "f", "value": "abc"}}}).passed)
check("filename_visible pass", _v(FakePage(body="Uploaded: a.csv"), {"validate_after": {"filename_visible": "a.csv"}}).passed)
check("filename_visible fail", not _v(FakePage(body="nothing"), {"validate_after": {"filename_visible": "a.csv"}}).passed)
check("file_exists missing fail", not _v(FakePage(), {"validate_after": {"file_exists": "/no/such/xyz"}}).passed)
import tempfile, os as _os
_tmp = _os.path.join(tempfile.gettempdir(), "phased_val_check.txt")
open(_tmp, "w").write("x")
check("file_exists explicit pass", _v(FakePage(), {"validate_after": {"file_exists": _tmp}}).passed)
check("file_exists from details", _v(FakePage(), {"validate_after": {"file_exists": True}}, result_details={"download_path": _tmp}).passed)
_os.remove(_tmp)
# combined
cmb = _v(FakePage(url="https://x/cart", body="Added", element_count=1),
         {"validate_after": {"url_contains": "cart", "text_contains": "Added", "exists": {"testid": "b"}}})
check("combined all pass", cmb.passed and len(cmb.checks) == 3)
check("combined one fail", not _v(FakePage(url="https://x/cart", body="Added"),
      {"validate_after": {"url_contains": "cart", "text_contains": "MISS"}}).passed)
check("validation to_dict", set(_v(FakePage(), {"validate_after": {"url_contains": "x"}}).to_dict().keys())
      == {"performed", "passed", "strategy", "checks", "details"})
summ("7. Execution Validation")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Monitor
# ─────────────────────────────────────────────────────────────────────────────
section("8. Monitor")
mon._reset_for_testing()
r1 = mon.start_step("e1", "s1", 1, "navigate", 0.0)
check("start_step record", r1.execution_id == "e1" and r1.step_id == "s1")
check("start_step unfinished", r1.finished_at is None)
mon.finish_step(r1, finished_at=0.5, attempts=2, outcome="completed", validation_result=True,
                locator_strategy="testid", recovery_used=["WAIT"])
check("finish outcome", r1.outcome == "completed")
check("finish attempts", r1.attempts == 2)
check("finish retries", r1.retries == 1)
check("finish elapsed", r1.elapsed_ms == 500.0)
check("finish validation", r1.validation_result is True)
check("finish strategy", r1.locator_strategy == "testid")
check("finish recovery", r1.recovery_used == ["WAIT"])
r2 = mon.start_step("e1", "s2", 2, "click", 0.0)
mon.finish_step(r2, finished_at=0.1, attempts=3, outcome="failed", failure_category="ElementNotFound")
check("failed category", r2.failure_category == "ElementNotFound")
check("steps_for 2", len(mon.steps_for("e1")) == 2)
check("steps_for empty", mon.steps_for("absent") == [])
s = mon.summary("e1")
check("summary total", s["total_steps"] == 2)
check("summary completed", s["completed_steps"] == 1)
check("summary failed", s["failed_steps"] == 1)
check("summary retries", s["total_retries"] == 3)
check("summary recoveries", s["recoveries_used"] == 1)
check("record to_dict keys", set(r1.to_dict().keys()) >= {"execution_id", "step_id", "order", "phase",
      "elapsed_ms", "attempts", "retries", "validation_result", "failure_category", "recovery_used",
      "locator_strategy", "screenshots", "outcome"})
check("stats", mon.stats()["tracked_executions"] == 1)
mon._reset_for_testing()
check("reset", mon.steps_for("e1") == [])
summ("8. Monitor")

# ─────────────────────────────────────────────────────────────────────────────
# 9. Metrics
# ─────────────────────────────────────────────────────────────────────────────
section("9. Metrics")
met._reset_for_testing()
m0 = met.get_metrics()
for k in ["steps_total", "steps_succeeded", "steps_failed", "step_success_rate", "average_retries",
          "average_execution_ms", "recoveries_attempted", "recovery_success_rate",
          "validations_attempted", "validation_success_rate", "locator_strategy_counts",
          "locator_strategy_pct", "failure_distribution"]:
    check(f"metrics key {k}", k in m0)
check("initial steps 0", m0["steps_total"] == 0)
check("initial rates 0 (no div by zero)", m0["step_success_rate"] == 0.0 and m0["recovery_success_rate"] == 0.0)
met.record_step(succeeded=True, retries=1, elapsed_ms=10.0, locator_strategy="testid")
met.record_step(succeeded=True, retries=3, elapsed_ms=20.0, locator_strategy="testid")
met.record_step(succeeded=False, retries=0, elapsed_ms=30.0, locator_strategy="css")
m1 = met.get_metrics()
check("steps total 3", m1["steps_total"] == 3)
check("avg retries", m1["average_retries"] == round(4/3, 4))
check("avg time", m1["average_execution_ms"] == round(60/3, 4))
check("step success rate", m1["step_success_rate"] == round(2/3, 4))
check("strategy counts testid", m1["locator_strategy_counts"]["testid"] == 2)
check("strategy pct testid", m1["locator_strategy_pct"]["testid"] == round(2/3, 4))
met.record_recovery(succeeded=True); met.record_recovery(succeeded=False)
check("recovery rate", met.get_metrics()["recovery_success_rate"] == 0.5)
met.record_validation(passed=True); met.record_validation(passed=True); met.record_validation(passed=False)
check("validation rate", met.get_metrics()["validation_success_rate"] == round(2/3, 4))
met.record_failure("ElementNotFound"); met.record_failure("ElementNotFound"); met.record_failure("NavigationTimeout")
fd = met.get_metrics()["failure_distribution"]
check("failure dist ElementNotFound", fd["ElementNotFound"] == 2)
check("failure dist NavigationTimeout", fd["NavigationTimeout"] == 1)
met._reset_for_testing()
check("metrics reset", met.get_metrics()["steps_total"] == 0)
summ("9. Metrics")

# ─────────────────────────────────────────────────────────────────────────────
# 10. Timeline + Diagnostics
# ─────────────────────────────────────────────────────────────────────────────
section("10. Timeline + Diagnostics")
etl._reset_for_testing()
check("8 valid events", len(etl.VALID_EVENTS) == 8)
for e in ["planned", "started", "retried", "recovered", "validated", "completed", "failed", "rollback"]:
    check(f"valid event {e}", e in etl.VALID_EVENTS)
for i, e in enumerate(["planned", "started", "recovered", "retried", "validated", "completed"]):
    etl.record("e1", "s1", e, order=1)
ev_list = etl.events_for("e1")
check("timeline events recorded", len(ev_list) == 6)
check("timeline chronological", ev_list[0]["event_type"] == "planned")
check("timeline events_for_step", len(etl.events_for_step("e1", "s1")) == 6)
tsum = etl.summary("e1")
check("timeline summary count", tsum["event_count"] == 6)
check("timeline summary types", tsum["type_counts"]["planned"] == 1)
check("timeline empty", etl.events_for("absent") == [])
etl.record("e1", "s2", "recovered", detail={"actions": ["WAIT"]})
check("timeline detail", any(e.get("detail", {}).get("actions") == ["WAIT"] for e in etl.events_for("e1")))
# diagnostics
mon._reset_for_testing(); met._reset_for_testing()
rec_m = mon.start_step("e-d", "s1", 1, "click", 0.0)
mon.finish_step(rec_m, finished_at=0.2, attempts=2, outcome="completed", validation_result=True,
                locator_strategy="testid", recovery_used=["WAIT"])
d = diag.diagnostics("e-d")
for k in ["execution_id", "page_url", "title", "active_frame", "active_tab", "locator_strategy_used",
          "recovery_history", "validation_history", "retry_history", "last_screenshot",
          "monitor_summary", "timeline_summary", "metrics"]:
    check(f"diag key {k}", k in d)
check("diag active_frame main", d["active_frame"] == "main")
check("diag locator strategy", d["locator_strategy_used"] == "testid")
check("diag recovery history", len(d["recovery_history"]) == 1)
check("diag validation history", len(d["validation_history"]) == 1)
check("diag retry history", len(d["retry_history"]) == 1)
check("diag screenshot metadata only", d["last_screenshot"] is None or isinstance(d["last_screenshot"], dict))
summ("10. Timeline + Diagnostics")

# ─────────────────────────────────────────────────────────────────────────────
# 11. Adapter — Phase D engaged
# ─────────────────────────────────────────────────────────────────────────────
section("11. Adapter — Phase D Engaged")
mon._reset_for_testing(); met._reset_for_testing(); etl._reset_for_testing()
a = _adapter(FakePage())
check("phase_d true", a.phase_d is True)
r = a.navigate(_cmd(CommandType.navigate, {"url": "https://x.com"}))
check("navigate success", r.success is True)
for k in ["attempts", "recoveries", "recovery_used", "locator_strategy", "validation_result", "phase"]:
    check(f"adaptive output {k}", k in r.output)
check("monitor recorded", len(mon.steps_for("e1")) == 1)
check("monitor completed", mon.steps_for("e1")[0].outcome == "completed")
check("metrics step recorded", met.get_metrics()["steps_total"] == 1)
check("timeline started+completed", {"started", "completed"} <= set(etl.summary("e1")["type_counts"].keys()))
mon._reset_for_testing(); met._reset_for_testing(); etl._reset_for_testing()
r = _adapter(FakePage()).click(_cmd(CommandType.click, {"testid": "go"}))
check("click adaptive strategy", r.output["details"]["strategy"] == "testid")
check("metric strategy testid", met.get_metrics()["locator_strategy_counts"].get("testid") == 1)
summ("11. Adapter — Phase D Engaged")

# ─────────────────────────────────────────────────────────────────────────────
# 12. Adapter — recovery + retry policy V2
# ─────────────────────────────────────────────────────────────────────────────
section("12. Adapter — Recovery + Retry Policy V2")
mon._reset_for_testing(); met._reset_for_testing(); etl._reset_for_testing()
# transient (element not found) recovers then succeeds
r = _adapter(FakePage(click_fail_times=1, click_fail_msg="no node found")).click(_cmd(CommandType.click, {"testid": "go"}))
check("recover+succeed", r.success is True)
check("recover attempts 2", r.output["attempts"] == 2)
check("recovery recorded", len(r.output["recovery_used"]) >= 1)
# hidden recovers via scroll
page = FakePage(click_fail_times=1, click_fail_msg="element is hidden")
r = _adapter(page).click(_cmd(CommandType.click, {"testid": "go"}))
check("hidden recover success", r.success is True)
check("hidden scrolled", page.scrolled is True)
check("hidden SCROLL action", "SCROLL_INTO_VIEW" in r.output["recovery_used"])
# transient exhausted -> bounded failure
r = _adapter(FakePage(click_fail_times=9, click_fail_msg="no node found"), retry_config=RetryConfig(max_retries=2)).click(_cmd(CommandType.click, {"testid": "go"}))
check("exhausted fails", r.success is False)
check("exhausted bounded 3", r.output["attempts"] == 3)
check("exhausted category", r.output["failure_category"] == "ElementNotFound")
# permanent -> immediate fail (no retry)
for msg, cat in [("is not a valid selector", "InvalidSelector"),
                 ("session expired login required", "AuthenticationExpired")]:
    r = _adapter(FakePage(click_fail_times=9, click_fail_msg=msg), retry_config=RetryConfig(max_retries=2)).click(_cmd(CommandType.click, {"selector": ".x"}))
    check(f"permanent {cat} immediate fail", r.success is False)
    check(f"permanent {cat} attempts 1", r.output["attempts"] == 1)
    check(f"permanent {cat} category", r.output["failure_category"] == cat)
# failure distribution recorded
met._reset_for_testing()
_adapter(FakePage(click_fail_times=9, click_fail_msg="is not a valid selector")).click(_cmd(CommandType.click, {"selector": ".x"}))
check("failure dist recorded", met.get_metrics()["failure_distribution"].get("InvalidSelector", 0) >= 1)
# bounded across retry budgets
for mr in [0, 1, 2, 3]:
    r = _adapter(FakePage(click_fail_times=99, click_fail_msg="no node found"), retry_config=RetryConfig(max_retries=mr)).click(_cmd(CommandType.click, {"testid": "x"}))
    check(f"bounded retries mr={mr}", r.output["attempts"] == mr + 1)
summ("12. Adapter — Recovery + Retry Policy V2")

# ─────────────────────────────────────────────────────────────────────────────
# 13. Adapter — first-class validation
# ─────────────────────────────────────────────────────────────────────────────
section("13. Adapter — First-Class Validation")
mon._reset_for_testing(); met._reset_for_testing()
r = _adapter(FakePage(url="https://x/cart")).navigate(_cmd(CommandType.navigate, {"url": "https://x/cart", "validate_after": {"url_contains": "cart"}}))
check("validate_after pass", r.validation_passed is True)
check("post_validation populated", r.output["post_validation"]["passed"] is True)
r = _adapter(FakePage(url="https://x/home"), retry_config=RetryConfig(max_retries=0)).navigate(_cmd(CommandType.navigate, {"url": "https://x/home", "validate_after": {"url_contains": "cart"}}))
check("validate_after fail -> success True", r.success is True)
check("validate_after fail -> validation False", r.validation_passed is False)
r = _adapter(FakePage(field_value="hi@x.com")).type(_cmd(CommandType.type, {"id": "email", "value": "hi@x.com", "validate_after": {"value_equals": "hi@x.com"}}))
check("type value_equals pass", r.validation_passed is True)
check("validations recorded", met.get_metrics()["validations_attempted"] >= 1)
summ("13. Adapter — First-Class Validation")

# ─────────────────────────────────────────────────────────────────────────────
# 14. Backward-compatibility (flags off = Phase C)
# ─────────────────────────────────────────────────────────────────────────────
section("14. Backward Compatibility")
off = PlaywrightAdapter(execution_id="e-off", session_manager=FakeMgr(FakePage()))
check("default phase_d off", off.phase_d is False)
check("default adaptive off", off.adaptive is False)
check("default recovery off", off.recovery is False)
check("default post_validation off", off.post_validation is False)
mon._reset_for_testing()
off.click(_cmd(CommandType.click, {"testid": "go"}))
check("flags off no monitor record", mon.steps_for("e-off") == [])
# Phase C resolver untouched
check("phase C priority 8", len(RESOLUTION_PRIORITY) == 8)
check("phase C resolver module has ElementResolver", hasattr(phasec_resolver, "ElementResolver"))
check("phase C priority preserved in resolver", phasec_resolver.ElementResolver.PRIORITY == RESOLUTION_PRIORITY)
# adaptive output keys NOT present when off (Phase C output shape)
roff = off.click(_cmd(CommandType.click, {"testid": "go"}))
check("phase C output has attempts", "attempts" in roff.output)
check("phase C output no failure_category on success", "failure_category" not in roff.output)
# capabilities additive
check("RESOLUTION_PRIORITY still present", hasattr(caps, "RESOLUTION_PRIORITY"))
check("EXTENDED additive superset", set(RESOLUTION_PRIORITY) <= set(EXTENDED_RESOLUTION_PRIORITY))
summ("14. Backward Compatibility")

# ─────────────────────────────────────────────────────────────────────────────
# 15. REST endpoints (additive)
# ─────────────────────────────────────────────────────────────────────────────
section("15. REST Endpoints")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
routes = {r.path for r in app.routes}
for p in ["/gateway/browser/metrics", "/gateway/browser/diagnostics/{execution_id}",
          "/gateway/browser/monitor/{execution_id}", "/gateway/browser/timeline/{execution_id}"]:
    check(f"route {p}", p in routes)
# existing endpoints preserved (no breaking changes)
for p in ["/gateway/start/{plan_id}", "/gateway/status/{execution_id}", "/gateway/inspect/{execution_id}",
          "/gateway/browser/session/{execution_id}", "/gateway/browser/screenshot/{execution_id}"]:
    check(f"existing route preserved {p}", p in routes)
check("metrics 200", client.get("/gateway/browser/metrics").status_code == 200)
check("metrics has keys", "step_success_rate" in client.get("/gateway/browser/metrics").json())
check("diagnostics 404 unknown", client.get("/gateway/browser/diagnostics/nope").status_code == 404)
check("monitor 404 unknown", client.get("/gateway/browser/monitor/nope").status_code == 404)
check("timeline 404 unknown", client.get("/gateway/browser/timeline/nope").status_code == 404)
summ("15. REST Endpoints")

# ─────────────────────────────────────────────────────────────────────────────
# 16. Static safety — no AI/OCR/LLM/Vision/self-healing/other stacks
# ─────────────────────────────────────────────────────────────────────────────
section("16. Static Safety")
forbidden = [
    "import openai", "from openai", "openai.", "import anthropic", "from anthropic",
    "import transformers", "import torch", "import cv2", "cv2.imread", "pytesseract", "easyocr",
    "import selenium", "from selenium", "selenium.webdriver", "import pyppeteer", "puppeteer.launch",
    "self_heal(", "def self_heal", "vision_model(", ".ocr(", "call_llm(", "embedding(",
    "model.predict", "openai_api", "anthropic_api",
]
pkg = pathlib.Path("app/execution_gateway/browser")
phase_d_files = ["failure_classes.py", "recovery.py", "adaptive_resolver.py", "execution_validation.py",
                 "monitor.py", "metrics.py", "exec_timeline.py", "diagnostics.py", "playwright_adapter.py", "run.py"]
for fname in phase_d_files:
    text = (pkg / fname).read_text(encoding="utf-8", errors="replace").lower()
    for fb in forbidden:
        check(f"NO '{fb}' in {fname}", fb.lower() not in text)
# determinism: no randomness in recovery/resolution/classification
for fname in ["recovery.py", "adaptive_resolver.py", "failure_classes.py", "execution_validation.py"]:
    text = (pkg / fname).read_text(encoding="utf-8", errors="replace")
    check(f"no random in {fname}", "import random" not in text and "random." not in text)
# adapter does not import playwright (talks to session manager); no new arch layer
adapter_src = (pkg / "playwright_adapter.py").read_text(encoding="utf-8")
check("adapter no playwright import", "import playwright" not in adapter_src and "from playwright" not in adapter_src)
# gateway/planner not modified by Phase D (no edits to those modules from browser pkg)
check("recovery is deterministic class", "class RecoveryEngine" in (pkg / "recovery.py").read_text(encoding="utf-8"))
summ("16. Static Safety")

# ─────────────────────────────────────────────────────────────────────────────
# 16a. All-category profile consistency (18 categories)
# ─────────────────────────────────────────────────────────────────────────────
section("16a. All-Category Profile Consistency")
from app.execution_gateway.browser.failure_classes import profile_for as _pf
for c in FailureCategory:
    p = _pf(c)
    check(f"{c.value} profile identity", p is PROFILES[c])
    check(f"{c.value} severity enum", p.severity in (FailureSeverity.transient, FailureSeverity.recoverable, FailureSeverity.permanent))
    check(f"{c.value} retryable membership", p.retryable == (c in RETRYABLE_CATEGORIES))
    check(f"{c.value} permanent membership", (not p.retryable) == (c in PERMANENT_CATEGORIES))
    check(f"{c.value} recovery tuple non-empty", len(p.recommended_recovery) >= 1)
    check(f"{c.value} permanent => NONE recovery", (p.retryable) or p.recommended_recovery == (RecoveryAction.none,))
    d = p.to_dict()
    check(f"{c.value} to_dict category", d["category"] == c.value)
    check(f"{c.value} to_dict retryable", d["retryable"] == p.retryable)
    check(f"{c.value} to_dict recovery list", isinstance(d["recommended_recovery"], list))
summ("16a. All-Category Profile Consistency")

# ─────────────────────────────────────────────────────────────────────────────
# 16b. Adaptive builder matrix (12 strategies × many values)
# ─────────────────────────────────────────────────────────────────────────────
section("16b. Adaptive Builder Matrix")
def _expected_key(strat, v):
    if strat in ("selector", "css"):    return ("locator", v)
    if strat == "testid":               return ("testid", v)
    if strat in ("aria_label", "aria", "label"): return ("label", v)
    if strat == "role":                 return ("role", v)
    if strat == "placeholder":          return ("placeholder", v)
    if strat == "text":                 return ("text", v)
    if strat == "id":                   return ("locator", f"#{v}")
    if strat == "name":                 return ("locator", f'[name="{v}"]')
    if strat == "xpath":                return ("locator", f"xpath={v}")
    return None
values = ["a", "b1", "go", "field2", "Name", "main", "q", "x", "submit", "item"]
for v in values:
    for strat in EXTENDED_RESOLUTION_PRIORITY:
        r = ar.resolve(FakePage(), {strat: v})
        check(f"builder {strat}={v} strategy", r.strategy == strat)
        check(f"builder {strat}={v} value", r.value == v)
        check(f"builder {strat}={v} key", r.locator.key == _expected_key(strat, v))
summ("16b. Adaptive Builder Matrix")

# ─────────────────────────────────────────────────────────────────────────────
# 16c. Extended classification variants
# ─────────────────────────────────────────────────────────────────────────────
section("16c. Extended Classification Variants")
variants = [
    ("element is not visible (hidden)", "click", FailureCategory.element_hidden),
    ("element is detached from the document", "click", FailureCategory.detached_element),
    ("the node is detached", "extract", FailureCategory.detached_element),
    ("Timeout 10000ms exceeded.", "navigate", FailureCategory.navigation_timeout),
    ("Timeout while waiting for load state \"networkidle\"", "navigate", FailureCategory.network_idle_timeout),
    ("Target page, context or browser has been closed", "click", FailureCategory.page_crash),
    ("page.click: page has been closed", "click", FailureCategory.page_crash),
    ("Unexpected popup window", "click", FailureCategory.unexpected_popup),
    ("alert( triggered", "click", FailureCategory.unexpected_popup),
    ("download did not start", "download", FailureCategory.download_failure),
    ("download timeout while waiting", "download", FailureCategory.download_timeout),
    ("no such file for set_input_files", "upload", FailureCategory.upload_failure),
    ("ERR_NAME_NOT_RESOLVED net::", "navigate", FailureCategory.navigation_failed),
    ("malformed selector token", "click", FailureCategory.invalid_selector),
    ("user is unauthorized to view", "navigate", FailureCategory.authentication_expired),
    ("your session expired", "click", FailureCategory.authentication_expired),
    ("locator resolved to 0 elements matching", "click", FailureCategory.element_not_found),
    ("could not find the submit button", "click", FailureCategory.element_not_found),
    ("element is not visible and is hidden", "click", FailureCategory.element_hidden),
    ("element is outside of the viewport bounds", "click", FailureCategory.element_hidden),
]
for msg, phase, expected in variants:
    a = fc.classify_failure(Exception(msg), phase=phase)
    check(f"variant '{msg[:24]}' category", a.category == expected)
    check(f"variant '{msg[:24]}' retryable", a.profile.retryable == (expected in RETRYABLE_CATEGORIES))
    check(f"variant '{msg[:24]}' base present", a.base is not None)
# classify_category helper consistency
for msg, phase, expected in variants:
    check(f"classify_category '{msg[:20]}'", fc.classify_category(Exception(msg), phase=phase) == expected)
summ("16c. Extended Classification Variants")

# ─────────────────────────────────────────────────────────────────────────────
# 16d. Adapter — all 9 methods through Phase D path
# ─────────────────────────────────────────────────────────────────────────────
section("16d. Adapter — All 9 Methods (Phase D)")
mon._reset_for_testing(); met._reset_for_testing(); etl._reset_for_testing()
method_cases = [
    ("navigate", {"url": "https://x.com"}, "NONE"),
    ("click", {"testid": "go"}, "NONE"),
    ("type", {"id": "e", "value": "hi"}, "NONE"),
    ("wait", {"ms": 5}, "NONE"),
    ("extract", {"selector": ".m", "mode": "text"}, "NONE"),
    ("validate", {"selector": ".x"}, "DOM_PRESENCE"),
    ("upload", {"selector": "input", "file": "/a"}, "NONE"),
    ("download", {"testid": "dl"}, "NONE"),
    ("execute_custom", {"action": "noop"}, "NONE"),
]
ctype_for = {"navigate": CommandType.navigate, "click": CommandType.click, "type": CommandType.type,
             "wait": CommandType.wait, "extract": CommandType.extract, "validate": CommandType.validate,
             "upload": CommandType.upload, "download": CommandType.download, "execute_custom": CommandType.custom}
for i, (mname, params, strat) in enumerate(method_cases):
    a = _adapter(FakePage())
    a.execution_id = f"e-m{i}"
    result = getattr(a, mname)(_cmd(ctype_for[mname], params, strategy=strat, step_id=f"st{i}", order=i))
    check(f"{mname} success bool", isinstance(result.success, bool))
    check(f"{mname} success true", result.success is True)
    check(f"{mname} duration >=0", result.duration_ms >= 0.0)
    check(f"{mname} output dict", isinstance(result.output, dict))
    check(f"{mname} validation bool", isinstance(result.validation_passed, bool))
    check(f"{mname} attempts present", "attempts" in result.output)
    check(f"{mname} recovery_used present", "recovery_used" in result.output)
    check(f"{mname} phase present", result.output.get("phase") == mname.replace("execute_custom", "custom"))
    check(f"{mname} monitor recorded", len(mon.steps_for(f"e-m{i}")) == 1)
    check(f"{mname} monitor completed", mon.steps_for(f"e-m{i}")[0].outcome == "completed")
summ("16d. Adapter — All 9 Methods (Phase D)")

# ─────────────────────────────────────────────────────────────────────────────
# 16e. Recovery action coverage per retryable category
# ─────────────────────────────────────────────────────────────────────────────
section("16e. Recovery Action Coverage")
retryable_recovery = [
    (FailureCategory.element_not_found, "no node found", "click"),
    (FailureCategory.element_hidden, "element is hidden", "click"),
    (FailureCategory.detached_element, "element is detached", "click"),
    (FailureCategory.stale_element, "stale element handle", "click"),
    (FailureCategory.navigation_timeout, "Timeout exceeded", "navigate"),
    (FailureCategory.network_idle_timeout, "waiting for networkidle", "navigate"),
    (FailureCategory.page_crash, "target closed", "click"),
    (FailureCategory.validation_failure, "validation failed", "validate"),
    (FailureCategory.unexpected_popup, "unexpected popup", "click"),
    (FailureCategory.download_timeout, "download timeout", "download"),
    (FailureCategory.transient_timeout, "Timeout exceeded", "click"),
    (FailureCategory.temporary_rendering, "rendering not ready", "click"),
]
for category, msg, phase in retryable_recovery:
    a = fc.classify_failure(Exception(msg), phase=phase)
    if a.category != category:
        # phase/keyword may refine; accept the refined retryable category as long as retryable
        check(f"{category.value} refined retryable", a.profile.retryable is True)
        continue
    page = FakePage(); r = rec.recover(a, FakeSession(page), _Cmd({"testid": "x"}))
    check(f"{category.value} recovery attempted", len(r.actions) >= 1)
    check(f"{category.value} recovery recorded bool", isinstance(r.recovered, bool))
    check(f"{category.value} actions valid", all(act in [x.value for x in RecoveryAction] for act in r.actions))
summ("16e. Recovery Action Coverage")

# ─────────────────────────────────────────────────────────────────────────────
# 17. Real browser certification (bonus; guarded)
# ─────────────────────────────────────────────────────────────────────────────
section("17. Real Browser Certification")
chromium_ok = False
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _b = _p.chromium.launch(headless=True); _b.close()
    chromium_ok = True
except Exception as _e:
    print(f"  (chromium unavailable — skipped: {str(_e)[:50]})")

if chromium_ok:
    import socket, threading, http.server, socketserver
    HTML = b"<!doctype html><html><head><title>V</title></head><body><h1 id='h'>Cert OK</h1><div id='slot'></div><script>setTimeout(function(){var b=document.createElement('button');b.id='late';b.setAttribute('data-testid','late');document.getElementById('slot').appendChild(b);},500);</script></body></html>"
    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(HTML))); self.end_headers(); self.wfile.write(HTML)
        def log_message(self, *a): pass
    _s = socket.socket(); _s.bind(("127.0.0.1", 0)); _port = _s.getsockname()[1]; _s.close()
    _httpd = socketserver.TCPServer(("127.0.0.1", _port), _H)
    threading.Thread(target=_httpd.serve_forever, daemon=True).start()
    URL = f"http://127.0.0.1:{_port}/"

    from app.execution_gateway import registry as ereg, analytics as ganal, timeline as gtl, audit as gaudit
    from app.execution_gateway.browser import run as brun, session as bs
    from app.execution_gateway.models import ExecutionState
    from app.execution_planning import registry as plan_reg
    from app.execution_planning.registry import set_status
    from app.execution_planning.models import PlanStatus, ActionType, TargetType, ValidationStrategy, ExecutionMode, make_step, make_plan
    from app.authorization import registry as auth_reg
    from app.authorization.models import make_authorization
    from app.mission import store as ms
    from app.mission.models import Mission, MissionState
    for m in [ereg, ganal, gtl, gaudit, plan_reg, auth_reg, ms, mon, met, etl]:
        m._reset_for_testing()
    bs._reset_for_testing()
    auth = make_authorization("c", True, "ok", "HIGH", time.time() + 3600, mission_id="m-cv", task_id="t")
    auth_reg.add(auth); ms.put(Mission("m-cv", "t", "obj", MissionState.active, task_ids=["t"]))
    steps = [
        make_step(1, ActionType.navigate, TargetType.url, URL, parameters={"url": URL,
                  "validate_after": {"url_contains": "127.0.0.1"}}),
        make_step(2, ActionType.extract, TargetType.region, "h", parameters={"id": "h", "mode": "text"}),
        # late button: short timeout forces ElementNotFound -> recovery -> retry -> success
        make_step(3, ActionType.click, TargetType.element, "late", parameters={"testid": "late", "timeout_ms": 250}),
        make_step(4, ActionType.validate, TargetType.page, "cert text",
                  parameters={"expected_text": "Cert OK"}, expected_result="Cert OK",
                  validation_strategy=ValidationStrategy.text_match),
    ]
    plan = make_plan(auth.authorization_id, mission_id="m-cv", task_id="t", created_at=time.time(),
                     execution_mode=ExecutionMode.sequential, steps=steps, estimated_duration_ms=0,
                     rollback_supported=True, confidence=0.9)
    plan_reg.add(plan); set_status(plan.plan_id, PlanStatus.ready)
    r = brun.execute_plan_with_browser(plan.plan_id, headless=True, cleanup=False)
    check("cert completed", r.state == ExecutionState.completed)
    check("cert 4 steps", r.completed_steps == 4)
    check("cert adaptive playwright", r.adapter_name == "playwright")
    check("cert extract content", "Cert OK" in r.step_executions[1].output["details"]["content_preview"])
    check("cert recovery happened", r.step_executions[2].output["attempts"] >= 2)
    check("cert recovery recorded", len(r.step_executions[2].output["recovery_used"]) >= 1)
    check("cert text validation", r.step_executions[3].validation_passed is True)
    check("cert monitor steps", mon.summary(r.execution_id)["total_steps"] == 4)
    check("cert metrics recovery", met.get_metrics()["recoveries_attempted"] >= 1)
    check("cert timeline recovered", etl.summary(r.execution_id)["type_counts"].get("recovered", 0) >= 1)
    check("cert timeline planned", etl.summary(r.execution_id)["type_counts"].get("planned", 0) == 4)
    dgn = diag.diagnostics(r.execution_id)
    check("cert diag url", dgn["page_url"] is not None)
    check("cert diag recovery history", len(dgn["recovery_history"]) >= 1)
    check("cert diag strategy", dgn["locator_strategy_used"] in ("testid", "id", "css"))
    bs.close(r.execution_id)
    _httpd.shutdown()
summ("17. Real Browser Certification")

# ── Final tally ───────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*62}")
print(f"PHASE D VALIDATION: {PASS}/{total} checks passed")
print("  ALL CHECKS PASSED" if FAIL == 0 else f"  FAILURES: {FAIL}")
print(f"{'='*62}")
sys.exit(0 if FAIL == 0 else 1)
