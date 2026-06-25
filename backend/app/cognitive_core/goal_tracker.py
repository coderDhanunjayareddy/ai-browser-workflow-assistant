"""
GoalTracker: infers and maintains conversational goal state.

Goal inference (from first meaningful intent):
  summarize → "Understand this page"
  ask       → "Find: <question[:60]>"
  compare   → "Compare: <entity names>"
  research  → "Research: <message[:60]>"
  unknown   → "Complete: <message[:60]>"

Goal state transitions:
  active → completed   when: summarize/ask path returns successfully
  active → handed_off  when: a handoff is triggered
  active → blocked     when: consecutive errors (3+)

Goals are updated, not replaced, within a session. Once a goal exists it
evolves via update_goal() rather than creating a new one.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.cognitive_core.models import CognitiveSession, Entity, Goal, GoalStatus


def _now() -> datetime:
    return datetime.utcnow()


def infer_goal(
    intent: str,
    message: str,
    entities: list[Entity],
) -> Goal:
    """Infer an initial goal from the first substantive turn."""
    if intent == "summarize":
        goal_text = "Understand this page"
    elif intent == "ask":
        truncated = message[:60].rstrip()
        goal_text = f"Find: {truncated}"
    elif intent == "compare":
        if entities:
            names = " vs ".join(e.name for e in entities[:3])
            goal_text = f"Compare: {names}"
        else:
            goal_text = f"Compare: {message[:60].rstrip()}"
    elif intent == "research":
        goal_text = f"Research: {message[:60].rstrip()}"
    else:
        goal_text = f"Complete: {message[:60].rstrip()}"

    return Goal(
        goal_id=str(uuid.uuid4()),
        goal_text=goal_text,
        status=GoalStatus.active,
        subgoals=[],
        created_at=_now(),
        updated_at=_now(),
    )


def update_goal(
    goal: Goal,
    intent: str,
    response_type: str,
    handoff_triggered: bool = False,
    consecutive_errors: int = 0,
) -> Goal:
    """
    Transition goal state based on the result of the current turn.
    Returns the same goal object (mutated in-place) for simplicity.
    """
    goal.updated_at = _now()

    if handoff_triggered:
        goal.status = GoalStatus.handed_off
        return goal

    if consecutive_errors >= 3:
        goal.status = GoalStatus.blocked
        return goal

    if response_type in ("summary", "answer") and goal.status == GoalStatus.active:
        # Progress toward completion — remain active until explicitly resolved
        # Mark completed only if summarize returned a full summary
        if intent == "summarize" and response_type == "summary":
            goal.status = GoalStatus.completed

    return goal


def evolve_goal(
    session: CognitiveSession,
    intent: str,
    message: str,
    entities: list[Entity],
    response_type: str,
    handoff_triggered: bool = False,
) -> Goal:
    """
    High-level entry point: infer a new goal or update the existing one.
    Called once per turn after intent classification and response generation.
    """
    if session.active_goal is None:
        session.active_goal = infer_goal(intent, message, entities)

    errors = _count_recent_errors(session)
    update_goal(
        session.active_goal,
        intent=intent,
        response_type=response_type,
        handoff_triggered=handoff_triggered,
        consecutive_errors=errors,
    )

    # Refine goal text if compare entities are now known
    if intent == "compare" and entities and "Compare: " in session.active_goal.goal_text:
        if session.active_goal.goal_text == "Compare: " + message[:60].rstrip():
            names = " vs ".join(e.name for e in entities[:3])
            session.active_goal.goal_text = f"Compare: {names}"
            session.active_goal.updated_at = _now()

    return session.active_goal


def _count_recent_errors(session: CognitiveSession) -> int:
    # Placeholder: a real implementation would inspect the turn history.
    # For V2.6 we always return 0 — error-based blocking is a V3.0 concern.
    return 0
