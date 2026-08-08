from __future__ import annotations

import time
import json
from typing import Any

from app.diagnostics.console import diagnostic_terminal_enabled, safe_print
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
        from app.intent_dispatcher import intent_dispatch_context

        enriched["intent_dispatch"] = intent_dispatch_context()
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
        _debug_v494_kernel(
            "POSTPROCESS_RESPONSE_RECEIVED",
            {
                "mission_id": session_id,
                "planner_turn_id": planner_turn_id,
                "suggested_actions": [action.model_dump() if hasattr(action, "model_dump") else getattr(action, "__dict__", {}) for action in result.suggested_actions[:3]],
                "page_url": str(getattr(page_context, "url", "") or ""),
            },
        )
        snapshot = self.build_snapshot(
            session_id=session_id,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
            planner_response=result,
        )
        if snapshot is None or not is_active("V47_SEMANTIC_EXECUTION_KERNEL"):
            _debug_v494_kernel(
                "KERNEL_INACTIVE_BRANCH",
                {
                    "mission_id": session_id,
                    "snapshot_is_none": snapshot is None,
                    "v47_active": is_active("V47_SEMANTIC_EXECUTION_KERNEL"),
                    "branch_reason": "snapshot is None or V47_SEMANTIC_EXECUTION_KERNEL is not active",
                },
            )
            return result
        tracer = get_entity_pipeline_tracer()
        _debug_v494_kernel(
            "SNAPSHOT_BUILT",
            {
                "mission_id": session_id,
                "planner_turn_id": planner_turn_id,
                "semantic_entity_count": len(snapshot.entities),
                "proposal": snapshot.proposal.to_dict() if snapshot.proposal else None,
                "eligibility": snapshot.eligibility.to_dict() if snapshot.eligibility else None,
                "grounding": snapshot.grounding.to_dict() if snapshot.grounding else None,
                "entity_ids": [entity.id for entity in snapshot.entities[:40]],
                "entity_urls": [(entity.canonical_url or entity.url) for entity in snapshot.entities[:40]],
            },
        )
        repaired_snapshot = _repair_page_evidenced_open_url(
            kernel=self,
            snapshot=snapshot,
            result=result,
            session_id=session_id,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
        )
        if repaired_snapshot is not None:
            snapshot = repaired_snapshot
            tracer.clear_failures(session_id)
            _debug_v494_kernel(
                "PAGE_EVIDENCED_URL_REPAIR_APPLIED",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "semantic_entity_count": len(snapshot.entities),
                    "proposal": snapshot.proposal.to_dict() if snapshot.proposal else None,
                },
            )
        if snapshot.proposal and snapshot.proposal.action_type == "SEARCH_WEB":
            tracer.clear_failures(session_id)
            _debug_v494_kernel(
                "SEARCH_WEB_CLEARED_STALE_ENTITY_FAILURES",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "branch_reason": "search navigation discovers entities and must not be blocked by stale entity lookup failures",
                    "proposal": snapshot.proposal.to_dict(),
                },
            )
        failures_before = tracer.failures(session_id)
        latest_failure_before = failures_before[-1] if failures_before else None
        current_lookup_succeeded = bool(snapshot.proposal and snapshot.proposal.entity_id)
        current_lookup_entity_id = snapshot.proposal.entity_id if snapshot.proposal else None
        current_lookup_url = snapshot.proposal.parameters.get("canonical_url") or snapshot.proposal.parameters.get("value") if snapshot.proposal else None
        pipeline_failure = tracer.active_failure_response(result, session_id)
        if pipeline_failure is not None:
            origin = latest_failure_before.to_dict() if latest_failure_before else {}
            created_at = int(origin.get("created_at") or 0)
            if diagnostic_terminal_enabled("AI_BROWSER_KERNEL_LOOKUP_TRACE"):
                safe_print(
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
                        ensure_ascii=True,
                    )
                )
        if pipeline_failure is not None:
            _debug_v494_kernel(
                "FINAL_REJECTION_ACTIVE_PIPELINE_FAILURE",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "branch_reason": "active_failure_response returned a replan before eligibility rejection branch",
                    "current_lookup_succeeded_before_replay": current_lookup_succeeded,
                    "current_lookup_entity_id": current_lookup_entity_id,
                    "current_lookup_url": current_lookup_url,
                    "returned_replan_reason": pipeline_failure.replan.reason if pipeline_failure.replan else None,
                },
            )
            return pipeline_failure
        if snapshot.eligibility and not snapshot.eligibility.eligible:
            failure_reason = snapshot.eligibility.reason
            if "entity_missing" in snapshot.eligibility.failures:
                _debug_v494_kernel(
                    "ENTITY_MISSING_REJECTION_BRANCH",
                    {
                        "mission_id": session_id,
                        "planner_turn_id": planner_turn_id,
                        "branch_reason": "snapshot.eligibility is ineligible and failures contains entity_missing",
                        "proposal": snapshot.proposal.to_dict() if snapshot.proposal else None,
                        "eligibility": snapshot.eligibility.to_dict(),
                    },
                )
                get_entity_pipeline_tracer().verify_exists(
                    session_id,
                    stage="SEMANTIC_KERNEL",
                    reason="SemanticKernel entity lookup failed",
                    exists=False,
                    entity_id=snapshot.proposal.entity_id if snapshot.proposal else None,
                )
                failure_reason = "ENTITY_PIPELINE_FAILURE stage=SemanticKernel reason=entity lookup failed"
            _debug_v494_kernel(
                "FINAL_REJECTION_ELIGIBILITY",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "branch_reason": "snapshot.eligibility.eligible is false",
                    "failure_reason": failure_reason,
                    "eligibility": snapshot.eligibility.to_dict(),
                },
            )
            return _replan_from_kernel(result, snapshot.recovery, failure_reason)
        if snapshot.grounding and snapshot.grounding.grounded and result.suggested_actions:
            _debug_v494_kernel(
                "GROUNDING_APPLY_BRANCH",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "branch_reason": "snapshot.grounding.grounded is true and suggested action exists",
                    "grounding": snapshot.grounding.to_dict(),
                },
            )
            _mark_grounded(session_id, snapshot)
            result.suggested_actions[0] = apply_grounding_to_action(result.suggested_actions[0], snapshot.grounding)
        elif snapshot.proposal and snapshot.proposal.action_type == "FOCUS_TAB" and snapshot.grounding and not snapshot.grounding.grounded:
            _debug_v494_kernel(
                "FINAL_REJECTION_GROUNDING",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "branch_reason": "FOCUS_TAB grounding failed before browser boundary",
                    "grounding": snapshot.grounding.to_dict(),
                },
            )
            return _replan_from_kernel(result, snapshot.recovery, snapshot.grounding.reason)
        _debug_v494_kernel(
            "POSTPROCESS_RETURN_ACTION",
            {
                "mission_id": session_id,
                "planner_turn_id": planner_turn_id,
                "outcome_kind": result.outcome_kind,
                "suggested_actions": [action.model_dump() if hasattr(action, "model_dump") else getattr(action, "__dict__", {}) for action in result.suggested_actions[:3]],
            },
        )
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


