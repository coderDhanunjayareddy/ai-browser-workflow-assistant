"""Phase D — Unit tests: execution_validation.py (first-class post-action validation)."""
import os
import tempfile
import pytest
from app.execution_gateway.browser import execution_validation as ev


class FakeLocator:
    def __init__(self, count=1, value=""): self._count = count; self._value = value
    def count(self): return self._count
    def input_value(self): return self._value


class FakePage:
    def __init__(self, url="https://x/p", body="ok", count=1, value=""):
        self.url = url; self.body = body; self._count = count; self._value = value
    def is_closed(self): return False
    def inner_text(self, sel): return self.body
    def locator(self, s): return FakeLocator(self._count, self._value)
    def get_by_test_id(self, v): return FakeLocator(self._count, self._value)
    def get_by_label(self, v): return FakeLocator(self._count, self._value)


class FakeSession:
    def __init__(self, page): self.page = page
    def ensure_page(self): return self.page


class _Cmd:
    def __init__(self, params): self.parameters = params


def _v(page, params, **kw):
    return ev.validate("click", FakeSession(page), _Cmd(params), **kw)


class TestNoOp:
    def test_no_validate_after_is_noop(self):
        r = _v(FakePage(), {"testid": "x"})
        assert r.performed is False
        assert r.passed is True
        assert r.strategy == "none"

    def test_empty_validate_after_noop(self):
        r = _v(FakePage(), {"validate_after": {}})
        assert r.performed is False


class TestUrlChecks:
    def test_url_contains_pass(self):
        r = _v(FakePage(url="https://shop.io/cart"), {"validate_after": {"url_contains": "cart"}})
        assert r.performed and r.passed

    def test_url_contains_fail(self):
        r = _v(FakePage(url="https://shop.io/home"), {"validate_after": {"url_contains": "cart"}})
        assert r.performed and not r.passed

    def test_url_changed_pass(self):
        r = _v(FakePage(url="https://x/after"), {"validate_after": {"url_changed": True}},
               pre_state={"url": "https://x/before"})
        assert r.passed

    def test_url_changed_fail(self):
        r = _v(FakePage(url="https://x/same"), {"validate_after": {"url_changed": True}},
               pre_state={"url": "https://x/same"})
        assert not r.passed


class TestTextChecks:
    def test_text_contains_pass(self):
        r = _v(FakePage(body="Order placed successfully"), {"validate_after": {"text_contains": "successfully"}})
        assert r.passed

    def test_text_contains_fail(self):
        r = _v(FakePage(body="error"), {"validate_after": {"text_contains": "successfully"}})
        assert not r.passed

    def test_text_absent_pass(self):
        r = _v(FakePage(body="all good"), {"validate_after": {"text_absent": "error"}})
        assert r.passed

    def test_text_absent_fail(self):
        r = _v(FakePage(body="an error occurred"), {"validate_after": {"text_absent": "error"}})
        assert not r.passed


class TestElementChecks:
    def test_exists_pass(self):
        r = _v(FakePage(count=1), {"validate_after": {"exists": {"testid": "toast"}}})
        assert r.passed

    def test_exists_fail(self):
        r = _v(FakePage(count=0), {"validate_after": {"exists": {"testid": "toast"}}})
        assert not r.passed

    def test_gone_pass(self):
        r = _v(FakePage(count=0), {"validate_after": {"gone": {"testid": "spinner"}}})
        assert r.passed

    def test_gone_fail(self):
        r = _v(FakePage(count=2), {"validate_after": {"gone": {"testid": "spinner"}}})
        assert not r.passed


class TestValueAndFiles:
    def test_value_equals_str(self):
        r = _v(FakePage(value="hi@x.com"),
               {"id": "email", "validate_after": {"value_equals": "hi@x.com"}})
        assert r.passed

    def test_value_equals_mismatch(self):
        r = _v(FakePage(value="other"),
               {"id": "email", "validate_after": {"value_equals": "hi@x.com"}})
        assert not r.passed

    def test_value_equals_dict(self):
        r = _v(FakePage(value="abc"),
               {"validate_after": {"value_equals": {"testid": "f", "value": "abc"}}})
        assert r.passed

    def test_filename_visible(self):
        r = _v(FakePage(body="Uploaded: report.csv"), {"validate_after": {"filename_visible": "report.csv"}})
        assert r.passed

    def test_file_exists_explicit(self):
        f = os.path.join(tempfile.gettempdir(), "phased_exec_val.txt")
        with open(f, "w") as fh:
            fh.write("x")
        r = _v(FakePage(), {"validate_after": {"file_exists": f}})
        assert r.passed
        os.remove(f)

    def test_file_exists_from_details(self):
        f = os.path.join(tempfile.gettempdir(), "phased_dl.txt")
        with open(f, "w") as fh:
            fh.write("x")
        r = _v(FakePage(), {"validate_after": {"file_exists": True}}, result_details={"download_path": f})
        assert r.passed
        os.remove(f)

    def test_file_exists_missing(self):
        r = _v(FakePage(), {"validate_after": {"file_exists": "/no/such/file/xyz.bin"}})
        assert not r.passed


class TestCombined:
    def test_multiple_checks_all_pass(self):
        r = _v(FakePage(url="https://x/cart", body="Added", count=1),
               {"validate_after": {"url_contains": "cart", "text_contains": "Added",
                                   "exists": {"testid": "badge"}}})
        assert r.performed and r.passed
        assert len(r.checks) == 3

    def test_one_failing_fails_all(self):
        r = _v(FakePage(url="https://x/cart", body="Added"),
               {"validate_after": {"url_contains": "cart", "text_contains": "MISSING"}})
        assert not r.passed

    def test_to_dict(self):
        r = _v(FakePage(), {"validate_after": {"url_contains": "x"}})
        d = r.to_dict()
        for k in ["performed", "passed", "strategy", "checks", "details"]:
            assert k in d
