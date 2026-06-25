import time
from typing import Optional

from sqlalchemy.orm import Session

from app.schemas.assist import (
    AssistRequest, AssistResponse, AssistHandoff, AssistMeta,
    StructuredSummary, WorkflowHandoffPayload, ResearchReportSchema, ResearchSourceSchema,
    IntelligenceLayerSchema, ExecutionOpportunitySchema, WorkflowReadinessSchema,
    ExecutionPlanSchema, WorkflowRecommendationSchema, BootstrapFactsSchema,
    GoalNodeSchema, GoalTreeSchema,
)
from app.intent.router import classify
from app.context.tab_context_engine import format_read_view
from app.services import summarization_service, qa_service, followup_service
from app.conversation import manager as conversation_manager
from app.cognitive_core import conversation_manager as cognitive_manager
from app.cognitive_core import intent_continuity, analytics as cognitive_analytics
from app.cognitive_core.workflow_bridge import build_handoff_payload
from app.unified import task_lifecycle, task_timeline as unified_timeline, analytics as task_analytics
from app.unified import workflow_continuity as wf_continuity

_NOT_IMPL_MESSAGES: dict[str, str] = {
    "compare": "Deep comparison is coming in a future update. I've noted the entities you mentioned.",
    "ask": "Page Q&A is coming in a future update. Try 'Summarize this page' for now.",
    "unknown": "I can summarize this page for you. Try clicking 'Summarize this page'.",
}
_DEFAULT_NOT_IMPL = "This capability is coming in a future update. Try 'Summarize this page' for now."


