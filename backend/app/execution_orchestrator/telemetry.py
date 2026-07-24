from __future__ import annotations

import time

from app.execution_orchestrator.models import ArtifactRegistry, ExecutionBudgets, OrchestratorTelemetry, PhaseState, TransitionRecord


def build_telemetry(
    *,
    started_at: float,
    active_phase: PhaseState,
    artifacts: ArtifactRegistry,
    budgets: ExecutionBudgets,
    transitions: list[TransitionRecord],
    planner_rejected: bool = False,
) -> OrchestratorTelemetry:
    return OrchestratorTelemetry(
        phase_duration_ms=int((time.perf_counter() - started_at) * 1000),
        planner_turns_in_phase=budgets.consumed.get("planner_turns", 0),
        phase_retries=active_phase.retry_count,
        transition_count=len(transitions),
        phase_failures=1 if active_phase.status == "failed" else 0,
        artifact_counts=artifacts.counts(),
        budget_consumption=budgets.consumed,
        planner_rejection_count=1 if planner_rejected else 0,
    )
