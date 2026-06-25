"""
V7.0 Live Browser Sync Layer — BrowserEventInspector.

Single debugging surface: aggregates recent events, tab state, trust, intelligence,
recommendations, and timeline summary for a given mission.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.browser import registry as event_reg
from app.browser import timeline as tl
from app.browser.recommendation import refresh as rec_refresh


class BrowserEventInspector:

    def inspect(self, mission_id: str, event_limit: int = 20) -> dict[str, Any]:
        t0 = time.perf_counter()

        recent_events = [e.to_dict() for e in
                         event_reg.events_for_mission(mission_id, limit=event_limit)]

        tab_context: Optional[dict] = None
        try:
            from app.tabs.context import build as _build_tab_ctx
            ctx = _build_tab_ctx(mission_id)
            tab_context = ctx.to_dict()
        except Exception:
            pass

        tab_findings: list[dict] = []
        try:
            from app.tabs.context import build as _build_tab_ctx
            from app.tabs.intelligence import analyze as _analyze_tabs
            ctx = _build_tab_ctx(mission_id)
            res = _analyze_tabs(ctx)
            tab_findings = [f.to_dict() for f in res.findings]
        except Exception:
            pass

        trust_summary: Optional[dict] = None
        try:
            from app.trust import mission_analyzer as _ma
            from app.trust import tab_analyzer as _ta
            m_ev = _ma.analyze(mission_id)
            t_ev = _ta.analyze(mission_id, tab_context=tab_context)
            trust_summary = {
                "mission_trust_score": round(m_ev.trust_score, 3),
                "mission_risk_level":  m_ev.risk_level.value,
                "approval_required":   m_ev.approval_required,
                "tab_trust_score":     round(t_ev.trust_score, 3),
            }
        except Exception:
            pass

        intel_summary: Optional[dict] = None
        try:
            from app.mission.intelligence import engine as _intel
            report = _intel.run(mission_id)
            if report:
                intel_summary = {
                    "readiness_score":     report.readiness_score,
                    "advisory_state":      report.advisory_state.value,
                    "recommended_action":  report.recommended_action,
                    "blocker_count":       len(report.blockers),
                    "browser_activity_score": getattr(report, "browser_activity_score", None),
                    "recent_event_count":    getattr(report, "recent_event_count", None),
                }
        except Exception:
            pass

        signals = []
        try:
            raw = rec_refresh(mission_id)
            signals = [s.to_dict() for s in raw]
        except Exception:
            pass

        timeline_summary = tl.summary(mission_id)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "mission_id":      mission_id,
            "recent_events":   recent_events,
            "tab_context":     tab_context,
            "tab_findings":    tab_findings,
            "trust":           trust_summary,
            "intelligence":    intel_summary,
            "recommendations": signals,
            "timeline":        timeline_summary,
            "latency_ms":      latency_ms,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_inspector = BrowserEventInspector()


def inspect(mission_id: str, event_limit: int = 20) -> dict:
    return _inspector.inspect(mission_id, event_limit)
