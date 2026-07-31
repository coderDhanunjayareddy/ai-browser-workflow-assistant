from __future__ import annotations

from typing import Any


def benchmark_score(metrics: dict[str, Any]) -> float:
    weights = {
        "mission_success_rate": 0.16,
        "blueprint_accuracy": 0.12,
        "intent_expansion_accuracy": 0.12,
        "ledger_consistency": 0.12,
        "evidence_coverage": 0.10,
        "evidence_confidence": 0.08,
        "validation_accuracy": 0.08,
        "mission_completion_accuracy": 0.10,
        "agreement_rate": 0.06,
        "reliability_score": 0.06,
    }
    score = sum(min(max(float(metrics.get(key) or 0.0), 0.0), 1.0) * weight for key, weight in weights.items())
    return round(score, 4)
