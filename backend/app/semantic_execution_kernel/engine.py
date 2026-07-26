from __future__ import annotations

import time
import json
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
from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer


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
        tracer = get_entity_pipeline_tracer()
        tracer.emit(session_id, "SEMANTIC_KERNEL", success=True, reason="received", count=len(entities))
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
        telemetry["entity_pipeline"] = tracer.telemetry(session_id)
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
                {
                    "frame_id": "entity_pipeline_replay",
                    "event": "entity_pipeline",
                    "pipeline": tracer.replay(session_id),
                },
            ],
        )

    def enrich_context(self, compressed_context: dict[str, Any], snapshot: KernelSnapshot | None) -> dict[str, Any]:
        if snapshot is None:
            return compressed_context
        tracer = get_entity_pipeline_tracer()
        from app.runtime_state_manager.entity_binding import list_entities

        registered_count = len(list_entities(snapshot.session_id))
        planner_count = len(snapshot.entities)
        tracer.verify_count(
            snapshot.session_id,
            stage="PLANNER_CONTEXT",
            reason="EntityRegistry -> PlannerContext planner_entities >= registered_entities",
            expected=registered_count,
            actual=planner_count,
            comparator="gte",
        )
        for entity in snapshot.entities:
            tracer.emit(
                snapshot.session_id,
                "PLANNER_CONTEXT",
                success=True,
                reason="included",
                trace_id=entity.trace_id,
                entity_id=entity.id,
                artifact_id=entity.artifact_id,
                canonical_url=entity.canonical_url or entity.url,
                selector_id=entity.selector_ids[0] if entity.selector_ids else None,
                runtime_resource_id=entity.runtime_resource_id,
                source=entity.source_layer,
            )
        if not is_active("V47_SEMANTIC_EXECUTION_KERNEL"):
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
        current_request_timestamp = int(time.time() * 1000)
        planner_turn_id = _planner_turn_id(session_id, result)
        snapshot = self.build_snapshot(
            session_id=session_id,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
            planner_response=result,
        )
        if snapshot is None or not is_active("V47_SEMANTIC_EXECUTION_KERNEL"):
            return result
        tracer = get_entity_pipeline_tracer()
        failures_before = tracer.failures(session_id)
        latest_failure_before = failures_before[-1] if failures_before else None
        current_lookup_succeeded = bool(snapshot.proposal and snapshot.proposal.entity_id)
        current_lookup_entity_id = snapshot.proposal.entity_id if snapshot.proposal else None
        current_lookup_url = snapshot.proposal.parameters.get("canonical_url") or snapshot.proposal.parameters.get("value") if snapshot.proposal else None
        pipeline_failure = tracer.active_failure_response(result, session_id)
        if pipeline_failure is not None:
            origin = latest_failure_before.to_dict() if latest_failure_before else {}
            created_at = int(origin.get("created_at") or 0)
            print(
                "[V4.9.3 proof] SEMANTIC_KERNEL_ACTIVE_FAILURE_RESPONSE "
                + json.dumps(
                    {
                        "mission_id": session_id,
                        "planner_turn_id": planner_turn_id,
                        "failure_creation_timestamp": created_at or None,
                        "current_request_timestamp": current_request_timestamp,
                        "when_originally_recorded": created_at or None,
                        "origin_file": origin.get("origin_file"),
                        "origin_function": origin.get("origin_function"),
                        "failure_stage": origin.get("stage"),
                        "failure_reason": origin.get("reason"),
                        "originated_during_this_request": bool(created_at and created_at >= current_request_timestamp),
                        "originated_during_previous_request": bool(created_at and created_at < current_request_timestamp),
                        "current_lookup_succeeded_before_replay": current_lookup_succeeded,
                        "current_lookup_entity_id": current_lookup_entity_id,
                        "current_lookup_url": current_lookup_url,
                        "returned_replan_reason": pipeline_failure.replan.reason if pipeline_failure.replan else None,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        if pipeline_failure is not None:
            return pipeline_failure
        if snapshot.eligibility and not snapshot.eligibility.eligible:
            failure_reason = snapshot.eligibility.reason
            if "entity_missing" in snapshot.eligibility.failures:
                get_entity_pipeline_tracer().verify_exists(
                    session_id,
                    stage="SEMANTIC_KERNEL",
                    reason="SemanticKernel entity lookup failed",
                    exists=False,
                    entity_id=snapshot.proposal.entity_id if snapshot.proposal else None,
                )
                failure_reason = "ENTITY_PIPELINE_FAILURE stage=SemanticKernel reason=entity lookup failed"
            return _replan_from_kernel(result, snapshot.recovery, failure_reason)
        if snapshot.grounding and snapshot.grounding.grounded and result.suggested_actions:
            _mark_grounded(session_id, snapshot)
            result.suggested_actions[0] = apply_grounding_to_action(result.suggested_actions[0], snapshot.grounding)
        return result


def _replan_from_kernel(result: AnalyzeResponse, recovery: RecoveryDecision, reason: str) -> AnalyzeResponse:
    diagnostic = reason if reason.startswith("ENTITY_PIPELINE_FAILURE") else "Semantic Execution Kernel rejected the proposal before browser execution."
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=f"{result.analysis}\n\n{diagnostic}",
        outcome_kind="replan",
        clarification_question=None,
        report=None,
        replan=ReplanOutcome(reason=f"{reason}. Recovery strategy: {recovery.strategy} ({recovery.reason})."),
        suggested_actions=[],
    )


def _planner_turn_id(session_id: str, result: AnalyzeResponse) -> str:
    action = result.suggested_actions[0] if result.suggested_actions else None
    action_id = getattr(action, "action_id", "") if action else ""
    action_type = getattr(action, "action_type", "") if action else ""
    value = getattr(action, "value", "") if action else ""
    return f"{session_id}:{action_id}:{action_type}:{value}"


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
    from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer

    get_entity_pipeline_tracer().emit(
        session_id,
        "GROUNDING",
        success=True,
        reason="resolved",
        trace_id=entity.trace_id,
        entity_id=entity.id,
        artifact_id=entity.artifact_id,
        canonical_url=entity.canonical_url or entity.url,
        selector_id=entity.selector_ids[0] if entity.selector_ids else None,
        runtime_resource_id=entity.runtime_resource_id,
        source=entity.source_layer,
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
