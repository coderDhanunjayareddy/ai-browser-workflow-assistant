"""
CognitiveAnalytics: in-memory metrics for the Cognitive Core.

Tracks per-session-request outcomes:
  - entity extraction hits (entities found vs. zero)
  - reference resolution outcomes (success / none)
  - handoff enrichment (entities included in payload)
  - goal state distribution

All counters reset when the process restarts (in-memory only, V2.6).
Expose via get_cognitive_analytics() — consumed by the analytics API route.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CognitiveMetrics:
    total_turns: int = 0
    turns_with_entities: int = 0
    turns_with_reference: int = 0
    reference_resolved: int = 0
    handoffs_triggered: int = 0
    handoffs_with_entities: int = 0
    handoffs_with_goal: int = 0


_metrics = CognitiveMetrics()


def record_turn(
    *,
    had_entities: bool,
    had_reference: bool,
    reference_resolved: bool,
) -> None:
    _metrics.total_turns += 1
    if had_entities:
        _metrics.turns_with_entities += 1
    if had_reference:
        _metrics.turns_with_reference += 1
        if reference_resolved:
            _metrics.reference_resolved += 1


def record_handoff(
    *,
    entity_count: int,
    has_goal: bool,
) -> None:
    _metrics.handoffs_triggered += 1
    if entity_count > 0:
        _metrics.handoffs_with_entities += 1
    if has_goal:
        _metrics.handoffs_with_goal += 1


def get_cognitive_analytics() -> dict:
    m = _metrics
    resolution_rate = (
        m.reference_resolved / m.turns_with_reference
        if m.turns_with_reference > 0
        else None
    )
    handoff_enrichment_rate = (
        m.handoffs_with_entities / m.handoffs_triggered
        if m.handoffs_triggered > 0
        else None
    )
    return {
        "total_turns": m.total_turns,
        "turns_with_entities": m.turns_with_entities,
        "turns_with_reference": m.turns_with_reference,
        "reference_resolved": m.reference_resolved,
        "resolution_rate": resolution_rate,
        "handoffs_triggered": m.handoffs_triggered,
        "handoffs_with_entities": m.handoffs_with_entities,
        "handoffs_with_goal": m.handoffs_with_goal,
        "handoff_enrichment_rate": handoff_enrichment_rate,
    }


def _reset_for_testing() -> None:
    global _metrics
    _metrics = CognitiveMetrics()
