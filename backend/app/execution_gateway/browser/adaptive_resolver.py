"""
Phase D — AdaptiveResolver (additive extension of the Phase C ElementResolver).

Extends the resolution priority with aria / label / placeholder / text strategies and
optional strict-uniqueness validation, while preserving the EXACT behaviour of every
Phase C strategy (same names, same relative order, same builders). The Phase C
ElementResolver and its RESOLUTION_PRIORITY are left untouched.

Priority (EXTENDED_RESOLUTION_PRIORITY):
  selector -> testid -> aria_label -> aria -> role -> label -> placeholder -> text
           -> id -> name -> css -> xpath

NO AI. NO OCR. NO self-healing. Deterministic.
Records which strategy succeeded (ResolvedElement.strategy) for analytics.
"""
from __future__ import annotations

from typing import Any, Optional

from app.execution_gateway.browser.capabilities import EXTENDED_RESOLUTION_PRIORITY
from app.execution_gateway.browser.resolver import (
    ElementResolutionError,
    ElementResolver,
    ResolvedElement,
    _escape,
)


class AdaptiveResolver(ElementResolver):

    PRIORITY = EXTENDED_RESOLUTION_PRIORITY

    def _build(self, page: Any, strategy: str, value: str, parameters: dict[str, Any]):
        # New Phase D strategies first; fall back to the inherited builders.
        if strategy == "aria":
            return page.get_by_label(value)          # aria-label is matched by get_by_label
        if strategy == "label":
            return page.get_by_label(value)
        if strategy == "placeholder":
            return page.get_by_placeholder(value)
        if strategy == "text":
            return page.get_by_text(value)
        return super()._build(page, strategy, value, parameters)

    def resolve_strict(self, page: Any, parameters: dict[str, Any]) -> ResolvedElement:
        """
        Resolve and validate strict uniqueness when requested (params['strict'] truthy).
        Strict uniqueness means the locator matches exactly one element. Raises
        ElementResolutionError on 0 or >1 matches so the failure engine can classify it.
        """
        resolved = self.resolve(page, parameters)
        if parameters.get("strict"):
            try:
                count = resolved.locator.count()
            except Exception:
                count = None
            if count is not None and count != 1:
                raise ElementResolutionError(
                    f"strict uniqueness failed: {resolved.strategy}='{resolved.value}' "
                    f"matched {count} elements (no node found / not unique)"
                )
        return resolved


# ── Module-level singleton ────────────────────────────────────────────────────

_resolver = AdaptiveResolver()


def resolve(page: Any, parameters: dict[str, Any]) -> ResolvedElement:
    return _resolver.resolve(page, parameters)

def resolve_strict(page: Any, parameters: dict[str, Any]) -> ResolvedElement:
    return _resolver.resolve_strict(page, parameters)

def strategy_for(parameters: dict[str, Any]) -> Optional[str]:
    return _resolver.strategy_for(parameters)
