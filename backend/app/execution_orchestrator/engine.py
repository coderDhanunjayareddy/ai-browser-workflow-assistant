from __future__ import annotations

import time
from typing import Any

from app.execution_orchestrator.artifact_registry import build_artifacts
from app.execution_orchestrator.budgets import build_budgets
from app.execution_orchestrator.completion_engine import build_progress_ledger
from app.execution_orchestrator.models import ExecutionOrchestratorSnapshot
from app.execution_orchestrator.phase_execution import attach_phase_execution_directive
from app.execution_orchestrator.phase_state_machine import build_phases, workflow_category
from app.execution_orchestrator.planner_gating import action_allowed, planner_constraints, reject_for_phase
from app.execution_orchestrator.recovery import route_recovery
from app.execution_orchestrator.replay import phase_replay
from app.execution_orchestrator.telemetry import build_telemetry
from app.execution_orchestrator.transition_engine import build_transitions
from app.feature_flags import is_active, is_shadow_or_active
from app.schemas.response import AnalyzeResponse


class ExecutionOrchestrator:
    def build_snapshot(
        self,
        *,
        session_id: str,
        task: str,
        page_context: Any,
        prior_steps: list[Any],
    ) -> ExecutionOrchestratorSnapshot | None:
        if not is_shadow_or_active("V48_EXECUTION_ORCHESTRATOR"):
            return None
        started = time.perf_counter()
        artifacts = build_artifacts(page_context, prior_steps)
        ledger = build_progress_ledger(task, artifacts, prior_steps)
        category = workflow_category(task)
        phases, active_phase = build_phases(category, ledger)
        budgets = build_budgets(prior_steps, artifacts)
        transitions = build_transitions(phases)
        recovery = route_recovery(active_phase, budgets)
        replay = phase_replay(phases, artifacts, transitions)
        telemetry = build_telemetry(
            started_at=started,
            active_phase=active_phase,
            artifacts=artifacts,
            budgets=budgets,
            transitions=transitions,
        )
        return ExecutionOrchestratorSnapshot(
            schema_version="execution_orchestrator.v1",
            session_id=session_id,
            workflow_category=category,
            phases=phases,
            active_phase=active_phase,
            progress_ledger=ledger,
            artifacts=artifacts,
            budgets=budgets,
            transitions=transitions,
            recovery=recovery,
            replay=replay,
            telemetry=telemetry,
        )

    def enrich_context(self, compressed_context: dict[str, Any], snapshot: ExecutionOrchestratorSnapshot | None) -> dict[str, Any]:
        if snapshot is None or not is_active("V48_EXECUTION_ORCHESTRATOR"):
            return compressed_context
        enriched = dict(compressed_context)
        enriched["execution_orchestrator"] = snapshot.to_compact_context()
        enriched["planner_phase_constraints"] = planner_constraints(snapshot)
        return enriched

    def postprocess_response(
        self,
        result: AnalyzeResponse,
        snapshot: ExecutionOrchestratorSnapshot | None,
    ) -> AnalyzeResponse:
        if snapshot is None or not is_active("V48_EXECUTION_ORCHESTRATOR"):
            return result
        if result.outcome_kind in {"report", "ask", "replan"}:
            return result
        if snapshot.budgets.exhausted:
            return reject_for_phase(result, snapshot, f"budget exhausted: {', '.join(snapshot.budgets.exhausted)}")
        if result.intent_dispatch is not None and not result.intent_dispatch.browser_executable:
            result.intent_dispatch.handled = True
            result.analysis = (
                f"{result.analysis}\n\nExecution Dispatcher routed intent "
                f"{result.intent_dispatch.intent} to {result.intent_dispatch.owner}."
            ).strip()
            return result
        if not result.suggested_actions:
            return result
        action = result.suggested_actions[0]
        if not action_allowed(action.action_type, snapshot.active_phase):
            return reject_for_phase(result, snapshot, f"action {action.action_type} is not allowed in phase {snapshot.active_phase.name}")
        return attach_phase_execution_directive(result, snapshot)


_orchestrator = ExecutionOrchestrator()


def observe_execution_orchestrator(
    *,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
) -> ExecutionOrchestratorSnapshot | None:
    return _orchestrator.build_snapshot(
        session_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
    )


def enrich_planner_context_with_orchestrator(
    compressed_context: dict[str, Any],
    snapshot: ExecutionOrchestratorSnapshot | None,
) -> dict[str, Any]:
    return _orchestrator.enrich_context(compressed_context, snapshot)


def postprocess_with_orchestrator(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot | None,
) -> AnalyzeResponse:
    return _orchestrator.postprocess_response(result, snapshot)