def run(request: AssistRequest, db: Optional[Session] = None) -> AssistResponse:
    t0 = time.monotonic()

    # ── Cognitive Core: load session and enrich message ────────────────────
    session = cognitive_manager.get_or_create(request.conversation_id, db=db)
    enriched = intent_continuity.enrich(request.message, session)

    # ── V4.5 Unified Task Graph: get or create task ────────────────────────
    unified_task = task_lifecycle.get_or_create(
        conversation_id=request.conversation_id,
        original_query=request.message,
        cognitive_session_id=request.conversation_id,
    )
    try:
        task_analytics.record_task_created()
    except Exception:
        pass

    # Classify intent on original message (not enriched — preserves routing)
    intent_result = classify(request.message, request.selection_scope)

    # ── Summarize path ─────────────────────────────────────────────────────
    if intent_result.route == "light" and intent_result.intent == "summarize":
        read_view_str = format_read_view(request.read_view, request.selection_scope)
        context_chars = len(read_view_str)

        summary: StructuredSummary = summarization_service.summarize(
            read_view_str, request.selection_scope
        )
        try:
            followups = followup_service.generate(
                read_view_str=read_view_str,
                context=f"User requested a page summary. TL;DR: {summary.tldr}",
            )
        except Exception:
            followups = []
        latency_ms = int((time.monotonic() - t0) * 1000)

        conversation_manager.append_turn(
            request.conversation_id, role="user", intent="summarize", content=request.message,
        )
        conversation_manager.append_turn(
            request.conversation_id, role="assistant", intent="summarize", content=summary.model_dump(),
        )

        # Cognitive Core: post-turn update (extract from summary entities)
        new_entities = cognitive_manager.process_turn(
            session,
            intent="summarize",
            message=request.message,
            summary_entities=summary.entities,
            response_type="summary",
            handoff_triggered=False,
            db=db,
        )
        cognitive_analytics.record_turn(
            had_entities=bool(new_entities or session.active_entities),
            had_reference=enriched.enrichment_applied,
            reference_resolved=bool(enriched.resolved_entities),
        )

        try:
            unified_timeline.record_assistant_response(unified_task, "summary", summary.tldr)
        except Exception:
            pass

        return AssistResponse(
            conversation_id=request.conversation_id,
            intent="summarize",
            routed_to="light",
            type="summary",
            content=summary,
            citations=[],
            suggested_followups=followups,
            available_actions=summary.available_actions,
            handoff=AssistHandoff(available=False, target=None),
            meta=AssistMeta(
                tokens=0,
                latency_ms=latency_ms,
                cache_hit=False,
                context_chars=context_chars,
            ),
            handoff_payload=None,
            task_id=unified_task.task_id,
            task_state=unified_task.state.value,
        )

    # ── Ask path ───────────────────────────────────────────────────────────
    if intent_result.route == "light" and intent_result.intent == "ask":
        read_view_str = format_read_view(request.read_view, request.selection_scope)
        context_chars = len(read_view_str)
        prior_turns = conversation_manager.get_thread(request.conversation_id)

        # Use enriched message for QA so entity context is available
        question_for_qa = enriched.enriched if enriched.enrichment_applied else request.message

        answer_result = qa_service.answer(
            read_view_str=read_view_str,
            question=question_for_qa,
            prior_turns=prior_turns,
            selection_scope=request.selection_scope,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)

        conversation_manager.append_turn(
            request.conversation_id, role="user", intent="ask", content=request.message,
        )
        conversation_manager.append_turn(
            request.conversation_id, role="assistant", intent="ask", content=answer_result.text,
        )

        # Cognitive Core: post-turn update
        new_entities = cognitive_manager.process_turn(
            session,
            intent="ask",
            message=request.message,
            summary_entities=None,
            response_type="answer",
            handoff_triggered=False,
            db=db,
        )
        cognitive_analytics.record_turn(
            had_entities=bool(new_entities or session.active_entities),
            had_reference=enriched.enrichment_applied,
            reference_resolved=bool(enriched.resolved_entities),
        )

        try:
            unified_timeline.record_assistant_response(unified_task, "answer", answer_result.text[:100])
        except Exception:
            pass

        return AssistResponse(
            conversation_id=request.conversation_id,
            intent="ask",
            routed_to="light",
            type="answer",
            content=answer_result.text,
            citations=[],
            suggested_followups=[],
            available_actions=[],
            handoff=AssistHandoff(available=False, target=None),
            meta=AssistMeta(
                tokens=0,
                latency_ms=latency_ms,
                cache_hit=False,
                context_chars=context_chars,
            ),
            handoff_payload=None,
            task_id=unified_task.task_id,
            task_state=unified_task.state.value,
        )

    # ── Research path (V3.5) ──────────────────────────────────────────────
    if intent_result.route == "research":
        return _handle_research(request, session, enriched, t0, db, unified_task=unified_task)

    # ── Fallback path (compare / unknown) ─────────────────────────────────
    fallback_msg = _NOT_IMPL_MESSAGES.get(intent_result.intent, _DEFAULT_NOT_IMPL)
    latency_ms = int((time.monotonic() - t0) * 1000)

    conversation_manager.append_turn(
        request.conversation_id, role="user", intent=intent_result.intent, content=request.message,
    )

    # Cognitive Core: extract entities from message before building payload
    new_entities = cognitive_manager.process_turn(
        session,
        intent=intent_result.intent,
        message=request.message,
        summary_entities=None,
        response_type="not_implemented",
        handoff_triggered=True,
        db=db,
    )

    # Build enriched handoff payload
    payload: Optional[WorkflowHandoffPayload] = build_handoff_payload(
        query=request.message,
        session=session,
    )

    cognitive_analytics.record_turn(
        had_entities=bool(new_entities or session.active_entities),
        had_reference=enriched.enrichment_applied,
        reference_resolved=bool(enriched.resolved_entities),
    )
    cognitive_analytics.record_handoff(
        entity_count=len(session.active_entities),
        has_goal=session.active_goal is not None,
    )

    try:
        unified_timeline.record_assistant_response(unified_task, "not_implemented", fallback_msg[:80])
    except Exception:
        pass

    return AssistResponse(
        conversation_id=request.conversation_id,
        intent=intent_result.intent,
        routed_to="fallback",
        type="not_implemented",
        content=fallback_msg,
        citations=[],
        suggested_followups=["Summarize this page"],
        available_actions=[],
        handoff=AssistHandoff(available=True, target="workflow"),
        meta=AssistMeta(tokens=0, latency_ms=latency_ms, cache_hit=False, context_chars=0),
        handoff_payload=payload,
        task_id=unified_task.task_id,
        task_state=unified_task.state.value,
    )


