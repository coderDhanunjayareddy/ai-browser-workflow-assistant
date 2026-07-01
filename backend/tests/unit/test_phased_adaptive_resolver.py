"""Phase D — Unit tests: adaptive_resolver.py (AdaptiveResolver)."""
import pytest
from app.execution_gateway.browser import adaptive_resolver as ar
from app.execution_gateway.browser.resolver import ElementResolutionError
from app.execution_gateway.browser.capabilities import EXTENDED_RESOLUTION_PRIORITY, RESOLUTION_PRIORITY


class FakeLocator:
    def __init__(self, kind, value, count=1): self.kind = kind; self.value = value; self._count = count
    def count(self): return self._count


class FakePage:
    def __init__(self, count=1): self._count = count
    def locator(self, sel): return FakeLocator("locator", sel, self._count)
    def get_by_test_id(self, v): return FakeLocator("testid", v, self._count)
    def get_by_label(self, v): return FakeLocator("label", v, self._count)
    def get_by_role(self, v, name=None): return FakeLocator("role", (v, name), self._count)
    def get_by_placeholder(self, v): return FakeLocator("placeholder", v, self._count)
    def get_by_text(self, v): return FakeLocator("text", v, self._count)


class TestExtendedPriority:
    def test_priority_is_extended(self):
        assert ar.AdaptiveResolver.PRIORITY == EXTENDED_RESOLUTION_PRIORITY

    def test_preserves_phase_c_relative_order(self):
        # every Phase C strategy keeps its relative order in the extended chain
        ext = list(EXTENDED_RESOLUTION_PRIORITY)
        positions = [ext.index(s) for s in RESOLUTION_PRIORITY]
        assert positions == sorted(positions)

    def test_twelve_strategies(self):
        assert len(EXTENDED_RESOLUTION_PRIORITY) == 12


class TestNewStrategies:
    def test_aria(self):
        r = ar.resolve(FakePage(), {"aria": "Name"})
        assert r.strategy == "aria"
        assert r.locator.kind == "label"

    def test_label(self):
        r = ar.resolve(FakePage(), {"label": "Email"})
        assert r.strategy == "label"
        assert r.locator.kind == "label"

    def test_placeholder(self):
        r = ar.resolve(FakePage(), {"placeholder": "Search"})
        assert r.strategy == "placeholder"
        assert r.locator.kind == "placeholder"

    def test_text(self):
        r = ar.resolve(FakePage(), {"text": "Submit"})
        assert r.strategy == "text"
        assert r.locator.kind == "text"


class TestBackwardCompatibility:
    @pytest.mark.parametrize("params,expected", [
        ({"selector": "#x"}, "selector"),
        ({"testid": "go"}, "testid"),
        ({"aria_label": "Name"}, "aria_label"),
        ({"role": "button"}, "role"),
        ({"id": "email"}, "id"),
        ({"name": "q"}, "name"),
        ({"css": ".b"}, "css"),
        ({"xpath": "//a"}, "xpath"),
    ])
    def test_phase_c_params_resolve_same(self, params, expected):
        assert ar.resolve(FakePage(), params).strategy == expected

    def test_priority_selector_first(self):
        # selector beats every later strategy
        params = {k: "v" for k in EXTENDED_RESOLUTION_PRIORITY}
        assert ar.resolve(FakePage(), params).strategy == "selector"

    def test_full_priority_walk(self):
        params = {k: "v" for k in EXTENDED_RESOLUTION_PRIORITY}
        for expected in EXTENDED_RESOLUTION_PRIORITY:
            assert ar.resolve(FakePage(), params).strategy == expected
            del params[expected]


class TestStrictUniqueness:
    def test_strict_unique_ok(self):
        r = ar.resolve_strict(FakePage(count=1), {"testid": "x", "strict": True})
        assert r.strategy == "testid"

    def test_strict_zero_raises(self):
        with pytest.raises(ElementResolutionError):
            ar.resolve_strict(FakePage(count=0), {"testid": "x", "strict": True})

    def test_strict_multiple_raises(self):
        with pytest.raises(ElementResolutionError):
            ar.resolve_strict(FakePage(count=3), {"testid": "x", "strict": True})

    def test_non_strict_allows_multiple(self):
        r = ar.resolve_strict(FakePage(count=3), {"testid": "x"})
        assert r.strategy == "testid"

    def test_strict_count_error_tolerant(self):
        # a locator without count() must not crash strict resolution
        class NoCountPage(FakePage):
            def get_by_test_id(self, v):
                class L: pass
                return L()
        r = ar.resolve_strict(NoCountPage(), {"testid": "x", "strict": True})
        assert r.strategy == "testid"


class TestStrategyFor:
    def test_strategy_for_extended(self):
        assert ar.strategy_for({"placeholder": "x"}) == "placeholder"
        assert ar.strategy_for({"text": "x"}) == "text"

    def test_strategy_for_none(self):
        assert ar.strategy_for({"url": "x"}) is None

    def test_strategy_for_priority(self):
        assert ar.strategy_for({"selector": "a", "text": "b"}) == "selector"
