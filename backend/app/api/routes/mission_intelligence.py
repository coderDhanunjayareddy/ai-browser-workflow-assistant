"""
V5.5 Mission Intelligence Layer — REST API.

5 read-only endpoints. All responses are advisory — no state mutations.

Endpoints:
  GET /mission/{id}/intelligence          → full MissionIntelligenceReport
  GET /mission/{id}/readiness             → readiness score + advisory state
  GET /mission/{id}/blockers              → list of detected blockers
  GET /mission/{id}/next-action           → single recommended next action
  GET /mission/{id}/workflow-recommendation → workflow type recommendation
  GET /mission/intelligence/analytics     → intelligence analytics counters
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.mission.intelligence import engine as intel_engine
from app.mission.intelligence import registry as intel_registry
from app.mission.intelligence import blocker_detector, readiness_scorer, workflow_recommender
from app.mission.intelligence import next_action_planner, state_advisor, analytics as intel_analytics
from app.mission.context_registry import get_context
from app.schemas.mission_intelligence import (
    MissionIntelligenceReportSchema,
    MissionReadinessSchema,
    MissionBlockersSchema,
    MissionBlockerSchema,
    MissionNextActionResponseSchema,
    MissionWorkflowRecommendationResponseSchema,
    MissionIntelligenceAnalyticsSchema,
    MissionNextActionSchema,
    MissionWorkflowRecommendationSchema,
)

router = APIRouter(tags=["mission-intelligence"])


def _report_or_404(mission_id: str, force: bool = False):
    report = intel_engine.run(mission_id, force_refresh=force)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return report


def _ctx_or_404(mission_id: str):
    ctx = get_context(mission_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return ctx


def _blocker_schema(b) -> MissionBlockerSchema:
    return MissionBlockerSchema(
        code=b.code,
        description=b.description,
        severity=b.severity.value,
        task_id=b.task_id,
    )


# ── GET /mission/{id}/intelligence ────────────────────────────────────────────

@router.get("/{mission_id}/intelligence", response_model=MissionIntelligenceReportSchema)
def get_intelligence(mission_id: str, force_refresh: bool = False):
    """Full advisory intelligence report for a mission."""
    report = _report_or_404(mission_id, force=force_refresh)

    wf_schema = None
    if report.workflow_recommendation:
        wf = report.workflow_recommendation
        wf_schema = MissionWorkflowRecommendationSchema(
            workflow_type=wf.workflow_type,
            action_type=wf.action_type,
            confidence=wf.confidence,
            reasoning=wf.reasoning,
        )

    return MissionIntelligenceReportSchema(
        mission_id=report.mission_id,
        readiness_score=report.readiness_score,
        confidence=report.confidence,
        recommended_action=report.recommended_action,
        suggested_workflow=report.suggested_workflow,
        blockers=[_blocker_schema(b) for b in report.blockers],
        missing_information=[
            {"field_name": g.field_name, "description": g.description, "category": g.category.value}
            for g in report.missing_information
        ],
        reasoning=report.reasoning,
        next_action=MissionNextActionSchema(
            action=report.next_action.action,
            reasoning=report.next_action.reasoning,
            priority=report.next_action.priority,
        ),
        advisory_state=report.advisory_state.value,
        workflow_recommendation=wf_schema,
        generated_at=report.generated_at,
        latency_ms=report.latency_ms,
        tab_context=report.tab_context,
        trust_score=report.trust_score,
        risk_level=report.risk_level,
        approval_required=report.approval_required,
        browser_activity_score=report.browser_activity_score,
        active_tab_count=report.active_tab_count,
        recent_event_count=report.recent_event_count,
    )


# ── GET /mission/{id}/readiness ───────────────────────────────────────────────

@router.get("/{mission_id}/readiness", response_model=MissionReadinessSchema)
def get_readiness(mission_id: str):
    """Readiness score and advisory state for a mission."""
    report = _report_or_404(mission_id)
    return MissionReadinessSchema(
        mission_id=mission_id,
        readiness_score=report.readiness_score,
        advisory_state=report.advisory_state.value,
        blockers=[_blocker_schema(b) for b in report.blockers],
    )


# ── GET /mission/{id}/blockers ────────────────────────────────────────────────

@router.get("/{mission_id}/blockers", response_model=MissionBlockersSchema)
def get_blockers(mission_id: str):
    """Detected blockers for a mission (computed fresh, no cache)."""
    ctx = _ctx_or_404(mission_id)
    blockers = blocker_detector.detect(ctx)
    return MissionBlockersSchema(
        mission_id=mission_id,
        blocker_count=len(blockers),
        blockers=[_blocker_schema(b) for b in blockers],
    )


# ── GET /mission/{id}/next-action ─────────────────────────────────────────────

@router.get("/{mission_id}/next-action", response_model=MissionNextActionResponseSchema)
def get_next_action(mission_id: str):
    """Single recommended next action for a mission (advisory only)."""
    report = _report_or_404(mission_id)
    return MissionNextActionResponseSchema(
        mission_id=mission_id,
        next_action=MissionNextActionSchema(
            action=report.next_action.action,
            reasoning=report.next_action.reasoning,
            priority=report.next_action.priority,
        ),
    )


# ── GET /mission/{id}/workflow-recommendation ─────────────────────────────────

@router.get(
    "/{mission_id}/workflow-recommendation",
    response_model=MissionWorkflowRecommendationResponseSchema,
)
def get_workflow_recommendation(mission_id: str):
    """Advisory workflow type recommendation for a mission."""
    report = _report_or_404(mission_id)
    wf_schema = None
    if report.workflow_recommendation:
        wf = report.workflow_recommendation
        wf_schema = MissionWorkflowRecommendationSchema(
            workflow_type=wf.workflow_type,
            action_type=wf.action_type,
            confidence=wf.confidence,
            reasoning=wf.reasoning,
        )
    return MissionWorkflowRecommendationResponseSchema(
        mission_id=mission_id,
        workflow_recommendation=wf_schema,
        readiness_score=report.readiness_score,
    )


# ── GET /mission/intelligence/analytics ───────────────────────────────────────

@router.get("/intelligence/analytics", response_model=MissionIntelligenceAnalyticsSchema)
def get_intelligence_analytics():
    """Intelligence layer analytics counters."""
    data = intel_analytics.get_analytics()
    return MissionIntelligenceAnalyticsSchema(**data)