def _build_intelligence_schema(intel_result) -> IntelligenceLayerSchema:
    """Convert an IntelligenceResult dataclass into an API-serializable schema."""
    from app.intelligence.models import GoalTree, GoalNode

    opp = intel_result.opportunity
    opp_schema = ExecutionOpportunitySchema(
        detected=opp.detected,
        confidence=opp.confidence,
        action_type=opp.action_type.value,
        required_entities=opp.required_entities,
        missing_information=opp.missing_information,
        workflow_candidate=opp.workflow_candidate,
    )

    readiness_schema = None
    if intel_result.readiness is not None:
        r = intel_result.readiness
        readiness_schema = WorkflowReadinessSchema(
            state=r.state.value,
            ready_entities=r.ready_entities,
            missing_entities=r.missing_entities,
            blocking_reason=r.blocking_reason,
            readiness_score=r.readiness_score,
        )

    plan_schema = None
    if intel_result.execution_plan is not None:
        p = intel_result.execution_plan
        plan_schema = ExecutionPlanSchema(
            plan_id=p.plan_id,
            goal=p.goal,
            workflow_type=p.workflow_type,
            required_inputs=p.required_inputs,
            inferred_inputs=p.inferred_inputs,
            missing_inputs=p.missing_inputs,
            confidence=p.confidence,
            recommended_next_action=p.recommended_next_action,
            approval_level=p.approval_level.value,
        )

    goal_tree_schema = None
    if intel_result.goal_tree is not None:
        gt: GoalTree = intel_result.goal_tree
        nodes_schema: dict[str, GoalNodeSchema] = {
            nid: GoalNodeSchema(
                node_id=n.node_id,
                text=n.text,
                parent_id=n.parent_id,
                children=n.children,
                is_leaf=n.is_leaf,
            )
            for nid, n in gt.nodes.items()
        }
        goal_tree_schema = GoalTreeSchema(
            root_id=gt.root_id,
            nodes=nodes_schema,
            depth=gt.depth,
            leaf_count=gt.leaf_count,
        )

    rec_schemas = [
        WorkflowRecommendationSchema(
            recommendation_id=r.recommendation_id,
            action=r.action,
            readiness=r.readiness.value,
            confidence=r.confidence,
            approval_level=r.approval_level.value,
            plan_id=r.plan_id,
        )
        for r in intel_result.recommendations
    ]

    bootstrap_schema = None
    if intel_result.bootstrap_facts is not None:
        bf = intel_result.bootstrap_facts
        bootstrap_schema = BootstrapFactsSchema(
            query=bf.query,
            goal_text=bf.goal_text,
            workflow_type=bf.workflow_type,
            goal_tree_summary=bf.goal_tree_summary,
            pre_filled_entities=bf.pre_filled_entities,
            research_topic=bf.research_topic,
            research_summary=bf.research_summary,
            confidence=bf.confidence,
            approval_level=bf.approval_level.value,
        )

    return IntelligenceLayerSchema(
        opportunity=opp_schema,
        readiness=readiness_schema,
        execution_plan=plan_schema,
        goal_tree=goal_tree_schema,
        recommendations=rec_schemas,
        bootstrap_facts=bootstrap_schema,
        latency_ms=intel_result.latency_ms,
    )


