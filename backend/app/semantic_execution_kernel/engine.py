from __future__ import annotations

import time
import json
import re
from typing import Any

from app.diagnostics.console import diagnostic_terminal_enabled, safe_print
from app.feature_flags import is_active, is_shadow_or_active
from app.schemas.response import AnalyzeResponse, ReplanOutcome, SuggestedAction
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
        ambiguity_repair = _repair_unsupported_contact_ambiguity(
            result=result,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
        )
        if ambiguity_repair is not None:
            return ambiguity_repair
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
        latest_failure_created_at = int(getattr(latest_failure_before, "created_at", 0) or 0)
        if pipeline_failure is not None and latest_failure_created_at and latest_failure_created_at <= current_request_timestamp:
            pipeline_failure = None
            _debug_v494_kernel(
                "IGNORED_STALE_ACTIVE_ENTITY_FAILURE",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "branch_reason": "historical entity failure belongs to a previous request; current proposal eligibility is authoritative",
                    "failure_creation_timestamp": latest_failure_created_at,
                    "current_request_timestamp": current_request_timestamp,
                    "current_lookup_url": current_lookup_url,
                    "current_lookup_succeeded": current_lookup_succeeded,
                },
            )
        if pipeline_failure is not None and snapshot.proposal and snapshot.proposal.action_type == "SEARCH_WEB":
            pipeline_failure = None
            tracer.clear_failures(session_id)
            _debug_v494_kernel(
                "SEARCH_WEB_IGNORED_ACTIVE_ENTITY_FAILURE",
                {
                    "mission_id": session_id,
                    "planner_turn_id": planner_turn_id,
                    "branch_reason": "current search navigation is discovery work and must not replay stale entity lookup failures",
                    "current_lookup_url": current_lookup_url,
                },
            )
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
            repaired_interactive = _repair_ungrounded_interactive_action(result, snapshot)
            if repaired_interactive is not None:
                return repaired_interactive
            refresh_response = _interactive_entity_refresh_response(result, snapshot, prior_steps)
            if refresh_response is not None:
                return refresh_response
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


def _repair_unsupported_contact_ambiguity(
    *,
    result: AnalyzeResponse,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
) -> AnalyzeResponse | None:
    question = str(result.clarification_question or "").lower()
    if result.outcome_kind != "ask" or "multiple" not in question:
        return None
    if not any(term in question for term in ("contact", "recipient", "match")):
        return None
    name = _requested_contact_name(task)
    if not name:
        return None
    searched = False
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        if str(data.get("action_type") or "").lower() != "fill":
            continue
        if name.lower() in str(data.get("value") or "").lower():
            searched = True
            break

    if searched:
        exact_matches = _exact_interactive_matches(page_context, name)
        if len(exact_matches) != 1:
            return None
        selector = exact_matches[0]
        return AnalyzeResponse(
            session_id=result.session_id,
            analysis=(
                f"{result.analysis}\n\nSemantic Execution Kernel resolved the requested destination from "
                "one unique exact visible label; partial and embedded text matches were excluded."
            ),
            outcome_kind="act",
            clarification_question=None,
            report=None,
            replan=None,
            suggested_actions=[SuggestedAction(
                action_id=f"open_exact_contact_{name.lower().replace(' ', '_')}",
                action_type="click",
                target_selector=selector,
                value=name,
                description=f"Open the unique exact contact or recipient: {name}",
                reasoning="Exactly one grounded interactive label equals the requested destination name.",
                confidence=0.94,
                safety_level="safe",
            )],
        )

    selector = ""
    for element in list(getattr(page_context, "interactive_elements", []) or []):
        data = element.model_dump() if hasattr(element, "model_dump") else dict(element)
        label = " ".join(
            str(data.get(key) or "")
            for key in ("text", "aria_label", "accessibility_name", "placeholder", "role", "type")
        ).lower()
        editable = str(data.get("type") or "").lower() in {"input", "textarea", "div"} or str(data.get("role") or "").lower() in {"textbox", "searchbox", "combobox"}
        if editable and any(term in label for term in ("search", "contact", "recipient", "start new chat")):
            selector = str(data.get("selector") or "")
            if selector:
                break
    if not selector:
        return None

    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nSemantic Execution Kernel rejected an unsupported ambiguity claim "
            "because no recipient search evidence exists yet."
        ),
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[SuggestedAction(
            action_id=f"ground_contact_search_{name.lower().replace(' ', '_')}",
            action_type="fill",
            target_selector=selector,
            value=name,
            description=f"Search for the requested contact or recipient: {name}",
            reasoning="Search the grounded recipient field before deciding whether multiple exact matches exist.",
            confidence=0.9,
            safety_level="safe",
        )],
    )


