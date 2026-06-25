"""
V7.0 Live Browser Sync Layer — TrustRefreshEngine.

Triggered by tab events that affect trust signals (critical changes, orphans, duplicates).
Invalidates cached trust evaluations and recomputes via V6.5 analyzers.
Trust rules are unchanged — only the refresh pathway is new.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrustRefreshResult:
    mission_id:        str
    refreshed:         bool
    trust_score:       Optional[float] = None
    risk_level:        Optional[str]   = None
    approval_required: Optional[bool]  = None
    tab_trust_score:   Optional[float] = None
    latency_ms:        int             = 0
    error:             Optional[str]   = None

    def to_dict(self) -> dict:
        return {
            "mission_id":        self.mission_id,
            "refreshed":         self.refreshed,
            "trust_score":       self.trust_score,
            "risk_level":        self.risk_level,
            "approval_required": self.approval_required,
            "tab_trust_score":   self.tab_trust_score,
            "latency_ms":        self.latency_ms,
            "error":             self.error,
        }


class TrustRefreshEngine:

    def refresh(self, mission_id: str, reason: str = "") -> TrustRefreshResult:
        t0 = time.perf_counter()

        trust_score       : Optional[float] = None
        risk_level        : Optional[str]   = None
        approval_required : Optional[bool]  = None
        tab_trust_score   : Optional[float] = None

        try:
            from app.trust import registry as trust_reg
            from app.trust.models import TargetType

            # Invalidate cached evaluations for this mission
            trust_reg.invalidate(TargetType.mission, mission_id)
            trust_reg.invalidate(TargetType.tab,     mission_id)

            # Recompute mission trust
            from app.trust import mission_analyzer as _mission_ta
            _m_ev = _mission_ta.analyze(mission_id)
            trust_score       = round(_m_ev.trust_score, 3)
            risk_level        = _m_ev.risk_level.value
            approval_required = _m_ev.approval_required

            # Recompute tab trust using fresh tab context
            from app.trust import tab_analyzer as _tab_ta
            from app.tabs.context import build as _build_tab_ctx
            try:
                ctx      = _build_tab_ctx(mission_id)
                ctx_dict = ctx.to_dict()
            except Exception:
                ctx_dict = None

            _t_ev = _tab_ta.analyze(mission_id, tab_context=ctx_dict)
            tab_trust_score = round(_t_ev.trust_score, 3)

        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return TrustRefreshResult(
                mission_id = mission_id,
                refreshed  = False,
                error      = str(exc),
                latency_ms = latency_ms,
            )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        return TrustRefreshResult(
            mission_id        = mission_id,
            refreshed         = True,
            trust_score       = trust_score,
            risk_level        = risk_level,
            approval_required = approval_required,
            tab_trust_score   = tab_trust_score,
            latency_ms        = latency_ms,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = TrustRefreshEngine()


def refresh(mission_id: str, reason: str = "") -> TrustRefreshResult:
    return _engine.refresh(mission_id, reason)