def _handle_research(request, session, enriched, t0: float, db, unified_task=None) -> AssistResponse:
    """
    V3.5 Research Engine path + V4.0 Intelligence Layer.
    Runs the full research pipeline, then the intelligence layer, and returns
    a research_report + intelligence in AssistResponse.
    """
    from app.research.engine import run_research
    from app.research import analytics as research_analytics
    from app.intelligence.engine import run_intelligence

    conversation_manager.append_turn(
        request.conversation_id, role="user", intent="research", content=request.message,
    )

    # ── V4.5 Task Lifecycle: mark researching ─────────────────────────────
    _utask = unified_task
    if _utask is None:
        _utask = task_lifecycle.get_or_create(
            conversation_id=request.conversation_id,
            original_query=request.message,
        )
    try:
        task_lifecycle.mark_researching(_utask, topic=request.message[:80])
        unified_timeline.record_research_started(_utask, topic=request.message[:80])
    except Exception:
        pass

    try:
        rsession, handoff = run_research(request, session)
        report = rsession.report

        # ── V4.0 Intelligence Layer ────────────────────────────────────────
        research_summary = report.executive_summary if report else ""
        intel_result = run_intelligence(
            query=request.message,
            topic=rsession.topic,
            research_summary=research_summary,
            cognitive_session=session,
        )
        intelligence_schema = _build_intelligence_schema(intel_result)

        # Record intelligence analytics in the research analytics module
        readiness_is_blocked = (
            intel_result.readiness is not None
            and intel_result.readiness.state.value == "BLOCKED"
        )
        research_analytics.record_intelligence_run(
            opportunity_detected=intel_result.opportunity.detected,
            recommendation_count=len(intel_result.recommendations),
            is_blocked=readiness_is_blocked,
        )

        # ── V4.5 Workflow Continuity: attach research + intelligence to task ──
        try:
            wf_continuity.attach_research(
                _utask,
                research_session_id=rsession.session_id,
                topic=rsession.topic,
                executive_summary=report.executive_summary if report else "",
                key_findings=report.key_findings if report else [],
                recommended_actions=report.recommended_actions if report else [],
                confidence_score=report.confidence_score if report else 0.3,
            )
            if intel_result.execution_plan is not None:
                p = intel_result.execution_plan
                wf_continuity.attach_intelligence(
                    _utask,
                    plan_id=p.plan_id,
                    workflow_type=p.workflow_type,
                    approval_level=p.approval_level.value,
                    confidence=p.confidence,
                    missing_inputs=p.missing_inputs,
                    recommended_next_action=p.recommended_next_action,
                )
            task_lifecycle.mark_research_complete(
                _utask,
                research_session_id=rsession.session_id,
                topic=rsession.topic,
                opportunity_detected=intel_result.opportunity.detected,
            )
            unified_timeline.record_research_completed(
                _utask,
                topic=rsession.topic,
                confidence=report.confidence_score if report else 0.3,
                source_count=len(rsession.sources),
            )
            if intel_result.opportunity.detected and intel_result.execution_plan:
                task_analytics.record_research_to_workflow()
                unified_timeline.record_workflow_prepared(
                    _utask,
                    workflow_type=intel_result.execution_plan.workflow_type,
                    approval_level=intel_result.execution_plan.approval_level.value,
                )
        except Exception:
            pass

        # Merge intelligence recommendations into research report's recommended_actions
        extra_rec_actions: list[str] = [
            r.action for r in intel_result.recommendations
        ]

        # Build serializable ResearchReportSchema
        sources_schema = [
            ResearchSourceSchema(
                source_id=s.source_id,
                title=s.title,
                url=s.url,
                source_type=s.source_type.value,
                snippet=s.snippet,
                credibility_score=s.credibility_score,
            )
            for s in rsession.sources
        ]
        base_recommended = (report.recommended_actions if report else [])
        merged_recommended = base_recommended + [
            a for a in extra_rec_actions if a not in base_recommended
        ]
        report_schema = ResearchReportSchema(
            executive_summary=report.executive_summary if report else "",
            key_findings=report.key_findings if report else [],
            supporting_evidence=report.supporting_evidence if report else [],
            risks=report.risks if report else [],
            open_questions=report.open_questions if report else [],
            recommended_actions=merged_recommended,
            confidence_score=report.confidence_score if report else 0.3,
            sources=sources_schema,
            session_id=rsession.session_id,
            topic=rsession.topic,
        )

        content = report.executive_summary if report else f"Research on '{rsession.topic}' completed."
        conversation_manager.append_turn(
            request.conversation_id, role="assistant", intent="research", content=content,
        )

        new_entities = cognitive_manager.process_turn(
            session,
            intent="research",
            message=request.message,
            summary_entities=None,
            response_type="research_report",
            handoff_triggered=bool(handoff),
            db=db,
        )
        cognitive_analytics.record_turn(
            had_entities=bool(new_entities or session.active_entities),
            had_reference=enriched.enrichment_applied,
            reference_resolved=bool(enriched.resolved_entities),
        )

        # Upgrade handoff when intelligence layer detected an opportunity
        effective_handoff = handoff
        if intel_result.opportunity.detected and effective_handoff is None:
            # Intelligence detected an opportunity; surface handoff for workflow tab
            from app.cognitive_core.workflow_bridge import build_handoff_payload
            effective_handoff = build_handoff_payload(
                query=request.message,
                session=session,
            )

        latency_ms = int((time.monotonic() - t0) * 1000)

        # Build suggested followups, including intelligence-driven ones
        followups = ["Summarize this page", f"Tell me more about {rsession.topic}"]
        if intel_result.opportunity.detected and intel_result.readiness is not None:
            if intel_result.readiness.state.value == "READY":
                followups.append("Open in Workflow to execute")
            elif intel_result.readiness.state.value == "PARTIALLY_READY":
                followups.append("Prepare workflow with current context")

        return AssistResponse(
            conversation_id=request.conversation_id,
            intent="research",
            routed_to="research",
            type="research_report",
            content=content,
            citations=[s.url for s in rsession.sources if s.url],
            suggested_followups=followups,
            available_actions=[],
            handoff=AssistHandoff(
                available=bool(effective_handoff),
                target="workflow" if effective_handoff else None,
            ),
            meta=AssistMeta(tokens=0, latency_ms=latency_ms, cache_hit=False, context_chars=0),
            handoff_payload=effective_handoff,
            research_report=report_schema,
            intelligence=intelligence_schema,
            task_id=_utask.task_id,
            task_state=_utask.state.value,
        )

    except Exception:
        latency_ms = int((time.monotonic() - t0) * 1000)
        try:
            task_lifecycle.mark_failed(_utask, reason="research_engine_exception")
        except Exception:
            pass
        return AssistResponse(
            conversation_id=request.conversation_id,
            intent="research",
            routed_to="research",
            type="not_implemented",
            content="Research could not be completed. Please try again.",
            citations=[],
            suggested_followups=["Summarize this page"],
            available_actions=[],
            handoff=AssistHandoff(available=False),
            meta=AssistMeta(tokens=0, latency_ms=latency_ms, cache_hit=False, context_chars=0),
            handoff_payload=None,
            research_report=None,
            intelligence=None,
            task_id=_utask.task_id,
            task_state=_utask.state.value,
        )
