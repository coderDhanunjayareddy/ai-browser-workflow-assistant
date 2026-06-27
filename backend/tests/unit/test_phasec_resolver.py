"""Phase C — Unit tests: resolver.py (deterministic element resolution)."""
import pytest
from app.execution_gateway.browser import resolver as resolver_module
from app.execution_gateway.browser.resolver import ElementResolver, ElementResolutionError


class FakeLocator:
    def __init__(self, kind, value): self.kind = kind; self.value = value


class FakePage:
    """Records which builder method the resolver chose."""
    def locator(self, sel):            return FakeLocator("locator", sel)
    def get_by_test_id(self, v):       return FakeLocator("testid", v)
    def get_by_label(self, v):         return FakeLocator("label", v)
    def get_by_role(self, v, name=None): return FakeLocator("role", (v, name))


@pytest.fixture
def page():
    return FakePage()


class TestPriority:
    def test_selector_first(self, page):
        r = resolver_module.resolve(page, {"selector": "#a", "testid": "b", "id": "c"})
        assert r.strategy == "selector"
        assert r.locator.kind == "locator"
        assert r.locator.value == "#a"

    def test_testid_over_arialabel(self, page):
        r = resolver_module.resolve(page, {"testid": "t", "aria_label": "a"})
        assert r.strategy == "testid"
        assert r.locator.kind == "testid"

    def test_arialabel_over_role(self, page):
        r = resolver_module.resolve(page, {"aria_label": "Name", "role": "button"})
        assert r.strategy == "aria_label"
        assert r.locator.kind == "label"

    def test_role(self, page):
        r = resolver_module.resolve(page, {"role": "button"})
        assert r.strategy == "role"
        assert r.locator.kind == "role"

    def test_role_with_name(self, page):
        r = resolver_module.resolve(page, {"role": "button", "role_name": "Submit"})
        assert r.locator.value == ("button", "Submit")

    def test_id(self, page):
        r = resolver_module.resolve(page, {"id": "email"})
        assert r.strategy == "id"
        assert r.locator.value == "#email"

    def test_name(self, page):
        r = resolver_module.resolve(page, {"name": "q"})
        assert r.strategy == "name"
        assert r.locator.value == '[name="q"]'

    def test_css(self, page):
        r = resolver_module.resolve(page, {"css": ".btn"})
        assert r.strategy == "css"
        assert r.locator.value == ".btn"

    def test_xpath(self, page):
        r = resolver_module.resolve(page, {"xpath": "//button"})
        assert r.strategy == "xpath"
        assert r.locator.value == "xpath=//button"


class TestFullPriorityOrder:
    def test_full_order(self, page):
        # All present → selector wins; remove one at a time down the chain
        params = {"selector": "s", "testid": "t", "aria_label": "a", "role": "r",
                  "id": "i", "name": "n", "css": "c", "xpath": "x"}
        order = ["selector", "testid", "aria_label", "role", "id", "name", "css", "xpath"]
        for expected in order:
            r = resolver_module.resolve(page, params)
            assert r.strategy == expected
            del params[expected]


class TestErrors:
    def test_no_params_raises(self, page):
        with pytest.raises(ElementResolutionError):
            resolver_module.resolve(page, {})

    def test_strategy_for(self):
        assert resolver_module.strategy_for({"id": "x"}) == "id"
        assert resolver_module.strategy_for({"selector": "s", "id": "x"}) == "selector"

    def test_strategy_for_none(self):
        assert resolver_module.strategy_for({"url": "x"}) is None

    def test_empty_value_skipped(self, page):
        # empty selector skipped, falls to id
        r = resolver_module.resolve(page, {"selector": "", "id": "x"})
        assert r.strategy == "id"

    def test_name_escaping(self, page):
        r = resolver_module.resolve(page, {"name": 'a"b'})
        assert '\\"' in r.locator.value