def _repair_page_evidenced_open_url(
    *,
    kernel: SemanticExecutionKernel,
    snapshot: KernelSnapshot,
    result: AnalyzeResponse,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
) -> KernelSnapshot | None:
    action = result.suggested_actions[0] if result.suggested_actions else None
    value = str(getattr(action, "value", "") or "").strip() if action else ""
    action_type = str(getattr(action, "action_type", "") or "").lower() if action else ""
    if action_type != "open_new_tab" or not value.startswith(("http://", "https://")):
        return None
    if not snapshot.eligibility or "entity_missing" not in snapshot.eligibility.failures:
        return None
    if not _page_evidence_contains_url(page_context, value):
        return None

    from app.runtime_state_manager.entity_binding import register_entity

    register_entity(
        session_id,
        entity_type="search_result",
        source_layer="page_evidence",
        title=str(getattr(action, "description", "") or value),
        canonical_url=value,
        confidence=0.74,
        source_page=str(getattr(page_context, "url", "") or ""),
        metadata={"repair": "page_evidenced_open_url", "action_id": getattr(action, "action_id", "") or ""},
    )
    return kernel.build_snapshot(
        session_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
        planner_response=result,
    )


def _page_evidence_contains_url(page_context: Any, url: str) -> bool:
    from urllib.parse import urlparse

    target = url.rstrip("/").lower()
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/").lower()
    evidence_parts: list[str] = [
        str(getattr(page_context, "url", "") or ""),
        str(getattr(page_context, "title", "") or ""),
        str(getattr(page_context, "visible_text", "") or ""),
        str(getattr(page_context, "selected_text", "") or ""),
    ]
    for element in list(getattr(page_context, "interactive_elements", []) or []):
        evidence_parts.extend(
            str(_read_context_item(element, key) or "")
            for key in ("href", "text", "selector", "aria_label", "title")
        )
    for block in list(getattr(page_context, "content_blocks", []) or []):
        evidence_parts.extend(
            str(_read_context_item(block, key) or "")
            for key in ("href", "text", "title", "selector")
        )
    evidence = "\n".join(evidence_parts).lower()
    if target in evidence:
        return True
    if host and host in evidence:
        return not path or path == "/" or path in evidence
    return False


def _read_context_item(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _planner_turn_id(session_id: str, result: AnalyzeResponse) -> str:
    action = result.suggested_actions[0] if result.suggested_actions else None
    action_id = getattr(action, "action_id", "") if action else ""
    action_type = getattr(action, "action_type", "") if action else ""
    value = getattr(action, "value", "") if action else ""
    return f"{session_id}:{action_id}:{action_type}:{value}"


def _debug_v494_kernel(event: str, payload: dict[str, Any]) -> None:
    if not diagnostic_terminal_enabled("AI_BROWSER_KERNEL_LOOKUP_TRACE"):
        return
    try:
        safe_print(
            "[V4.9.4 kernel-lookup] SEMANTIC_KERNEL "
            + json.dumps({"event": event, **payload}, ensure_ascii=True)
        )
    except Exception as exc:
        safe_print(f"[V4.9.4 kernel-lookup] SEMANTIC_KERNEL_LOG_FAILED {exc}")


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
