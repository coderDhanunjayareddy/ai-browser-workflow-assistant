from __future__ import annotations

from typing import Any


SUBSYSTEMS = ("planner", "browser", "ledger", "providers", "knowledge_extraction", "validation", "completion", "blueprint", "cognitive_runtime", "overall_mission")


def diagnose_benchmark(metrics: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if metrics["planner_calls"] > int(snapshot.get("expected_planner_calls") or 3):
        issues.append(_issue("planner", "excessive_planner_calls", "Planner usage exceeded expected threshold.", 0.75))
    if metrics["high_confidence_disagreement"] > 0:
        issues.append(_issue("cognitive_runtime", "high_confidence_disagreement", "Cognitive and Runtime V1 disagree at high confidence.", 0.8))
    if metrics["ledger_intents"] == 0:
        issues.append(_issue("ledger", "no_ledger_progression", "No ledger intents were observed.", 0.9))
    if metrics["evidence_coverage"] < 0.5:
        issues.append(_issue("knowledge_extraction", "low_evidence_coverage", "Evidence coverage is below migration threshold.", 0.65))
    if metrics["runtime_stability"] < 1.0:
        issues.append(_issue("overall_mission", "runtime_instability", "Runtime errors were observed.", 0.9))
    weak = issues[0]["subsystem"] if issues else "none"
    return {
        "subsystems": {name: _subsystem_status(name, issues) for name in SUBSYSTEMS},
        "root_cause": issues[0]["category"] if issues else "none",
        "weak_subsystem": weak,
        "failure_category": issues[0]["category"] if issues else "none",
        "confidence": issues[0]["confidence"] if issues else 1.0,
        "issues": issues,
    }


def _issue(subsystem: str, category: str, reason: str, confidence: float) -> dict[str, Any]:
    return {"subsystem": subsystem, "category": category, "reason": reason, "confidence": confidence}


def _subsystem_status(name: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = [issue for issue in issues if issue["subsystem"] == name]
    return {
        "status": "weak" if relevant else "ok",
        "issues": relevant,
    }
