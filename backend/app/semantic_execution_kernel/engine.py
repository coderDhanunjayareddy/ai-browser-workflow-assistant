from __future__ import annotations

import time
from typing import Any

from app.feature_flags import is_active, is_shadow_or_active
from app.schemas.response import AnalyzeResponse, ReplanOutcome
from app.semantic_execution_kernel.browser_context_registry import build_browser_context
from app.semantic_execution_kernel.eligibility import check_eligibility
from app.semantic_execution_kernel.entity_registry import build_entity_registry
from app.semantic_execution_kernel.grounding import apply_grounding_to_action, ground_semantic_action
from app.semantic_execution_kernel.loop_prevention import loop_prevention_status
from app.semantic_execution_kernel.mission_state import build_mission_state
from app.semantic_execution_kernel.models import KernelSnapshot, RecoveryDecision
from app.semantic_execution_kernel.observability import telemetry_summary
from app.semantic_execution_kernel.planner_constraints import legal_action_prompt, proposal_from_planner_action
from app.semantic_execution_kernel.progress_ledger import build_progress_ledger
from app.semantic_execution_kernel.recovery import recovery_decision
from app.semantic_execution_kernel.replay import semantic_replay_frames
from app.semantic_execution_kernel.semantic_action_registry import semantic_action_registry
from app.semantic_execution_kernel.state_sync import synchronization_summary


class SemanticExecutionKernel:
    def build_snapshot(
        self,
        *,
        session_id: str,
        task: str,
        page_context: Any,
        prior_steps: list[Any],
        planner_response: AnalyzeResponse | None = None,
    ) -> KernelSnapshot | None:
        if not is_shadow_or_active("V47_SEMANTIC_EXECUTION_KERNEL"):
            return None
        started = time.perf_counter()
        entities = build_entity_registry(page_context, session_id=session_id)
        mission_state = build_mission_state(task, prior_steps)
        browser_context = build_browser_context(page_context, prior_steps)
        proposal = None
        if planner_response and planner_response.suggested_actions:
            proposal = proposal_from_planner_action(planner_response.suggested_actions[0], entities, session_id=session_id)
        loop_status = loop_prevention_status(proposal, prior_steps)
        eligibility = check_eligibility(
            proposal,
            mission_state=mission_state,
            entities=entities,
            loop_status=loop_status,
        ) if proposal else None
        grounding = ground_semantic_action(proposal, entities=entities, eligibility=eligibility) if eligibility else None
        ledger = build_progress_ledger(prior_steps, proposal)
        recovery = recovery_decision(eligibility)
        sync = synchronization_summary(mission_state=mission_state, entities=entities, browser_context=browser_context)
        telemetry = telemetry_summary(
            started_at=started,
            entities=entities,
            eligibility=eligibility,
            grounding=grounding,
            loop_status=loop_status,
            sync=sync,
        )
        from app.runtime_state_manager.entity_binding import binding_telemetry, entity_binding_trace, registry_identity

        telemetry["entity_binding"] = binding_telemetry(session_id)
        telemetry["registry_identity"] = registry_identity(session_id)
        return KernelSnapshot(
            schema_version="semantic_execution_kernel.v1",
            session_id=session_id,
            mission_state=mission_state,
            entities=entities,
            browser_context=browser_context,
            legal_actions=semantic_action_registry(),
            proposal=proposal,
            eligibility=eligibility,
            grounding=grounding,
            ledger=ledger,
            loop_prevention=loop_status,
            recovery=recovery,
            telemetry=telemetry,
            replay=[
                *semantic_replay_frames(ledger),
                *[
                    {
                        "frame_id": f"entity_binding_trace_{index}",
                        "event": event.get("event"),
                        "entity_id": event.get("entity_id"),
                        "artifact_id": event.get("artifact_id"),
                        "runtime_resource_id": event.get("runtime_resource_id"),
                        "resolved_by": event.get("resolved_by"),
                        "registry_version": event.get("registry_version"),
                    }
                    for index, event in enumerate(entity_binding_trace(session_id, limit=12), 1)
                ],
            ],
        )

    def enrich_context(self, compressed_context: dict[str, Any], snapshot: KernelSnapshot | None) -> dict[str, Any]:
        if snapshot is None or not is_active("V47_SEMANTIC_EXECUTION_KERNEL"):
            return compressed_context
        enriched = dict(compressed_context)
        enriched["semantic_execution_kernel"] = snapshot.to_compact_context()
        enriched["legal_semantic_actions"] = legal_action_prompt(snapshot.entities)
        return enriched

    def postprocess_response(
        self,
        *,
        result: AnalyzeResponse,
        session_id: str,
        task: str,
        page_context: Any,
        prior_steps: list[Any],
    ) -> AnalyzeResponse:
        snapshot = self.build_snapshot(
            session_id=session_id,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
            planner_response=result,
        )
        if snapshot is None or not is_active("V47_SEMANTIC_EXECUTION_KERNEL"):
            return result
        if snapshot.eligibility and not snapshot.eligibility.eligible:
            return _replan_from_kernel(result, snapshot.recovery, snapshot.eligibility.reason)
        if snapshot.grounding and snapshot.grounding.grounded and result.suggested_actions:
            _mark_grounded(session_id, snapshot)
            result.suggested_actions[0] = apply_grounding_to_action(result.suggested_actions[0], snapshot.grounding)
        return result


def _replan_from_kernel(result: AnalyzeResponse, recovery: RecoveryDecision, reason: str) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=f"{result.analysis}\n\nSemantic Execution Kernel rejected the proposal before browser execution.",
        outcome_kind="replan",
        clarification_question=None,
        report=None,
        replan=ReplanOutcome(reason=f"{reason}. Recovery strategy: {recovery.strategy} ({recovery.reason})."),
        suggested_actions=[],
    )


def _mark_grounded(session_id: str, snapshot: KernelSnapshot) -> None:
    if snapshot.proposal is None or snapshot.proposal.entity_id is None:
        return
    entity = next((item for item in snapshot.entities if item.id == snapshot.proposal.entity_id), None)
    if entity is None:
        return
    from app.runtime_state_manager.entity_binding import register_entity

    register_entity(
        session_id,
        entity_type=entity.semantic_type,
        source_layer=entity.source_layer,
        title=entity.title,
        canonical_url=entity.canonical_url or entity.url,
        artifact_id=entity.artifact_id,
        runtime_resource_id=entity.runtime_resource_id,
        selector_ids=entity.selector_ids,
        confidence=entity.confidence,
        source_page=entity.source_page,
        metadata=entity.metadata,
        state="GROUNDED",
    )


_kernel = SemanticExecutionKernel()


def observe_semantic_execution_kernel(
    *,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
) -> KernelSnapshot | None:
    return _kernel.build_snapshot(
        session_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
    )


def enrich_planner_context_with_kernel(compressed_context: dict[str, Any], snapshot: KernelSnapshot | None) -> dict[str, Any]:
    return _kernel.enrich_context(compressed_context, snapshot)


def postprocess_with_kernel(
    *,
    result: AnalyzeResponse,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
) -> AnalyzeResponse:
    return _kernel.postprocess_response(
        result=result,
        session_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
    )
