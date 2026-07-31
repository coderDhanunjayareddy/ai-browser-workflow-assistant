from __future__ import annotations

from statistics import mean
from typing import Any

from app.benchmark.benchmark_models import BenchmarkMission, ExecutionTrace


def compute_metrics(*, benchmark: BenchmarkMission, trace: ExecutionTrace) -> dict[str, Any]:
    stages = trace.stages
    blueprint = dict(stages.get("mission_blueprint") or {})
    observed_nodes = list(blueprint.get("observed_nodes") or [])
    expected_nodes = list(blueprint.get("expected_nodes") or benchmark.expected_blueprint)
    comparisons = list(stages.get("decision_comparison") or [])
    evidence = list(stages.get("evidence") or [])
    validations = list(stages.get("validation") or [])
    ledger_intents = list(stages.get("ledger_intents") or [])
    provider_events = list(stages.get("provider_execution") or [])
    browser_actions = list(stages.get("browser_actions") or [])
    failures = list(stages.get("failures") or [])
    complete = bool(dict(stages.get("mission_completion") or {}).get("complete"))
    confidences = [float(item.get("confidence") or 0.0) for item in evidence if isinstance(item, dict)]
    agreements = [str(item.get("agreement") or "") for item in comparisons if isinstance(item, dict)]
    return {
        "mission_success_rate": 1.0 if complete else 0.0,
        "blueprint_accuracy": _coverage(observed_nodes, expected_nodes),
        "intent_expansion_accuracy": _coverage([item.get("blueprint_node_id") for item in ledger_intents if isinstance(item, dict)], expected_nodes),
        "ledger_consistency": 1.0 if all(str(item.get("status") or "") in {"QUEUED", "DISPATCHED", "EXECUTING", "COMPLETED", "FAILED", "BLOCKED", "WAITING_BROWSER", "WAITING_PROVIDER"} for item in ledger_intents if isinstance(item, dict)) else 0.0,
        "execution_time_ms": int(dict(stages.get("duration") or {}).get("duration_ms") or 0),
        "planner_calls": int(dict(stages.get("planner_calls") or {}).get("count") or 0),
        "browser_actions": len(browser_actions),
        "provider_calls": len(provider_events),
        "evidence_coverage": min(len(evidence) / max(len(expected_nodes), 1), 1.0),
        "evidence_confidence": round(mean(confidences), 4) if confidences else 0.0,
        "validation_accuracy": _validation_accuracy(validations),
        "mission_completion_accuracy": 1.0 if complete and not failures else 0.0,
        "recovery_count": len(stages.get("recovery") or []),
        "replanning_count": sum(1 for item in comparisons if isinstance(item, dict) and str(item.get("runtime_decision")) == "REPLAN"),
        "clarification_count": len(stages.get("clarifications") or []),
        "agreement_rate": _agreement_rate(agreements),
        "failure_category": str(failures[0].get("category")) if failures and isinstance(failures[0], dict) else "none",
        "latency_ms": _latency(stages),
        "reliability_score": 1.0 if not failures else 0.0,
    }


def _coverage(observed: list[Any], expected: list[Any]) -> float:
    expected_set = {str(item) for item in expected if item}
    observed_set = {str(item) for item in observed if item}
    return round(len(expected_set & observed_set) / len(expected_set), 4) if expected_set else 1.0


def _validation_accuracy(validations: list[Any]) -> float:
    if not validations:
        return 0.0
    passed = sum(1 for item in validations if isinstance(item, dict) and bool(item.get("passed", item.get("valid", False))))
    return round(passed / len(validations), 4)


def _agreement_rate(agreements: list[str]) -> float:
    if not agreements:
        return 0.0
    good = sum(1 for item in agreements if item in {"exact", "semantic"})
    return round(good / len(agreements), 4)


def _latency(stages: dict[str, Any]) -> int:
    provider = stages.get("provider_execution") or []
    values = [int(item.get("latency_ms") or 0) for item in provider if isinstance(item, dict)]
    return int(mean(values)) if values else 0
