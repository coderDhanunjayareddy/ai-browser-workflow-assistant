from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from app.browser_intelligence.models import RecoveryDecision, SemanticPageModel
from app.browser_intelligence.selector_engine import SelectorIntelligenceEngine


class AdaptiveRecoveryEngine:
    hierarchy = (
        "original_selector",
        "stable_selector",
        "semantic_selector",
        "accessibility_selector",
        "text_matching",
        "nearby_element_search",
        "similar_element_search",
        "adapter_assisted_lookup",
    )

    def recover(self, *, failed_selector: str | None, target_label: str | None, page_model: SemanticPageModel) -> RecoveryDecision:
        attempts: list[dict[str, Any]] = []
        selector_engine = SelectorIntelligenceEngine()

        if failed_selector:
            original = selector_engine.candidate_for(failed_selector)
            attempts.append({"strategy": "original_selector", "selector": failed_selector, "valid": original.valid, "confidence": original.confidence})
            if original.valid and original.confidence >= 0.75:
                return _decision(True, "original_selector", failed_selector, original.selector_id, original.confidence, attempts)

        stable = [candidate for candidate in page_model.selector_candidates if candidate.valid and candidate.confidence >= 0.75]
        if target_label:
            matching = [
                element for element in page_model.elements
                if element.selector and _similar(target_label, element.label) >= 0.72
            ]
            for strategy in self.hierarchy[1:]:
                candidate = _best_for_strategy(strategy, matching, stable, page_model)
                attempts.append({
                    "strategy": strategy,
                    "candidate_count": len(matching) if "selector" not in strategy else len(stable),
                    "selector": candidate.selector if candidate else None,
                    "confidence": candidate.confidence if candidate else 0,
                })
                if candidate and candidate.selector:
                    return _decision(True, strategy, candidate.selector, candidate.selector_id, candidate.confidence, attempts)
        else:
            for candidate in stable[:1]:
                attempts.append({"strategy": "stable_selector", "selector": candidate.selector, "confidence": candidate.confidence})
                return _decision(True, "stable_selector", candidate.selector, candidate.selector_id, candidate.confidence, attempts)

        return _decision(False, "replan_required", None, None, 0.0, attempts)


def _best_for_strategy(strategy: str, matching: list[Any], stable: list[Any], page_model: SemanticPageModel) -> Any | None:
    if strategy == "stable_selector" and stable:
        return stable[0]
    if strategy in {"semantic_selector", "accessibility_selector", "text_matching", "nearby_element_search", "similar_element_search"} and matching:
        return sorted(matching, key=lambda element: element.confidence, reverse=True)[0]
    if strategy == "adapter_assisted_lookup" and page_model.search_results:
        result = page_model.search_results[0]
        return type("Candidate", (), {
            "selector": result.open_selector,
            "selector_id": result.selector_id,
            "confidence": 0.9,
        })()
    return None


def _similar(left: str, right: str) -> float:
    left_norm = " ".join((left or "").lower().split())
    right_norm = " ".join((right or "").lower().split())
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.9
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _decision(
    recovered: bool,
    strategy: str,
    selector: str | None,
    selector_id: str | None,
    confidence: float,
    attempts: list[dict[str, Any]],
) -> RecoveryDecision:
    return RecoveryDecision(
        recovered=recovered,
        strategy=strategy,
        selector=selector,
        selector_id=selector_id,
        confidence=round(confidence, 2),
        attempts=attempts,
        replay_metadata={"attempt_count": len(attempts), "hierarchy_version": "v46.recovery.v1"},
    )