def _requested_contact_name(task: str) -> str:
    requested = re.search(
        r"\b(?:contact|recipient|friend)\s+(?:named\s+)?([A-Z][\w .'-]{1,60}?)(?:[.,]|\s+(?:through|on|in|and|to|with)\b|$)",
        str(task or ""),
    )
    return requested.group(1).strip() if requested else ""


def _exact_interactive_matches(page_context: Any, requested_name: str) -> list[str]:
    normalized_requested = " ".join(str(requested_name or "").casefold().split())
    selectors: list[str] = []
    seen: set[str] = set()
    for element in list(getattr(page_context, "interactive_elements", []) or []):
        data = element.model_dump() if hasattr(element, "model_dump") else dict(element)
        element_type = str(data.get("type") or "").lower()
        role = str(data.get("role") or "").lower()
        if element_type in {"input", "textarea", "select"} or role in {"textbox", "searchbox", "combobox"}:
            continue
        labels = {
            " ".join(str(data.get(key) or "").casefold().split())
            for key in ("text", "aria_label", "accessibility_name")
            if str(data.get(key) or "").strip()
        }
        if normalized_requested not in labels:
            continue
        selector = str(data.get("selector") or "").strip()
        if selector and selector not in seen:
            seen.add(selector)
            selectors.append(selector)
    return selectors


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


def _repair_ungrounded_interactive_action(
    result: AnalyzeResponse,
    snapshot: KernelSnapshot,
) -> AnalyzeResponse | None:
    if not snapshot.proposal or not snapshot.eligibility or not result.suggested_actions:
        return None
    if "entity_missing" not in snapshot.eligibility.failures:
        return None
    if snapshot.proposal.action_type not in {"FILL_FORM", "CLICK_ENTITY"}:
        return None
    if not _looks_like_interactive_browser_task(snapshot.mission_state.mission):
        return None

    entity = _best_interactive_entity(snapshot)
    selector = entity.browser_bindings.selector if entity else ""
    if not selector:
        return None

    original = result.suggested_actions[0]
    repaired = SuggestedAction(
        action_id=f"{original.action_id or 'interactive'}_grounded",
        action_type=snapshot.proposal.source_action_type,  # type: ignore[arg-type]
        target_selector=selector,
        value=original.value,
        description=original.description or f"Use grounded element: {entity.title}",
        reasoning=(
            "Semantic Execution Kernel grounded the interactive action to a visible page entity "
            f"({entity.semantic_type}: {entity.title})."
        ),
        confidence=max(float(original.confidence or 0.0), min(0.9, entity.confidence)),
        safety_level=original.safety_level,
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nSemantic Execution Kernel repaired an ungrounded "
            f"{snapshot.proposal.source_action_type} action using current page entities."
        ),
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[repaired],
    )


def _best_interactive_entity(snapshot: KernelSnapshot):
    proposal = snapshot.proposal
    if proposal is None:
        return None
    scored: list[tuple[float, Any]] = []
    for entity in snapshot.entities:
        selector = entity.browser_bindings.selector
        if not selector:
            continue
        if proposal.action_type == "FILL_FORM" and entity.semantic_type not in {"form", "message"}:
            continue
        if proposal.action_type == "CLICK_ENTITY" and entity.semantic_type not in {"button", "link", "message", "document"}:
            continue
        score = _interactive_entity_score(entity, snapshot.mission_state.mission, proposal)
        if score >= 0.62:
            scored.append((score, entity))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], -item[1].confidence, item[1].title))
    return scored[0][1]


def _interactive_entity_score(entity: Any, task: str, proposal: Any) -> float:
    text = _entity_text(entity)
    task_text = str(task or "").lower()
    value = str(proposal.parameters.get("value") or "").lower()
    description = str(proposal.parameters.get("description") or proposal.source_description or "").lower()
    combined_goal = " ".join([task_text, value, description])
    score = 0.0
    if entity.confidence:
        score += min(float(entity.confidence), 1.0) * 0.25
    if proposal.action_type == "FILL_FORM" and entity.semantic_type in {"form", "message"}:
        score += 0.25
    if proposal.action_type == "CLICK_ENTITY" and entity.semantic_type in {"button", "link"}:
        score += 0.22
    if any(term in text for term in ("search", "find", "contact", "name", "to", "recipient", "start new chat")):
        if any(term in combined_goal for term in ("rahul", "contact", "friend", "search")):
            score += 0.33
        if value and not _looks_like_message_body(value):
            score += 0.18
    if any(term in text for term in ("message", "type a message", "write", "compose")):
        if any(term in combined_goal for term in ("hii", "hi", "message", "send")):
            score += 0.33
        if _looks_like_message_body(value):
            score += 0.18
    if any(term in text for term in ("attach", "attachment", "file", "upload", "document")):
        if any(term in combined_goal for term in ("file", "upload", "attach", ".xlsx", ".pdf", ".png", ".jpg")):
            score += 0.36
    if value and value in text:
        score += 0.18
    if any(token and token in text for token in _important_tokens(description)):
        score += 0.12
    state = entity.metadata.get("state", "") if isinstance(entity.metadata, dict) else ""
    if "disabled" in str(state).lower():
        score -= 0.3
    return score


