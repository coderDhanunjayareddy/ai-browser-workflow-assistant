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
from app.intent_dispatcher.models import IntentDispatchDirective
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
        ledger = build_progress_ledger(task, artifacts, prior_steps, session_id=session_id)
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
            if result.intent_execution is not None:
                result.analysis = (
                    f"{result.analysis}\n\nExecution Dispatcher executed intent "
                    f"{result.intent_dispatch.intent} with {result.intent_dispatch.owner}: "
                    f"{result.intent_execution.reason}"
                ).strip()
            return result
        if not result.suggested_actions:
            return result
        action = result.suggested_actions[0]
        open_response = _open_phase_entity_response(result, snapshot, action.action_type)
        if open_response is not None:
            return attach_phase_execution_directive(open_response, snapshot)
        if not action_allowed(action.action_type, snapshot.active_phase):
            collect_response = _collect_before_open_response(result, snapshot, action.action_type)
            if collect_response is not None:
                return collect_response
            return reject_for_phase(result, snapshot, f"action {action.action_type} is not allowed in phase {snapshot.active_phase.name}")
        return attach_phase_execution_directive(result, snapshot)


_orchestrator = ExecutionOrchestrator()


def _collect_before_open_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action_type: str,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "COLLECT":
        return None
    if str(action_type or "").lower() != "open_new_tab":
        return None
    if snapshot.progress_ledger.current_counts.get("collected_items", 0) > 0:
        return None
    current_url = snapshot.artifacts.visited_urls[-1] if snapshot.artifacts.visited_urls else ""
    if not _is_search_results_url(current_url):
        return None

    directive = IntentDispatchDirective(
        mission_id=result.session_id,
        intent="collect_search_results",
        owner="browser_intelligence",
        capability="serp_collection",
        dispatch_target="browser_intelligence",
        browser_executable=False,
        reason=(
            "Execution Orchestrator requires deterministic search-result collection "
            "before opening ranked result entities from the COLLECT phase."
        ),
        payload={
            "action_type": "collect_search_results",
            "description": "Collect visible search result candidates before opening sources",
            "reasoning": "Collect and register visible result entities so OPEN phase actions are grounded.",
            "confidence": 0.9,
            "safety_level": "safe",
        },
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator converted the premature open-tab proposal "
            "into deterministic search-result collection for the active COLLECT phase."
        ),
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
    )


def _is_search_results_url(url: str) -> bool:
    from urllib.parse import urlsplit

    parsed = urlsplit(str(url or ""))
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"google.com", "bing.com"} and parsed.path.startswith("/search"):
        return True
    if host == "duckduckgo.com" and parsed.query:
        return True
    return False


def _open_phase_entity_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action_type: str,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "OPEN":
        return None
    if str(action_type or "").lower() in {"open_new_tab", "focus_existing_tab", "switch_tab"}:
        return None
    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    if snapshot.progress_ledger.current_counts.get("opened_pages", 0) >= target:
        return None
    entity = _first_openable_entity(snapshot.session_id)
    if entity is None or not entity.canonical_url:
        return None

    from app.schemas.response import SuggestedAction

    action = SuggestedAction(
        action_id=f"orchestrator_open_recovery_{entity.entity_id[-12:]}",
        action_type="open_new_tab",
        target_selector="",
        value=entity.canonical_url,
        description=f"Open collected source: {entity.title or entity.canonical_url}",
        reasoning=(
            "Execution Orchestrator recovered an invalid planner action for the OPEN phase "
            f"by opening a registered search-result entity_id={entity.entity_id}."
        ),
        confidence=max(0.0, min(1.0, float(entity.confidence or 0.82))),
        safety_level="safe",
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator recovered the OPEN phase by selecting "
            "the first registered source entity instead of the invalid planner action."
        ),
        outcome_kind="act",
        suggested_actions=[action],
    )


def _first_openable_entity(session_id: str):
    from app.browser_url_policy import is_openable_browser_url
    from app.runtime_state_manager.entity_binding import list_entities

    entities = [
        entity
        for entity in list_entities(session_id)
        if entity.canonical_url
        and entity.state != "INVALID"
        and entity.entity_type in {"search_result", "semantic_element", "link", "card", "list_item", "table_row"}
        and is_openable_browser_url(entity.canonical_url)
    ]
    if not entities:
        return None
    return sorted(
        entities,
        key=lambda entity: (
            _entity_rank(entity),
            0 if entity.entity_type == "search_result" else 1,
            -float(entity.confidence or 0.0),
            entity.title,
            entity.entity_id,
        ),
    )[0]


def _entity_rank(entity) -> int:
    try:
        return int((entity.metadata or {}).get("rank") or 9999)
    except (TypeError, ValueError):
        return 9999


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
