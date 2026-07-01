"""
Phase D — Browser Diagnostics (additive, metadata only).

A read-only diagnostic surface for one execution, aggregating:
  page url / title / active frame / active tab
  locator strategy used
  recovery history
  validation history
  retry history
  last screenshot metadata (path + filename only — NO image bytes stored)

Pulls from the BrowserSessionManager (live page) + ExecutionMonitor + ExecutionTimeline.
Metadata only; never stores images.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from app.execution_gateway.browser import session as session_module
from app.execution_gateway.browser import monitor as exec_monitor
from app.execution_gateway.browser import exec_timeline
from app.execution_gateway.browser import metrics as exec_metrics


def diagnostics(execution_id: str) -> dict[str, Any]:
    steps = exec_monitor.steps_for(execution_id)

    # ── live browser state (best-effort) ──
    sess_info = session_module.session_info(execution_id) or {}
    sess = session_module.get(execution_id)
    active_frame = "main"
    last_screenshot = None
    if sess is not None:
        try:
            shot = sess.latest_screenshot()
            if shot:
                last_screenshot = {
                    "path":     shot,
                    "filename": os.path.basename(shot),
                    "exists":   _safe(lambda: os.path.exists(shot)) is True,
                }
        except Exception:
            pass

    # ── per-step histories from the monitor ──
    recovery_history = [
        {"step_id": s.step_id, "order": s.order, "phase": s.phase, "recovery_used": s.recovery_used}
        for s in steps if s.recovery_used
    ]
    validation_history = [
        {"step_id": s.step_id, "order": s.order, "phase": s.phase, "validation_result": s.validation_result}
        for s in steps if s.validation_result is not None
    ]
    retry_history = [
        {"step_id": s.step_id, "order": s.order, "phase": s.phase,
         "attempts": s.attempts, "retries": s.retries}
        for s in steps if s.retries > 0
    ]
    # latest known locator strategy
    locator_strategy_used = None
    for s in reversed(steps):
        if s.locator_strategy:
            locator_strategy_used = s.locator_strategy
            break

    return {
        "execution_id":          execution_id,
        "page_url":              sess_info.get("current_url"),
        "title":                 sess_info.get("current_title"),
        "active_frame":          active_frame,
        "active_tab":            sess_info.get("active_tab_id"),
        "tab_count":             sess_info.get("tab_count"),
        "locator_strategy_used": locator_strategy_used,
        "recovery_history":      recovery_history,
        "validation_history":    validation_history,
        "retry_history":         retry_history,
        "last_screenshot":       last_screenshot,
        "monitor_summary":       exec_monitor.summary(execution_id),
        "timeline_summary":      exec_timeline.summary(execution_id),
        "metrics":               exec_metrics.get_metrics(),
        "session":               sess_info or None,
        # Phase E — Website Intelligence pointer (additive; analysis served on demand)
        "website_intelligence": {
            "available":        sess is not None,
            "live_endpoint":    f"/website-intelligence/live/{execution_id}",
            "analyze_endpoint": "/website-intelligence/analyze",
        },
    }


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None
