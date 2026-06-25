"""
V7.5 Decision Center — Mission source adapter.

Wraps mission intelligence blockers and low-readiness signals into DecisionItems.
Does NOT duplicate intelligence engine logic.
"""
from __future__ import annotations

from app.decisions.models import (
    DecisionItem, DecisionType, DecisionPriority, make_decision,
)

_SOURCE = "mission_intelligence"


def decisions_for_mission(mission_id: str) -> list[DecisionItem]:
    """
    Produce DecisionItems from V5.5 MissionIntelligenceReport:
    - BLOCKER items for each blocking issue
    - WARNING for low readiness
    Returns [] on any error.
    """
    items: list[DecisionItem] = []
    try:
        from app.mission.intelligence import engine as _intel
        report = _intel.run(mission_id)
        if report is None:
            return []

        # Blockers → BLOCKER decision items
        for blocker in (report.blockers or []):
            blocker_text = str(blocker)
            items.append(make_decision(
                decision_type = DecisionType.blocker,
                priority      = DecisionPriority.high,
                title         = f"Mission blocker: {blocker_text[:60]}",
                description   = f"Blocker preventing mission progress: {blocker_text}",
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {"blocker": blocker_text},
            ))

        # Low readiness warning (< 0.40)
        rs = getattr(report, "readiness_score", 1.0)
        if rs is not None and rs < 0.40:
            items.append(make_decision(
                decision_type = DecisionType.recommendation,
                priority      = DecisionPriority.medium,
                title         = f"Low mission readiness ({rs:.0%})",
                description   = (
                    f"Mission readiness score is {rs:.0%}, below the 40% threshold. "
                    "Address blockers and fill information gaps before proceeding."
                ),
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {"readiness_score": rs},
            ))

        # Recommended action from intelligence → opportunity
        rec = getattr(report, "recommended_action", None)
        if rec and rec not in ("", "none", "None"):
            items.append(make_decision(
                decision_type = DecisionType.opportunity,
                priority      = DecisionPriority.low,
                title         = "Intelligence recommendation available",
                description   = str(rec),
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {"recommended_action": rec},
            ))

    except Exception:
        pass

    return items
