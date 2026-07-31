from __future__ import annotations

from typing import Any

from app.benchmark.benchmark_models import BenchmarkMission, ExecutionTrace


TRACE_STAGES = (
    "mission_metadata",
    "mission_blueprint",
    "blueprint_readiness",
    "expanded_nodes",
    "ledger_intents",
    "intent_execution_timeline",
    "provider_execution",
    "browser_actions",
    "evidence",
    "validation",
    "mission_completion",
    "cognitive_recommendations",
    "decision_comparison",
    "duration",
    "planner_calls",
    "recovery",
    "clarifications",
    "failures",
)


class ExecutionTraceCollector:
    def collect(self, *, benchmark: BenchmarkMission, mission_id: str | None = None, snapshots: dict[str, Any] | None = None) -> ExecutionTrace:
        snapshots = dict(snapshots or {})
        stages = {
            stage: snapshots.get(stage, _default_stage(stage, benchmark))
            for stage in TRACE_STAGES
        }
        timeline = list(snapshots.get("timeline") or _timeline_from_stages(stages))
        return ExecutionTrace(
            benchmark_id=benchmark.id,
            mission_id=mission_id,
            stages=stages,
            timeline=timeline,
        )


def _default_stage(stage: str, benchmark: BenchmarkMission) -> Any:
    if stage == "mission_metadata":
        return {"benchmark_id": benchmark.id, "category": benchmark.category, "user_prompt": benchmark.user_prompt}
    if stage == "mission_blueprint":
        return {"expected_nodes": benchmark.expected_blueprint, "observed_nodes": []}
    if stage in {"expanded_nodes", "ledger_intents", "intent_execution_timeline", "provider_execution", "browser_actions", "evidence", "validation", "cognitive_recommendations", "decision_comparison", "recovery", "clarifications", "failures"}:
        return []
    if stage == "blueprint_readiness":
        return {"ready": [], "blocked": [], "waiting": []}
    if stage == "mission_completion":
        return {"complete": False, "reason": "not_observed"}
    if stage == "duration":
        return {"duration_ms": 0}
    if stage == "planner_calls":
        return {"count": 0}
    return {}


def _timeline_from_stages(stages: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"order": index + 1, "stage": stage, "observed": bool(value)}
        for index, (stage, value) in enumerate(stages.items())
    ]
