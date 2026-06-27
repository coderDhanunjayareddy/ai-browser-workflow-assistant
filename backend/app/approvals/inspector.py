"""
V8.0 Human Approval Center — ApprovalInspector.

Single debug surface: pending approvals + decision context + trust signals + timeline.
Read-only. No mutations.
"""
from __future__ import annotations

import time
from typing import Optional

from app.approvals import registry as reg
from app.approvals import analytics as anal
from app.approvals import timeline as tl
from app.approvals import queue as q_mod
from app.approvals.models import ApprovalStatus


def inspect(mission_id: str = "") -> dict:
    t0 = time.perf_counter()

    # Core approval data
    if mission_id:
        all_items = reg.list_for_mission(mission_id, limit=500)
    else:
        all_items = reg.list_all(limit=500)

    pending  = [r for r in all_items if r.status == ApprovalStatus.pending]
    approved = [r for r in all_items if r.status == ApprovalStatus.approved]
    rejected = [r for r in all_items if r.status == ApprovalStatus.rejected]
    critical = q_mod.critical(limit=20) if not mission_id else q_mod.pending_for_mission(mission_id, limit=20)

    # Source breakdown
    source_breakdown: dict[str, int] = {}
    for r in all_items:
        src = r.source_type.value
        source_breakdown[src] = source_breakdown.get(src, 0) + 1

    # Trust signals (non-blocking)
    trust_signals: Optional[dict] = None
    try:
        if mission_id:
            from app.trust import mission_analyzer as _ma
            ev = _ma.analyze(mission_id)
            trust_signals = {
                "trust_score":       round(ev.trust_score, 3),
                "risk_level":        ev.risk_level.value,
                "approval_required": ev.approval_required,
                "reasoning":         ev.reasoning,
            }
    except Exception:
        pass

    # Decision context (non-blocking)
    decision_context: Optional[dict] = None
    try:
        if mission_id:
            from app.decisions import feed as _dec_feed
            decision_context = _dec_feed.summary_for_mission(mission_id)
    except Exception:
        pass

    # Mission context (non-blocking)
    mission_context: Optional[dict] = None
    try:
        if mission_id:
            from app.mission import store as _ms
            m = _ms.get(mission_id)
            if m:
                mission_context = {
                    "mission_id":    m.mission_id,
                    "title":         m.title,
                    "state":         m.state.value,
                    "task_count":    len(m.task_ids),
                    "priority":      m.priority,
                }
    except Exception:
        pass

    # Timeline summary
    tl_summary: dict = {}
    try:
        if mission_id:
            tl_summary = tl.summary(mission_id)
        else:
            recent = tl.recent_global(limit=10)
            tl_summary = {"recent_events": recent, "event_count": len(tl.recent_global(limit=1000))}
    except Exception:
        pass

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "mission_id":       mission_id or None,
        "pending_count":    len(pending),
        "approved_count":   len(approved),
        "rejected_count":   len(rejected),
        "critical_pending": len(critical),
        "pending_approvals": [r.to_dict() for r in pending[:10]],
        "critical_approvals": [r.to_dict() for r in critical[:5]],
        "source_breakdown":  source_breakdown,
        "trust_signals":     trust_signals,
        "decision_context":  decision_context,
        "mission_context":   mission_context,
        "timeline_summary":  tl_summary,
        "analytics":         anal.get_analytics(),
        "registry_stats":    reg.stats(),
        "latency_ms":        latency_ms,
    }
