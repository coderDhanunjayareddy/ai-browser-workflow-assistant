"""
V8.5 Governance Layer — ContractInspector.

Single debug surface: contracts + source approvals + mission context + trust signals.
Read-only. No mutations.
"""
from __future__ import annotations

import time
from typing import Optional

from app.governance import registry as reg
from app.governance import analytics as anal
from app.governance import timeline as tl
from app.governance import eligibility as elig
from app.governance.models import ContractStatus


def inspect(mission_id: str = "") -> dict:
    t0 = time.perf_counter()

    if mission_id:
        all_contracts = reg.list_for_mission(mission_id, limit=500)
    else:
        all_contracts = reg.list_all(limit=500)

    active   = [c for c in all_contracts if c.status == ContractStatus.active]
    expired  = [c for c in all_contracts if c.status == ContractStatus.expired]
    revoked  = [c for c in all_contracts if c.status == ContractStatus.revoked]
    consumed = [c for c in all_contracts if c.status == ContractStatus.consumed]

    # Eligibility for active contracts
    eligible_contracts = []
    for c in active:
        result = elig.check(c)
        if result.eligible:
            eligible_contracts.append(c)

    # Source breakdown
    source_breakdown: dict[str, int] = {}
    for c in all_contracts:
        src = c.source_type
        source_breakdown[src] = source_breakdown.get(src, 0) + 1

    # Decision source context (non-blocking)
    decision_context: Optional[dict] = None
    try:
        if mission_id:
            from app.decisions import feed as _dec_feed
            decision_context = _dec_feed.summary_for_mission(mission_id)
    except Exception:
        pass

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
            }
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
                    "mission_id": m.mission_id,
                    "title":      m.title,
                    "state":      m.state.value,
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
            tl_summary = {
                "recent_events": recent,
                "event_count":   len(tl.recent_global(limit=1000)),
            }
    except Exception:
        pass

    # V8.8: Authorization summary (non-blocking)
    authorization_summary: Optional[dict] = None
    try:
        if mission_id:
            from app.authorization import registry as _auth_reg
            authorization_summary = _auth_reg.summary_for_mission(mission_id)
    except Exception:
        pass

    latency_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "mission_id":         mission_id or None,
        "total_contracts":    len(all_contracts),
        "active_count":       len(active),
        "expired_count":      len(expired),
        "revoked_count":      len(revoked),
        "consumed_count":     len(consumed),
        "execution_eligible": len(eligible_contracts),
        "active_contracts":   [c.to_dict() for c in active[:5]],
        "eligible_contracts": [c.to_dict() for c in eligible_contracts[:5]],
        "source_breakdown":   source_breakdown,
        "decision_context":   decision_context,
        "trust_signals":      trust_signals,
        "mission_context":    mission_context,
        "authorization":      authorization_summary,
        "timeline_summary":   tl_summary,
        "analytics":          anal.get_analytics(),
        "registry_stats":     reg.stats(),
        "latency_ms":         latency_ms,
    }
