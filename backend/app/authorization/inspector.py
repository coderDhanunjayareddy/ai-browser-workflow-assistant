"""
V8.8 Execution Authorization Framework — AuthorizationInspector.

Full read-only debug surface for a mission's authorization state.
No mutations. No execution.
"""
from __future__ import annotations

import time
from typing import Optional

from app.authorization import registry as reg
from app.authorization import analytics as anal
from app.authorization import timeline as tl
from app.authorization import readiness as rdns
from app.authorization.models import AuthorizationStatus


def inspect(mission_id: str = "") -> dict:
    t0 = time.perf_counter()

    if mission_id:
        items = reg.list_for_mission(mission_id, limit=500)
    else:
        items = reg.list_all(limit=500)

    active   = [a for a in items if a.status == AuthorizationStatus.active and a.authorized]
    denied   = [a for a in items if a.status == AuthorizationStatus.denied or not a.authorized]
    expired  = [a for a in items if a.status == AuthorizationStatus.expired]
    revoked  = [a for a in items if a.status == AuthorizationStatus.revoked]
    consumed = [a for a in items if a.status == AuthorizationStatus.consumed]
    executable = [a for a in active if a.is_executable]

    # Risk breakdown
    risk_breakdown: dict[str, int] = {}
    for a in items:
        rl = a.risk_level
        risk_breakdown[rl] = risk_breakdown.get(rl, 0) + 1

    # Mission context (non-blocking)
    mission_context: Optional[dict] = None
    try:
        if mission_id:
            from app.mission import store as ms
            m = ms.get(mission_id)
            if m:
                mission_context = {
                    "mission_id": m.mission_id,
                    "title":      m.title,
                    "state":      m.state.value,
                }
    except Exception:
        pass

    # Trust signals (non-blocking)
    trust_signals: Optional[dict] = None
    try:
        if mission_id:
            from app.trust import mission_analyzer as ma
            ev = ma.analyze(mission_id)
            trust_signals = {
                "trust_score":       round(ev.trust_score, 3),
                "risk_level":        ev.risk_level.value,
                "approval_required": ev.approval_required,
            }
    except Exception:
        pass

    # Governance summary (non-blocking)
    governance_context: Optional[dict] = None
    try:
        if mission_id:
            from app.governance import registry as gov_reg
            governance_context = gov_reg.summary_for_mission(mission_id)
    except Exception:
        pass

    # Readiness report (non-blocking)
    readiness_report: Optional[dict] = None
    try:
        if mission_id:
            report = rdns.evaluate(mission_id)
            readiness_report = report.to_dict()
    except Exception:
        pass

    # Timeline summary
    tl_summary: dict = {}
    try:
        if mission_id:
            tl_summary = tl.summary(mission_id)
        else:
            tl_summary = {"recent_events": tl.recent_global(limit=10)}
    except Exception:
        pass

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "mission_id":             mission_id or None,
        "total_authorizations":   len(items),
        "active_count":           len(active),
        "denied_count":           len(denied),
        "expired_count":          len(expired),
        "revoked_count":          len(revoked),
        "consumed_count":         len(consumed),
        "executable_count":       len(executable),
        "active_authorizations":  [a.to_dict() for a in active[:5]],
        "executable_authorizations": [a.to_dict() for a in executable[:5]],
        "risk_breakdown":         risk_breakdown,
        "mission_context":        mission_context,
        "trust_signals":          trust_signals,
        "governance_context":     governance_context,
        "readiness_report":       readiness_report,
        "timeline_summary":       tl_summary,
        "analytics":              anal.get_analytics(),
        "registry_stats":         reg.stats(),
        "latency_ms":             latency_ms,
    }
