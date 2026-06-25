"""
V5.5 Mission Intelligence — MissionIntelligenceEngine.

Orchestrates all V5.5 intelligence components into a single MissionIntelligenceReport.

Pipeline (always deterministic, no LLM):
  1. Check registry cache         → return cached report if fresh
  2. get_context(mission_id)      → MissionContext (one call, all data)
  3. blocker_detector.detect()    → list[MissionBlocker]
  4. information_gap.analyze()    → list[MissionInformationGap]
  5. readiness_scorer.score()     → ReadinessDetail (includes readiness_score)
  6. workflow_recommender.recommend() → Optional[MissionWorkflowRecommendation]
  7. next_action_planner.plan()   → MissionNextAction
  8. state_advisor.advise()       → MissionAdvisoryState
  9. Build MissionIntelligenceReport
  10. Store in registry
  11. Record analytics

ADVISORY ONLY — report never mutates Mission or Task state.
"""
from __future__ import annotations

import time
from typing import Optional

from app.mission.context_registry import get_context, MissionContext
from app.mission.intelligence import (
    blocker_detector,
    information_gap,
    readiness_scorer,
    workflow_recommender,
    next_action_planner,
    state_advisor,
    registry as intel_registry,
)
from app.mission.intelligence.models import MissionIntelligenceReport
from app.mission.intelligence import analytics as intel_analytics


