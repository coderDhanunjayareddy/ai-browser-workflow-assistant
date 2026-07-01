"""Phase D — Unit tests: PlaywrightAdapter with Phase D enabled (adaptive/recovery/validation).

Uses fake page/session objects (no real browser). Verifies the additive Phase D path:
adaptive resolution, deterministic recovery + retry, first-class post-validation, and
monitor/metrics/timeline wiring.
"""
import pytest
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl
from app.execution_gateway.models import make_command, CommandType, RetryConfig


@pytest.fixture(autouse=True)
def clean():
    mon._reset_for_testing(); met._reset_for_testing(); etl._reset_for_testing()
    yield
    mon._reset_for_testing(); met._reset_for_testing(); etl._reset_for_testing()


class FakeLocator:
    def __init__(self, page): self.page = page
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


class FakePage:
    def __init__(self, *, url="https://x/p", body="ok", element_count=1, field_value="",
                 click_fail_times=0, click_fail_msg="no node found"):
        self.url = url; self.body = body; self.element_count = element_count
        self.field_value = field_value; self.click_calls = 0
        self.click_fail_times = click_fail_times; self.click_fail_msg = click_fail_msg
        self.filled = None; self.scrolled = False; self.events = []
    def is_closed(self): return False
    def goto(self, url, **k): self.url = url
    def title(self): return "T"
    def locator(self, s): return FakeLocator(self)
    def get_by_test_id(self, v): return FakeLocator(self)
    def get_by_label(self, v): return FakeLocator(self)
    def get_by_role(self, v, name=None): return FakeLocator(self)
    def get_by_placeholder(self, v): return FakeLocator(self)
    def get_by_text(self, v): return FakeLocator(self)
    def inner_text(self, sel): return self.body
    def content(self): return f"<html>{self.body}</html>"
    def wait_for_timeout(self, ms): self.events.append(("wait", ms))
    def wait_for_load_state(self, s, timeout=None): self.events.append(("networkidle",))
    def evaluate(self, js): self.events.append(("eval",))


class FakeSession:
    def __init__(self, page): self.page = page; self.active_tab_id = "tab-0"; self.downloads = []; self.context = None
    def ensure_page(self): return self.page
    def screenshot(self, label=""): return f"/tmp/{label}.png"
    def refresh(self): self.page.events.append(("refresh",))


class FakeMgr:
    def __init__(self, page): self.session = FakeSession(page)
    def get_or_create(self, eid, headless=True): return self.session
    def get(self, eid): return self.session
    def close(self, eid): return True


def _adapter(page, **flags):
    base = dict(adaptive=True, recovery=True, post_validation=True, retry_config=RetryConfig(max_retries=2))
    base.update(flags)
    return PlaywrightAdapter(execution_id="e1", session_manager=FakeMgr(page), **base)


def _cmd(ctype, params=None, expected="", strategy="NONE", step_id="s1", order=1):
    return make_command(ctype, step_id, order, "tgt", parameters=params or {},
                        expected_result=expected, validation_strategy=strategy)


class TestPhaseDEngaged:
    def test_uses_adaptive_path(self):
        a = _adapter(FakePage())
        assert a.phase_d is True

    def test_success_records_monitor(self):
        a = _adapter(FakePage())
        a.navigate(_cmd(CommandType.navigate, {"url": "https://x.com"}))
        assert len(mon.steps_for("e1")) == 1
        assert mon.steps_for("e1")[0].outcome == "completed"

    def test_success_records_metrics(self):
        a = _adapter(FakePage())
        a.click(_cmd(CommandType.click, {"testid": "go"}))
        m = met.get_metrics()
        assert m["steps_total"] == 1
        assert m["steps_succeeded"] == 1
        assert m["locator_strategy_counts"].get("testid") == 1

    def test_success_records_timeline(self):
        a = _adapter(FakePage())
        a.click(_cmd(CommandType.click, {"testid": "go"}))
        types = etl.summary("e1")["type_counts"]
        assert "started" in types and "completed" in types

    def test_output_has_phase_d_fields(self):
        a = _adapter(FakePage())
        r = a.click(_cmd(CommandType.click, {"testid": "go"}))
        for k in ["attempts", "recoveries", "recovery_used", "locator_strategy"]:
            assert k in r.output


