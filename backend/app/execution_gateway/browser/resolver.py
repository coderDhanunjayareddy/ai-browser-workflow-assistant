"""
Phase C — ElementResolver.

Deterministic element resolution. NEVER uses AI. NEVER uses OCR. NEVER self-heals.

Priority order (first present wins):
  1. selector     (explicit Playwright selector)   -> page.locator(value)
  2. testid       (data-testid)                     -> page.get_by_test_id(value)
  3. aria_label   (aria-label)                      -> page.get_by_label(value)
  4. role                                           -> page.get_by_role(value, name=role_name?)
  5. id                                             -> page.locator("#value")
  6. name                                           -> page.locator('[name="value"]')
  7. css                                            -> page.locator(value)
  8. xpath                                          -> page.locator("xpath=value")

The resolver only builds a locator; it does not act. It is fully unit-testable with a
duck-typed fake page that records which builder was called.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.execution_gateway.browser.capabilities import RESOLUTION_PRIORITY


class ElementResolutionError(Exception):
    """Raised when no resolution parameter is present in a command."""


@dataclass
class ResolvedElement:
    locator:  Any     # a Playwright Locator (or fake in tests)
    strategy: str     # which priority strategy matched
    value:    str     # the value used


def _escape(value: str) -> str:
    # Minimal attribute-value escaping for id/name CSS construction.
    return value.replace('"', '\\"')


class ElementResolver:

    PRIORITY = RESOLUTION_PRIORITY

    def resolve(self, page: Any, parameters: dict[str, Any]) -> ResolvedElement:
        for strategy in self.PRIORITY:
            value = parameters.get(strategy)
            if value:
                locator = self._build(page, strategy, value, parameters)
                return ResolvedElement(locator=locator, strategy=strategy, value=str(value))
        raise ElementResolutionError(
            "no resolution parameter present; expected one of "
            f"{', '.join(self.PRIORITY)}"
        )

    def strategy_for(self, parameters: dict[str, Any]) -> Optional[str]:
        for strategy in self.PRIORITY:
            if parameters.get(strategy):
                return strategy
        return None

    def _build(self, page: Any, strategy: str, value: str, parameters: dict[str, Any]):
        if strategy == "selector":
            return page.locator(value)
        if strategy == "testid":
            return page.get_by_test_id(value)
        if strategy == "aria_label":
            return page.get_by_label(value)
        if strategy == "role":
            role_name = parameters.get("role_name")
            if role_name:
                return page.get_by_role(value, name=role_name)
            return page.get_by_role(value)
        if strategy == "id":
            return page.locator(f"#{value}")
        if strategy == "name":
            return page.locator(f'[name="{_escape(value)}"]')
        if strategy == "css":
            return page.locator(value)
        if strategy == "xpath":
            return page.locator(f"xpath={value}")
        # unreachable given PRIORITY membership
        raise ElementResolutionError(f"unknown strategy: {strategy}")


# ── Module-level singleton ────────────────────────────────────────────────────

_resolver = ElementResolver()


def resolve(page: Any, parameters: dict[str, Any]) -> ResolvedElement:
    return _resolver.resolve(page, parameters)

def strategy_for(parameters: dict[str, Any]) -> Optional[str]:
    return _resolver.strategy_for(parameters)
