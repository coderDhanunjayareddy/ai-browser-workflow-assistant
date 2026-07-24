from __future__ import annotations

import hashlib
from typing import Any

from app.browser_intelligence.models import DomMutationSignal, SemanticPageModel


class DynamicDomTracker:
    """Detect meaningful semantic changes between page observations.

    This is intentionally deterministic and lightweight. Runtime browser-side
    MutationObserver streaming can feed the same model later; today it compares
    bounded semantic signatures so stale page understanding can be detected.
    """

    def __init__(self) -> None:
        self._last_signature_by_scope: dict[str, str] = {}
        self._last_counts_by_scope: dict[str, dict[str, int]] = {}

    def track(self, scope_id: str, page_model: SemanticPageModel) -> list[DomMutationSignal]:
        signature = semantic_signature(page_model)
        counts = semantic_counts(page_model)
        previous_signature = self._last_signature_by_scope.get(scope_id)
        previous_counts = self._last_counts_by_scope.get(scope_id, {})
        self._last_signature_by_scope[scope_id] = signature
        self._last_counts_by_scope[scope_id] = counts
        if previous_signature is None:
            return [
                DomMutationSignal(
                    mutation_id=_id("initial", signature),
                    mutation_type="initial_observation",
                    target_hint=page_model.classification.page_type,
                    impact_score=0.2,
                    requires_refresh=False,
                    metadata={"signature": signature, "counts": counts},
                )
            ]
        if previous_signature == signature:
            return []

        delta = {
            key: counts.get(key, 0) - previous_counts.get(key, 0)
            for key in sorted(set(counts) | set(previous_counts))
        }
        impact = min(1.0, 0.25 + sum(abs(v) for v in delta.values()) / 40)
        meaningful = any(value != 0 for value in delta.values()) or impact >= 0.3 or bool(page_model.search_results)
        mutation_type = "semantic_model_changed"
        if delta.get("search_result", 0):
            mutation_type = "search_results_changed"
        elif delta.get("list", 0) or delta.get("table", 0):
            mutation_type = "collection_changed"
        elif delta.get("dialog", 0):
            mutation_type = "dialog_changed"

        return [
            DomMutationSignal(
                mutation_id=_id(mutation_type, f"{previous_signature}->{signature}"),
                mutation_type=mutation_type,
                target_hint=page_model.classification.page_type,
                impact_score=round(impact, 3),
                requires_refresh=meaningful,
                metadata={"previous_signature": previous_signature, "signature": signature, "delta": delta},
            )
        ]


def semantic_signature(page_model: SemanticPageModel) -> str:
    parts = [
        page_model.url,
        page_model.title,
        page_model.classification.page_type,
        page_model.adapter,
    ]
    parts.extend(
        f"{element.kind}:{element.label[:80]}:{element.href or element.selector or ''}"
        for element in page_model.elements[:80]
    )
    parts.extend(f"result:{result.rank}:{result.url}" for result in page_model.search_results[:20])
    return hashlib.sha1("|".join(parts).encode("utf-8", errors="ignore")).hexdigest()


def semantic_counts(page_model: SemanticPageModel) -> dict[str, int]:
    counts: dict[str, int] = {}
    for element in page_model.elements:
        counts[element.kind] = counts.get(element.kind, 0) + 1
    if page_model.search_results:
        counts["search_result"] = len(page_model.search_results)
    return counts


def _id(prefix: str, value: str) -> str:
    return f"mut_{hashlib.sha1((prefix + value).encode('utf-8', errors='ignore')).hexdigest()[:12]}"