class TestAdaptiveResolution:
    def test_adaptive_strategy_recorded(self):
        a = _adapter(FakePage())
        r = a.click(_cmd(CommandType.click, {"testid": "go"}))
        assert r.output["details"]["strategy"] == "testid"

    def test_new_strategy_placeholder(self):
        a = _adapter(FakePage())
        r = a.click(_cmd(CommandType.click, {"placeholder": "Search"}))
        assert r.output["details"]["strategy"] == "placeholder"


class TestRecoveryRetry:
    def test_recovers_and_succeeds(self):
        # click fails once (ElementNotFound) then succeeds → recovery + retry
        page = FakePage(click_fail_times=1, click_fail_msg="no node found")
        a = _adapter(page)
        r = a.click(_cmd(CommandType.click, {"testid": "go"}))
        assert r.success is True
        assert r.output["attempts"] == 2
        assert len(r.output["recovery_used"]) >= 1

    def test_recovery_recorded_in_metrics(self):
        page = FakePage(click_fail_times=1)
        _adapter(page).click(_cmd(CommandType.click, {"testid": "go"}))
        m = met.get_metrics()
        assert m["recoveries_attempted"] >= 1

    def test_hidden_element_scrolls(self):
        page = FakePage(click_fail_times=1, click_fail_msg="element is hidden / not visible")
        a = _adapter(page)
        r = a.click(_cmd(CommandType.click, {"testid": "go"}))
        assert r.success is True
        assert page.scrolled is True
        assert "SCROLL_INTO_VIEW" in r.output["recovery_used"]

    def test_retry_exhausted_fails(self):
        page = FakePage(click_fail_times=9, click_fail_msg="no node found")
        a = _adapter(page, retry_config=RetryConfig(max_retries=2))
        r = a.click(_cmd(CommandType.click, {"testid": "go"}))
        assert r.success is False
        assert r.output["attempts"] == 3   # bounded — never infinite
        assert r.output["failure_category"] == "ElementNotFound"

    def test_permanent_fails_immediately(self):
        page = FakePage(click_fail_times=9, click_fail_msg="is not a valid selector")
        a = _adapter(page, retry_config=RetryConfig(max_retries=2))
        r = a.click(_cmd(CommandType.click, {"selector": ".x"}))
        assert r.success is False
        assert r.output["attempts"] == 1   # permanent → no retry
        assert r.output["failure_category"] == "InvalidSelector"

    def test_failure_records_distribution(self):
        page = FakePage(click_fail_times=9, click_fail_msg="is not a valid selector")
        _adapter(page).click(_cmd(CommandType.click, {"selector": ".x"}))
        assert met.get_metrics()["failure_distribution"].get("InvalidSelector", 0) >= 1


class TestPostValidation:
    def test_validate_after_pass(self):
        page = FakePage(url="https://x/cart")
        a = _adapter(page)
        r = a.navigate(_cmd(CommandType.navigate,
                            {"url": "https://x/cart", "validate_after": {"url_contains": "cart"}}))
        assert r.validation_passed is True
        assert r.output["post_validation"]["passed"] is True

    def test_validate_after_fail(self):
        page = FakePage(url="https://x/home")
        a = _adapter(page, retry_config=RetryConfig(max_retries=0))
        r = a.navigate(_cmd(CommandType.navigate,
                            {"url": "https://x/home", "validate_after": {"url_contains": "cart"}}))
        # dispatch ok but post-validation failed → success True, validation_passed False
        assert r.success is True
        assert r.validation_passed is False

    def test_value_equals_validation(self):
        page = FakePage(field_value="hi@x.com")
        a = _adapter(page)
        r = a.type(_cmd(CommandType.type,
                        {"id": "email", "value": "hi@x.com", "validate_after": {"value_equals": "hi@x.com"}}))
        assert r.validation_passed is True

    def test_validation_records_metrics(self):
        page = FakePage(url="https://x/cart")
        _adapter(page).navigate(_cmd(CommandType.navigate,
                 {"url": "https://x/cart", "validate_after": {"url_contains": "cart"}}))
        assert met.get_metrics()["validations_attempted"] >= 1


class TestBackwardCompatOff:
    def test_flags_off_is_phase_c(self):
        a = PlaywrightAdapter(execution_id="e2", session_manager=FakeMgr(FakePage()))
        assert a.phase_d is False
        # no monitor records when Phase D disabled
        a.click(_cmd(CommandType.click, {"testid": "go"}))
        assert mon.steps_for("e2") == []
