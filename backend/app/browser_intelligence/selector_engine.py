from __future__ import annotations

import hashlib
import re
from typing import Any

from app.browser_intelligence.models import SelectorCandidate


_UNSTABLE_SELECTOR_PATTERNS = (
    re.compile(r":nth-of-type\(\d+\)"),
    re.compile(r">\s*div(?:\[[^\]]+\])?(?:\s*>|$)"),
    re.compile(r"jfk|gb_|gNO89b|RNmpXc", re.IGNORECASE),
)


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{prefix}_{digest}"


class SelectorIntelligenceEngine:
    """Deterministic selector validation and ranking.

    The planner is still given selectors for Planner Contract V2 compatibility,
    but V4.5 also assigns selector IDs and confidence so selectors are generated
    by Browser Intelligence rather than invented downstream.
    """

    def build_candidates(self, page_context: Any) -> list[SelectorCandidate]:
        candidates: list[SelectorCandidate] = []
        seen: set[str] = set()
        for element in getattr(page_context, "interactive_elements", []) or []:
            selector = str(getattr(element, "selector", "") or "").strip()
            if not selector or selector in seen:
                continue
            seen.add(selector)
            candidates.append(self.candidate_for(selector))
        return candidates

    def candidate_for(self, selector: str) -> SelectorCandidate:
        strategy = self._strategy(selector)
        valid = self.validate(selector)
        confidence = self._confidence(selector, strategy, valid)
        reason = "valid_selector" if valid else "selector_failed_static_validation"
        if valid and confidence < 0.5:
            reason = "valid_but_unstable_selector"
        return SelectorCandidate(
            selector_id=stable_id("sel", selector),
            selector=selector,
            strategy=strategy,
            confidence=confidence,
            valid=valid,
            reason=reason,
        )

    def validate(self, selector: str) -> bool:
        selector = (selector or "").strip()
        if not selector:
            return False
        if selector in {"window", "document", "body"}:
            return True
        if selector.count("[") != selector.count("]"):
            return False
        if selector.count("(") != selector.count(")"):
            return False
        if len(selector) > 500:
            return False
        return True

    def _strategy(self, selector: str) -> str:
        lower = selector.lower()
        if selector.startswith("#"):
            return "id"
        if "data-testid" in lower:
            return "testid"
        if "aria-label" in lower:
            return "aria_label"
        if "placeholder" in lower:
            return "placeholder"
        if "title=" in lower:
            return "title"
        if "href=" in lower:
            return "href"
        if ":nth-of-type" in lower:
            return "structural"
        return "css"

    def _confidence(self, selector: str, strategy: str, valid: bool) -> float:
        if not valid:
            return 0.0
        base = {
            "id": 0.96,
            "testid": 0.95,
            "aria_label": 0.9,
            "placeholder": 0.86,
            "title": 0.84,
            "href": 0.82,
            "css": 0.68,
            "structural": 0.42,
        }.get(strategy, 0.5)
        if any(pattern.search(selector) for pattern in _UNSTABLE_SELECTOR_PATTERNS):
            base -= 0.2
        return max(0.0, min(1.0, round(base, 2)))
