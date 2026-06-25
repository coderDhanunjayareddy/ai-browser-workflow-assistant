"""
V6.5 Trust Engine — REST API routes.

Endpoints:
  GET  /trust/evaluate                  → evaluate a named action (query param)
  POST /trust/action                    → evaluate a specific action
  POST /trust/workflow                  → evaluate a workflow
  POST /trust/tab                       → evaluate mission tab trust
  POST /trust/mission                   → evaluate full mission trust
  GET  /trust/analytics                 → trust analytics counters
  GET  /trust/inspect/{mission_id}      → full trust inspector for a mission

All responses are ADVISORY. No actions are executed. No approvals are granted.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.trust import (
    action_analyzer,
    workflow_analyzer,
    tab_analyzer,
    mission_analyzer,
    analytics as trust_analytics,
    registry  as trust_registry,
)
from app.trust.models import TargetType, RiskLevel, RISK_LEVEL_ORDER
from app.schemas.trust import (
    TrustEvaluationSchema,
    TrustAnalyticsSchema,
    TrustInspectorSchema,
    EvaluateActionRequest,
    EvaluateWorkflowRequest,
    EvaluateTabRequest,
    EvaluateMissionRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trust", tags=["trust"])


def _to_schema(ev) -> TrustEvaluationSchema:
    return TrustEvaluationSchema(
        evaluation_id     = ev.evaluation_id,
        target_type       = ev.target_type.value,
        target_id         = ev.target_id,
        trust_score       = round(ev.trust_score, 3),
        risk_level        = ev.risk_level.value,
        approval_required = ev.approval_required,
        confidence        = round(ev.confidence, 3),
        reasoning         = ev.reasoning,
        created_at        = ev.created_at,
    )


# ── GET /trust/evaluate ───────────────────────────────────────────────────────

@router.get("/evaluate", response_model=TrustEvaluationSchema)
def evaluate_action_get(action_type: str, readiness_score: float = 0.5):
    """Quick action trust evaluation via query param."""
    ev = action_analyzer.analyze(
        action_type     = action_type,
        readiness_score = readiness_score,
    )
    trust_registry.set_evaluation(ev)
    return _to_schema(ev)


# ── POST /trust/action ────────────────────────────────────────────────────────

@router.post("/action", response_model=TrustEvaluationSchema)
def evaluate_action(req: EvaluateActionRequest):
    """Evaluate trust for a browser action."""
    ev = action_analyzer.analyze(
        action_type     = req.action_type,
        action_id       = req.action_id,
        workflow_type   = req.workflow_type,
        readiness_score = req.readiness_score,
        blocker_count   = req.blocker_count,
    )
    trust_registry.set_evaluation(ev)
    return _to_schema(ev)


# ── POST /trust/workflow ──────────────────────────────────────────────────────

@router.post("/workflow", response_model=TrustEvaluationSchema)
def evaluate_workflow(req: EvaluateWorkflowRequest):
    """Evaluate trust for a workflow before execution."""
    ev = workflow_analyzer.analyze(
        workflow_type          = req.workflow_type,
        workflow_id            = req.workflow_id,
        readiness_score        = req.readiness_score,
        critical_blocker_count = req.critical_blocker_count,
        missing_info_count     = req.missing_info_count,
        workflow_tab_present   = req.workflow_tab_present,
    )
    trust_registry.set_evaluation(ev)
    return _to_schema(ev)


# ── POST /trust/tab ───────────────────────────────────────────────────────────

@router.post("/tab", response_model=TrustEvaluationSchema)
def evaluate_tab(req: EvaluateTabRequest):
    """Evaluate tab trust for a mission."""
    ev = tab_analyzer.analyze(
        mission_id   = req.mission_id,
        tab_context  = req.tab_context,
        tab_findings = req.tab_findings,
    )
    trust_registry.set_evaluation(ev)
    return _to_schema(ev)


# ── POST /trust/mission ───────────────────────────────────────────────────────

@router.post("/mission", response_model=TrustEvaluationSchema)
def evaluate_mission(req: EvaluateMissionRequest):
    """Evaluate mission-level trust."""
    ev = mission_analyzer.analyze(
        mission_id            = req.mission_id,
        readiness_score       = req.readiness_score,
        critical_blockers     = req.critical_blockers,
        missing_info_count    = req.missing_info_count,
        task_count            = req.task_count,
        completed_task_count  = req.completed_task_count,
        failed_task_count     = req.failed_task_count,
        tab_count             = req.tab_count,
        orphan_tab_count      = req.orphan_tab_count,
        workflow_tab_present  = req.workflow_tab_present,
    )
    trust_registry.set_evaluation(ev)
    return _to_schema(ev)


# ── GET /trust/analytics ──────────────────────────────────────────────────────

@router.get("/analytics", response_model=TrustAnalyticsSchema)
def get_analytics():
    """Return trust evaluation counters."""
    return TrustAnalyticsSchema(**trust_analytics.get_analytics())


# ── GET /trust/inspect/{mission_id} ──────────────────────────────────────────

@router.get("/inspect/{mission_id}", response_model=TrustInspectorSchema)
def inspect_trust(mission_id: str):
    """
    Full trust inspector for a mission.

    Aggregates mission trust, tab trust, and workflow trust from live data.
    Advisory only — no actions executed.
    """
    evaluations: dict[str, Optional[TrustEvaluationSchema]] = {
        "mission_trust":  None,
        "tab_trust":      None,
        "workflow_trust": None,
    }

    # --- Mission trust (live, from intelligence engine) ---
    try:
        from app.mission import store as mission_store
        from app.mission.intelligence import engine as intel_engine
        from app.unified import store as task_store

        m = mission_store.get(mission_id)
        if m is None:
            raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")

        intel = intel_engine.run(mission_id)

        tasks = [task_store.get(tid) for tid in m.task_ids if task_store.get(tid)]
        from app.unified.models import TaskState
        completed = sum(1 for t in tasks if t.state == TaskState.completed)
        failed    = sum(1 for t in tasks if t.state == TaskState.failed)

        m_ev = mission_analyzer.analyze(
            mission_id            = mission_id,
            readiness_score       = intel.readiness_score if intel else 0.0,
            critical_blockers     = len(intel.critical_blockers) if intel else 0,
            missing_info_count    = len(intel.missing_information) if intel else 0,
            task_count            = len(tasks),
            completed_task_count  = completed,
            failed_task_count     = failed,
        )
        trust_registry.set_evaluation(m_ev)
        evaluations["mission_trust"] = _to_schema(m_ev)

    except HTTPException:
        raise
    except Exception:
        pass

    # --- Tab trust (from V6.0 tab layer) ---
    try:
        from app.tabs.context import build as build_tab_ctx
        from app.tabs.intelligence import analyze as tab_intel_analyze

        tab_ctx = build_tab_ctx(mission_id)
        tab_intel = tab_intel_analyze(tab_ctx)

        t_ev = tab_analyzer.analyze(
            mission_id   = mission_id,
            tab_context  = tab_ctx.to_dict(),
            tab_findings = [f.to_dict() for f in tab_intel.findings],
        )
        trust_registry.set_evaluation(t_ev)
        evaluations["tab_trust"] = _to_schema(t_ev)

    except Exception:
        pass

    # --- Workflow trust (from mission intelligence recommended workflow) ---
    try:
        if intel and intel.suggested_workflow:
            wf_ev = workflow_analyzer.analyze(
                workflow_type          = intel.suggested_workflow,
                readiness_score        = intel.readiness_score,
                critical_blocker_count = len(intel.critical_blockers),
                missing_info_count     = len(intel.missing_information),
            )
            trust_registry.set_evaluation(wf_ev)
            evaluations["workflow_trust"] = _to_schema(wf_ev)
    except Exception:
        pass

    # --- Aggregate overall trust ---
    all_evals = [e for e in evaluations.values() if e is not None]
    if all_evals:
        overall_score = sum(e.trust_score for e in all_evals) / len(all_evals)
        risk_order = {v: k for k, v in enumerate(
            ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        )}
        overall_risk = max(
            (e.risk_level for e in all_evals),
            key=lambda r: risk_order.get(r, 0),
        )
        overall_approval = any(e.approval_required for e in all_evals)
    else:
        overall_score    = 0.5
        overall_risk     = "MEDIUM"
        overall_approval = False

    return TrustInspectorSchema(
        mission_id          = mission_id,
        mission_trust       = evaluations["mission_trust"],
        tab_trust           = evaluations["tab_trust"],
        workflow_trust      = evaluations["workflow_trust"],
        overall_trust_score = round(overall_score, 3),
        overall_risk_level  = overall_risk,
        approval_required   = overall_approval,
    )