def _entity_text(entity: Any) -> str:
    parts = [
        getattr(entity, "title", "") or "",
        getattr(entity, "semantic_type", "") or "",
    ]
    metadata = getattr(entity, "metadata", {}) or {}
    if isinstance(metadata, dict):
        parts.extend(str(value or "") for value in metadata.values())
    binding = getattr(entity, "browser_bindings", None)
    if binding is not None:
        parts.extend([
            getattr(binding, "selector", "") or "",
            getattr(binding, "selector_id", "") or "",
        ])
    return " ".join(parts).lower()


def _important_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9_.-]{3,}", str(text or "").lower())
        if token not in {"the", "and", "for", "with", "into", "this", "that", "field", "button", "click", "fill"}
    ][:8]


def _looks_like_message_body(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    greetings = {"hi", "hii", "hello", "hey", "thanks", "thank you", "ok", "okay"}
    return text in greetings or len(text.split()) >= 3


def _interactive_entity_refresh_response(
    result: AnalyzeResponse,
    snapshot: KernelSnapshot,
    prior_steps: list[Any],
) -> AnalyzeResponse | None:
    if not snapshot.proposal or not snapshot.eligibility:
        return None
    if "entity_missing" not in snapshot.eligibility.failures:
        return None
    if snapshot.proposal.action_type not in {"FILL_FORM", "CLICK_ENTITY"}:
        return None
    if not _looks_like_interactive_browser_task(snapshot.mission_state.mission):
        return None

    refresh_attempts = _entity_refresh_wait_count(prior_steps)
    if refresh_attempts >= 2:
        return AnalyzeResponse(
            session_id=result.session_id,
            analysis=(
                f"{result.analysis}\n\nSemantic Execution Kernel could not find a grounded "
                "interactive field or button after refreshing the current app page. The page may still be "
                "loading, require login, or not expose the requested target in the current browser state."
            ),
            outcome_kind="ask",
            clarification_question=(
                "I opened the target app, but I cannot find the needed field/button yet. "
                "Please make sure the app is logged in and the target contact or form is visible, then continue."
            ),
            report=None,
            replan=None,
            suggested_actions=[],
        )

    action = SuggestedAction(
        action_id=f"kernel_refresh_entities_{refresh_attempts + 1}",
        action_type="wait",
        target_selector="window",
        value="1500",
        description="Refresh current app page entities before interaction",
        reasoning=(
            "Semantic Execution Kernel needs a fresh observation of dynamic interactive elements "
            "before grounding the requested fill or click action."
        ),
        confidence=0.76,
        safety_level="safe",
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nSemantic Execution Kernel requested a bounded refresh wait because "
            "the proposed interactive action was not yet grounded to a current page entity."
        ),
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[action],
    )


def _entity_refresh_wait_count(prior_steps: list[Any]) -> int:
    count = 0
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        if str(data.get("action_type") or "").lower() != "wait":
            continue
        description = str(data.get("description") or "").lower()
        reasoning = str(data.get("reasoning") or "").lower()
        if "refresh current app page entities" in description or "fresh observation of dynamic interactive elements" in reasoning:
            count += 1
    return count


def _looks_like_interactive_browser_task(task: str) -> bool:
    text = str(task or "").lower()
    action_or_app = any(
        term in text
        for term in (
            "send",
            "message",
            "whatsapp",
            "gmail",
            "mail",
            "chat",
            "profile",
            "setting",
            "dashboard",
            "create",
            "update",
            "save",
        )
    )
    browser_goal = any(term in text for term in ("open", "go to", "navigate", "use", "login", "sign in"))
    return action_or_app and browser_goal


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
    if _is_search_results_page(str(getattr(page_context, "url", "") or "")) and _is_external_search_result_host(host):
        return host in evidence
    if host and host in evidence:
        return not path or path == "/" or path in evidence
    return False


def _is_search_results_page(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "google.com":
        return parsed.path.startswith("/search") or parsed.path.startswith("/sorry") or bool(parsed.query)
    if host == "bing.com":
        return parsed.path.startswith("/search")
    if host == "duckduckgo.com":
        return parsed.path in {"", "/"} and "q=" in parsed.query
    return False


def _is_external_search_result_host(host: str) -> bool:
    if not host:
        return False
    search_hosts = {
        "google.com",
        "bing.com",
        "duckduckgo.com",
        "microsoft.com",
    }
    return host not in search_hosts and not host.endswith(".google.com") and not host.endswith(".bing.com")


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
