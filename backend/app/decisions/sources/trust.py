"""
V7.5 Decision Center — Trust source adapter.

Wraps V6.5 TrustEvaluation outputs into DecisionItems.
Does NOT duplicate trust engine logic.
Does NOT store evaluations — reads from TrustRegistry or re-runs analyzers.
"""
from __future__ import annotations

from typing import Optional

from app.decisions.models import (
    DecisionItem, DecisionType, DecisionPriority, make_decision,
)
from app.decisions.priority import PriorityEngine

_SOURCE   = "trust_engine"
_priority = PriorityEngine()


def decisions_for_mission(mission_id: str) -> list[DecisionItem]:
    """
    Produce DecisionItems from V6.5 trust evaluation for a mission.
    Returns [] if trust engine unavailable or mission does not exist.
    """
    items: list[DecisionItem] = []
    try:
        from app.trust import mission_analyzer as _ma
        from app.trust import tab_analyzer    as _ta
        from app.trust.models import RiskLevel

        m_ev = _ma.analyze(mission_id)
        t_ev = _ta.analyze(mission_id, tab_context=None)

        # Mission-level trust warning
        if m_ev.risk_level in (RiskLevel.high, RiskLevel.critical):
            p = (DecisionPriority.critical
                 if m_ev.risk_level == RiskLevel.critical
                 else DecisionPriority.high)
            items.append(make_decision(
                decision_type = DecisionType.trust_warning,
                priority      = p,
                title         = f"Mission trust risk: {m_ev.risk_level.value}",
                description   = (
                    f"Trust score {round(m_ev.trust_score, 3)} — "
                    f"risk level {m_ev.risk_level.value}. "
                    f"{m_ev.reasoning}"
                ),
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {
                    "trust_score":       round(m_ev.trust_score, 3),
                    "risk_level":        m_ev.risk_level.value,
                    "approval_required": m_ev.approval_required,
                },
            ))

        # Approval required → explicit recommendation
        if m_ev.approval_required:
            items.append(make_decision(
                decision_type = DecisionType.recommendation,
                priority      = DecisionPriority.high,
                title         = "Human approval required before execution",
                description   = (
                    "Trust policy requires explicit human approval. "
                    "Review mission state and risk level before proceeding."
                ),
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {"reason": "approval_required"},
            ))

        # Tab-level trust warning (separate from mission)
        if t_ev.risk_level in (RiskLevel.high, RiskLevel.critical):
            p_tab = (DecisionPriority.critical
                     if t_ev.risk_level == RiskLevel.critical
                     else DecisionPriority.medium)
            items.append(make_decision(
                decision_type = DecisionType.trust_warning,
                priority      = p_tab,
                title         = f"Tab trust risk: {t_ev.risk_level.value}",
                description   = (
                    f"Tab trust score {round(t_ev.trust_score, 3)}. "
                    "Some open tabs may have security or quality issues."
                ),
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {"tab_trust_score": round(t_ev.trust_score, 3)},
            ))

    except Exception:
        pass

    return items
