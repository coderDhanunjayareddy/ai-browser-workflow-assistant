from __future__ import annotations

from typing import Any


def score_benchmark(metrics: dict[str, Any]) -> float:
    weights = {
        "mission_success_rate": 0.2,
        "completion_accuracy": 0.14,
        "decision_agreement": 0.12,
        "evidence_coverage": 0.1,
        "evidence_confidence": 0.08,
        "blueprint_readiness": 0.08,
        "validation_accuracy": 0.08,
        "runtime_stability": 0.12,
        "failure_recovery_rate": 0.08,
    }
    score = 0.0
    for key, weight in weights.items():
        score += min(max(float(metrics.get(key) or 0.0), 0.0), 1.0) * weight
    penalty = min(float(metrics.get("high_confidence_disagreement") or 0.0) * 0.03, 0.2)
    return round(max(score - penalty, 0.0), 4)
