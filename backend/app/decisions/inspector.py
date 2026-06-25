"""
V7.5 Decision Center — DecisionInspector.

Single debug surface for the Decision Center.
Aggregates active decisions, priorities, source systems, trust signals, and blockers.
Read-only — does not mutate any state.
"""
from __future__ import annotations

import time
from typing import Any

from app.decisions import registry as reg
from app.decisions import analytics as anal
from app.decisions import timeline as tl
from app.decisions import feed
from app.decisions.models import DecisionPriority, DecisionStatus


class DecisionInspector:

    def inspect(self, mission_id: str = "") -> dict[str, Any]:
        t0 = time.perf_counter()

        if mission_id:
            active   = reg.list_active(mission_id=mission_id, limit=50)
            all_dec  = reg.list_for_mission(mission_id, limit=100)
        else:
            active   = reg.list_active(limit=50)
            all_dec  = reg.list_all(limit=100)

        critical = [d for d in active if d.priority == DecisionPriority.critical]
        high     = [d for d in active if d.priority == DecisionPriority.high]

        # Source breakdown
        sources: dict[str, int] = {}
        for d in active:
            sources[d.source] = sources.get(d.source, 0) + 1

        # Trust signals summary (non-blocking)
        trust_summary: dict = {}
        if mission_id:
            try:
                from app.trust import mission_analyzer as _ma
                m_ev = _ma.analyze(mission_id)
                trust_summary = {
                    "trust_score":       round(m_ev.trust_score, 3),
                    "risk_level":        m_ev.risk_level.value,
                    "approval_required": m_ev.approval_required,
                }
            except Exception:
                pass

        # Blockers
        blockers: list[str] = []
        if mission_id:
            try:
                from app.mission.intelligence import engine as _intel
                report = _intel.run(mission_id)
                if report:
                    blockers = [str(b) for b in (report.blockers or [])]
            except Exception:
                pass

        timeline_summary = tl.summary(mission_id) if mission_id else {}
        analytics        = anal.get_analytics()
        registry_stats   = reg.stats()
        latency_ms       = int((time.perf_counter() - t0) * 1000)

        return {
            "mission_id":        mission_id or None,
            "active_count":      len(active),
            "critical_count":    len(critical),
            "high_count":        len(high),
            "active_decisions":  [d.to_dict() for d in active[:20]],
            "critical_decisions":[d.to_dict() for d in critical],
            "source_breakdown":  sources,
            "trust_signals":     trust_summary,
            "blockers":          blockers,
            "timeline":          timeline_summary,
            "analytics":         analytics,
            "registry_stats":    registry_stats,
            "latency_ms":        latency_ms,
        }


# Module-level singleton
_inspector = DecisionInspector()


def inspect(mission_id: str = "") -> dict:
    return _inspector.inspect(mission_id)
