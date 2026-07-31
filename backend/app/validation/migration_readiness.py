from __future__ import annotations

from typing import Any


DECISIONS = ("WAIT", "CONTINUE", "REQUEST_USER", "RECOVER", "REPLAN", "COMPLETE", "BLOCKED", "FAIL")


class MigrationReadinessEvaluator:
    def evaluate(self, metrics: dict[str, Any], comparisons: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        comparisons = list(comparisons or [])
        return {
            decision: self._decision_readiness(decision, metrics, comparisons)
            for decision in DECISIONS
        }

    def _decision_readiness(self, decision: str, metrics: dict[str, Any], comparisons: list[dict[str, Any]]) -> dict[str, Any]:
        relevant = [item for item in comparisons if str(item.get("runtime_decision") or "").upper() == decision]
        agreement = _agreement(relevant) if relevant else float(metrics.get("comparison_agreement") or 0.0)
        confidence = _confidence(relevant) if relevant else float(metrics.get("decision_confidence") or 0.0)
        penalty = 0.1 if decision in {"RECOVER", "REPLAN", "FAIL"} else 0.0
        readiness = max(min((agreement * 0.65) + (confidence * 0.35) - penalty, 1.0), 0.0)
        risk = "low" if readiness >= 0.9 else "medium" if readiness >= 0.75 else "high"
        wave = "5C" if risk == "low" else "5D" if risk == "medium" else "future"
        return {
            "readiness": round(readiness, 4),
            "risk": risk,
            "recommended_wave": wave,
            "required_evidence": ["shadow_comparisons", "agreement_metrics", "false_positive_review"],
            "confidence": round(confidence, 4),
        }


def _agreement(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    good = sum(1 for item in items if str(item.get("agreement")) in {"exact", "semantic"})
    return good / len(items)


def _confidence(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return sum(float(item.get("confidence") or 0.0) for item in items) / len(items)