def run(mission_id: str, *, force_refresh: bool = False) -> Optional[MissionIntelligenceReport]:
    """
    Run intelligence analysis for a mission.

    Returns None if the mission does not exist.
    Uses cache by default; set force_refresh=True to skip cache.

    All steps are deterministic. No LLM. No DB. < 15ms p95.
    """
    # ── Step 1: Check cache ───────────────────────────────────────────────────
    if not force_refresh:
        cached = intel_registry.get(mission_id)
        if cached is not None:
            intel_analytics.record_cache_hit()
            return cached

    intel_analytics.record_cache_miss()

    # ── Step 2: Load mission context ──────────────────────────────────────────
    t0 = time.perf_counter()

    ctx: Optional[MissionContext] = get_context(mission_id)
    if ctx is None:
        return None

    # ── Step 3: Detect blockers ───────────────────────────────────────────────
    blockers = blocker_detector.detect(ctx)
    intel_analytics.record_blocker_detection(len(blockers))

    # ── Step 4: Analyze information gaps ─────────────────────────────────────
    missing_info = information_gap.analyze(ctx)

    # ── Step 5: Compute readiness score ──────────────────────────────────────
    detail = readiness_scorer.score_from_context(
        ctx,
        blocker_count=len(blockers),
        missing_info_count=len(missing_info),
    )
    readiness_score = detail.score
    intel_analytics.record_readiness_evaluation(readiness_score)

    # ── Step 6: Workflow recommendation ──────────────────────────────────────
    wf_rec = workflow_recommender.recommend(
        mission_title=ctx.mission_title,
        mission_objective=ctx.mission_title,  # objective not on MissionContext; use title
        readiness_score=readiness_score,
    )
    if wf_rec is not None:
        intel_analytics.record_workflow_recommendation()

    # ── Step 7: Next action ───────────────────────────────────────────────────
    next_action = next_action_planner.plan(ctx, blockers, readiness_score)
    intel_analytics.record_next_action_generation()

    # ── Step 8: Advisory state ────────────────────────────────────────────────
    advisory_state = state_advisor.advise(ctx, blockers, readiness_score)

    # ── Step 9: Build report ──────────────────────────────────────────────────
    latency_ms = int((time.perf_counter() - t0) * 1000)

    # Overall confidence: detection confidence + readiness contribution
    raw_confidence = 0.70 * readiness_score + 0.30 * (1.0 if not blockers else 0.5)
    confidence = round(min(1.0, raw_confidence), 3)

    reasoning_parts = [
        f"Mission '{ctx.mission_title}' has {ctx.task_count} task(s).",
        f"Readiness: {readiness_score:.0%}.",
    ]
    if blockers:
        critical_count = sum(1 for b in blockers if b.is_critical)
        reasoning_parts.append(
            f"{len(blockers)} blocker(s) detected ({critical_count} critical)."
        )
    if missing_info:
        reasoning_parts.append(f"{len(missing_info)} information gap(s) identified.")
    if wf_rec:
        reasoning_parts.append(f"Recommended workflow: {wf_rec.workflow_type}.")
    reasoning = " ".join(reasoning_parts)

    report = MissionIntelligenceReport(
        mission_id=mission_id,
        readiness_score=readiness_score,
        confidence=confidence,
        recommended_action=next_action.action,
        suggested_workflow=wf_rec.workflow_type if wf_rec else None,
        blockers=blockers,
        missing_information=missing_info,
        reasoning=reasoning,
        next_action=next_action,
        advisory_state=advisory_state,
        workflow_recommendation=wf_rec,
        latency_ms=latency_ms,
    )

    # ── Step 10: V6.0 tab context enrichment (non-blocking) ──────────────────
    try:
        from app.tabs.context import build as build_tab_context
        tab_ctx = build_tab_context(mission_id)
        report.tab_context = tab_ctx.to_dict()
    except Exception:
        pass  # tab layer is optional — intelligence never fails because of it

    # ── Step 10b: V6.5 trust evaluation enrichment (non-blocking) ────────────
    try:
        from app.trust import mission_analyzer as _trust_ma
        from app.unified import store as _task_store
        from app.unified.models import TaskState as _TaskState
        _tasks = [_task_store.get(tid) for tid in ctx.task_summaries
                  if _task_store.get(ctx.task_summaries[0].get("task_id","") if isinstance(ctx.task_summaries[0], dict) else ctx.task_summaries[0].task_id if hasattr(ctx.task_summaries[0], "task_id") else "")]
        _completed = sum(1 for s in ctx.task_summaries
                         if (s.get("state") if isinstance(s, dict) else getattr(s, "state", "")) == "COMPLETED")
        _failed    = sum(1 for s in ctx.task_summaries
                         if (s.get("state") if isinstance(s, dict) else getattr(s, "state", "")) == "FAILED")
        _trust_ev = _trust_ma.analyze(
            mission_id            = mission_id,
            readiness_score       = readiness_score,
            critical_blockers     = len([b for b in blockers if b.is_critical]),
            missing_info_count    = len(missing_info),
            task_count            = ctx.task_count,
            completed_task_count  = _completed,
            failed_task_count     = _failed,
            tab_count             = report.tab_context.get("tab_count", 0) if report.tab_context else 0,
            workflow_tab_present  = report.tab_context.get("workflow_tab_present", False) if report.tab_context else False,
        )
        report.trust_score        = round(_trust_ev.trust_score, 3)
        report.risk_level         = _trust_ev.risk_level.value
        report.approval_required  = _trust_ev.approval_required
    except Exception:
        pass  # trust layer is optional — intelligence never fails because of it

    # ── Step 10c: V7.0 browser activity enrichment (non-blocking) ───────────
    try:
        from app.browser import registry as _br_reg
        _recent = _br_reg.events_for_mission(mission_id, limit=10)
        report.recent_event_count     = len(_recent)
        _tc = report.tab_context or {}
        report.active_tab_count       = _tc.get("active_tab_count", 0)
        report.browser_activity_score = round(min(1.0, len(_recent) / 10.0), 3)
    except Exception:
        pass  # browser sync is optional — intelligence never fails because of it

    # ── Step 11: Cache the result ─────────────────────────────────────────────
    intel_registry.set_report(mission_id, report)

    # ── Step 12: Record analytics ─────────────────────────────────────────────
    intel_analytics.record_intelligence_run(latency_ms)

    return report
