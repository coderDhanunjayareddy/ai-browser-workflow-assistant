"""
V7.5 Decision Center — Research source adapter.

Wraps research opportunities from V3.5 research layer into DecisionItems.
Does NOT duplicate research logic.
"""
from __future__ import annotations

from app.decisions.models import (
    DecisionItem, DecisionType, DecisionPriority, make_decision,
)

_SOURCE = "research_layer"


def decisions_for_mission(mission_id: str) -> list[DecisionItem]:
    """
    Produce OPPORTUNITY DecisionItems from research layer gaps and opportunities.
    Returns [] if research layer unavailable or no gaps found.
    """
    items: list[DecisionItem] = []
    try:
        from app.mission import memory as mm
        mem = mm.get(mission_id)
        if mem is None:
            return []

        # Research findings gaps (missing or empty)
        findings = getattr(mem, "research_findings", None) or []
        if not findings:
            items.append(make_decision(
                decision_type = DecisionType.opportunity,
                priority      = DecisionPriority.low,
                title         = "No research findings recorded",
                description   = (
                    "Mission memory has no research findings. "
                    "Running research may improve mission context quality."
                ),
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {"finding_count": 0},
            ))

        # Entity gaps (no entities despite goals)
        goals    = getattr(mem, "goals",    None) or []
        entities = getattr(mem, "entities", None) or {}
        if goals and not entities:
            items.append(make_decision(
                decision_type = DecisionType.opportunity,
                priority      = DecisionPriority.low,
                title         = "Mission entities not identified",
                description   = (
                    f"Mission has {len(goals)} goal(s) but no identified entities. "
                    "Research may help identify key entities."
                ),
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {"goal_count": len(goals), "entity_count": 0},
            ))

    except Exception:
        pass

    return items
