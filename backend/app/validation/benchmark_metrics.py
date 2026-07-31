from __future__ import annotations

from statistics import mean
from typing import Any


def compute_benchmark_metrics(snapshot: dict[str, Any]) -> dict[str, Any]:
    comparisons = list(snapshot.get("comparisons") or [])
    ledger = dict(snapshot.get("ledger") or {})
    providers = dict(snapshot.get("providers") or {})
    evidence = dict(snapshot.get("evidence") or {})
    blueprint = dict(snapshot.get("blueprint") or {})
    planner_calls = int(snapshot.get("planner_calls") or 0)
    agreement_values = [str(item.get("agreement") or "") for item in comparisons if isinstance(item, dict)]
    confidences = [float(item.get("confidence") or 0.0) for item in comparisons if isinstance(item, dict)]
    total_comparisons = len(agreement_values)
    agreement_count = sum(1 for item in agreement_values if item in {"exact", "semantic"})
    high_conflict = sum(
        1
        for item in comparisons
        if isinstance(item, dict) and str(item.get("agreement")) == "disagreement" and float(item.get("confidence") or 0.0) >= 0.75
    )
    ledger_intents = int(ledger.get("intent_count") or len(ledger.get("intents") or []))
    browser_intents = int(ledger.get("browser_intents") or providers.get("browser_control", 0) or 0)
    completed = bool(snapshot.get("mission_completed") or ledger.get("completed") or False)
    return {
        "mission_success_rate": 1.0 if completed else 0.0,
        "completion_accuracy": float(snapshot.get("completion_accuracy") or (1.0 if completed else 0.0)),
        "decision_agreement": _ratio(agreement_count, total_comparisons),
        "high_confidence_disagreement": high_conflict,
        "planner_calls": planner_calls,
        "ledger_intents": ledger_intents,
        "browser_intents": browser_intents,
        "provider_calls": int(sum(int(v or 0) for v in providers.values())) if providers else 0,
        "recovery_count": int(snapshot.get("recovery_count") or 0),
        "replan_count": int(snapshot.get("replan_count") or 0),
        "wait_count": int(snapshot.get("wait_count") or 0),
        "clarification_count": int(snapshot.get("clarification_count") or 0),
        "mission_duration_ms": int(snapshot.get("mission_duration_ms") or 0),
        "provider_latency_ms": dict(snapshot.get("provider_latency_ms") or {}),
        "evidence_coverage": float(evidence.get("coverage") or 0.0),
        "evidence_confidence": float(evidence.get("confidence") or (mean(confidences) if confidences else 0.0)),
        "blueprint_readiness": float(blueprint.get("readiness") or 0.0),
        "expansion_efficiency": float(blueprint.get("expansion_efficiency") or _ratio(ledger_intents, max(len(blueprint.get("nodes") or []), ledger_intents))),
        "validation_accuracy": float(snapshot.get("validation_accuracy") or 0.0),
        "comparison_agreement": _ratio(agreement_count, total_comparisons),
        "decision_confidence": round(mean(confidences), 4) if confidences else 0.0,
        "runtime_stability": float(snapshot.get("runtime_stability") or (1.0 if not snapshot.get("runtime_errors") else 0.0)),
        "failure_recovery_rate": float(snapshot.get("failure_recovery_rate") or 0.0),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
