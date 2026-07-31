from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from app.cognitive_runtime.comparison_models import DecisionComparison


def compute_comparison_metrics(comparisons: list[DecisionComparison]) -> dict[str, Any]:
    total = len(comparisons)
    agreement_counts = Counter(item.agreement for item in comparisons)
    runtime_counts = Counter(item.runtime_decision for item in comparisons)
    cognitive_counts = Counter(item.cognitive_decision for item in comparisons)
    by_type: dict[str, Counter[str]] = defaultdict(Counter)
    for item in comparisons:
        by_type[item.runtime_decision][item.agreement] += 1
    high_confidence_disagreements = [
        item for item in comparisons if item.confidence >= 0.75 and item.agreement == "disagreement"
    ]
    latencies = [
        float(item.metadata.get("recommendation_latency_ms") or 0.0)
        for item in comparisons
        if isinstance(item.metadata, dict)
    ]
    confidences = [item.confidence for item in comparisons]
    return {
        "total_comparisons": total,
        "overall_agreement": _ratio(agreement_counts["exact"] + agreement_counts["semantic"], total),
        "exact_agreement": _ratio(agreement_counts["exact"], total),
        "semantic_agreement": _ratio(agreement_counts["semantic"], total),
        "partial_agreement": _ratio(agreement_counts["partial"], total),
        "disagreement_rate": _ratio(agreement_counts["disagreement"], total),
        "agreement_by_decision_type": {
            decision: {
                "total": sum(counter.values()),
                "exact": counter["exact"],
                "semantic": counter["semantic"],
                "partial": counter["partial"],
                "disagreement": counter["disagreement"],
                "agreement_rate": _ratio(counter["exact"] + counter["semantic"], sum(counter.values())),
            }
            for decision, counter in sorted(by_type.items())
        },
        "high_confidence_disagreement": len(high_confidence_disagreements),
        "confidence_distribution": _confidence_distribution(confidences),
        "recommendation_frequency": dict(sorted(cognitive_counts.items())),
        "runtime_decision_frequency": dict(sorted(runtime_counts.items())),
        "false_positive_candidates": [
            item.to_dict()
            for item in high_confidence_disagreements
            if item.cognitive_decision in {"REPLAN", "RECOVER", "FAILED", "BLOCKED"}
        ],
        "false_negative_candidates": [
            item.to_dict()
            for item in comparisons
            if item.confidence >= 0.75
            and item.agreement == "disagreement"
            and item.runtime_decision in {"REPLAN", "RECOVER", "FAILED", "BLOCKED"}
        ],
        "average_confidence": round(mean(confidences), 4) if confidences else 0.0,
        "recommendation_latency": {
            "average_ms": round(mean(latencies), 2) if latencies else 0.0,
            "samples": len(latencies),
        },
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _confidence_distribution(values: list[float]) -> dict[str, int]:
    buckets = {"0.00-0.24": 0, "0.25-0.49": 0, "0.50-0.74": 0, "0.75-1.00": 0}
    for value in values:
        if value < 0.25:
            buckets["0.00-0.24"] += 1
        elif value < 0.50:
            buckets["0.25-0.49"] += 1
        elif value < 0.75:
            buckets["0.50-0.74"] += 1
        else:
            buckets["0.75-1.00"] += 1
    return buckets
