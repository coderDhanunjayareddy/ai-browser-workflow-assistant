"""
Phase F — Workflow Trace (diagnostics improvement, additive & read-only).

Consolidates the EXISTING Phase D observability (ExecutionMonitor + ExecutionTimeline +
browser diagnostics) into a single per-execution "workflow trace":

  workflow trace (ordered per-step lifecycle), recovery timeline, locator strategy used,
  validation history, retry history, execution summary, and a semantic-snapshot pointer.

Pure aggregation of data the platform already records. No new state. Never reads a live
Playwright page from a worker thread (honors the Phase E thread-affinity constraint) —
the semantic snapshot is exposed as a pointer / served on demand via Website Intelligence.
"""
from __future__ import annotations

from typing import Any, Optional

from app.execution_gateway.browser import monitor as exec_monitor
from app.execution_gateway.browser import exec_timeline
from app.execution_gateway.browser import session as session_module


def workflow_trace(execution_id: str) -> dict[str, Any]:
    steps = exec_monitor.steps_for(execution_id)
    events = exec_timeline.events_for(execution_id, limit=1000)

    # per-step trace: monitor record + its lifecycle events, in order
    events_by_step: dict[str, list[dict]] = {}
    for e in events:
        events_by_step.setdefault(e["step_id"], []).append({
            "event_type": e["event_type"], "order": e["order"], "timestamp": e["timestamp"],
            "detail": e["detail"],
        })
    step_trace = [
        {
            "step_id":          s.step_id,
            "order":            s.order,
            "phase":            s.phase,
            "outcome":          s.outcome,
            "attempts":         s.attempts,
            "retries":          s.retries,
            "elapsed_ms":       s.elapsed_ms,
            "validation_result": s.validation_result,
            "failure_category": s.failure_category,
            "locator_strategy": s.locator_strategy,
            "recovery_used":    s.recovery_used,
            "lifecycle":        events_by_step.get(s.step_id, []),
        }
        for s in sorted(steps, key=lambda s: s.order)
    ]

    recovery_timeline = [
        {"step_id": s.step_id, "order": s.order, "recovery_used": s.recovery_used,
         "outcome": s.outcome, "attempts": s.attempts}
        for s in sorted(steps, key=lambda s: s.order) if s.recovery_used
    ]
    validation_history = [
        {"step_id": s.step_id, "order": s.order, "validation_result": s.validation_result}
        for s in sorted(steps, key=lambda s: s.order) if s.validation_result is not None
    ]
    retry_history = [
        {"step_id": s.step_id, "order": s.order, "attempts": s.attempts, "retries": s.retries}
        for s in sorted(steps, key=lambda s: s.order) if s.retries > 0
    ]
    locator_strategy_used = None
    for s in sorted(steps, key=lambda s: s.order, reverse=True):
        if s.locator_strategy:
            locator_strategy_used = s.locator_strategy
            break

    sess = session_module.get(execution_id)
    return {
        "execution_id":          execution_id,
        "step_trace":            step_trace,
        "recovery_timeline":     recovery_timeline,
        "validation_history":    validation_history,
        "retry_history":         retry_history,
        "locator_strategy_used": locator_strategy_used,
        "execution_summary":     exec_monitor.summary(execution_id),
        "timeline_summary":      exec_timeline.summary(execution_id),
        "semantic_snapshot": {
            "available":        sess is not None,
            "live_endpoint":    f"/website-intelligence/live/{execution_id}",
            "analyze_endpoint": "/website-intelligence/analyze",
        },
    }


def has_trace(execution_id: str) -> bool:
    return bool(exec_monitor.steps_for(execution_id)) or \
        exec_timeline.summary(execution_id)["event_count"] > 0


def semantic_snapshot_of(html: str, *, url: str = "", title: str = "") -> Optional[dict]:
    """Deterministic semantic snapshot of captured HTML (reuses Website Intelligence)."""
    try:
        from app.website_intelligence import analyzer
        return analyzer.analyze_html(html, url=url, title=title).to_dict()
    except Exception:
        return None
