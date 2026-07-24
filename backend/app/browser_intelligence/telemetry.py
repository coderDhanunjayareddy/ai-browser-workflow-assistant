from __future__ import annotations

from typing import Any

from app.browser_intelligence.models import SemanticPageModel


def telemetry_summary(page_model: SemanticPageModel) -> dict[str, Any]:
    candidates = page_model.selector_candidates
    valid_count = sum(1 for candidate in candidates if candidate.valid)
    recovery_risk_count = sum(1 for candidate in candidates if candidate.confidence < 0.5)
    return {
        "extraction_latency_ms": page_model.telemetry.get("extraction_latency_ms", 0),
        "classification_latency_ms": page_model.telemetry.get("extraction_latency_ms", 0),
        "classification_confidence": page_model.classification.confidence,
        "adapter": page_model.adapter,
        "adapter_usage": {page_model.adapter: 1},
        "selector_candidate_count": len(candidates),
        "selector_valid_count": valid_count,
        "selector_recovery_risk_count": recovery_risk_count,
        "search_result_count": len(page_model.search_results),
        "false_success_prevention_candidates": recovery_risk_count,
    }
