"""
WorkflowContext: converts WorkflowHandoffPayload into structures the
WorkflowOrchestrator and ContextCompressor can consume.

Two outputs:
  1. cognitive_context dict  — injected as a 6th key into the planner context
  2. bootstrap_facts dict    — pre-populates WorkflowState.facts on cold start
"""
from __future__ import annotations

from typing import Optional

from app.schemas.assist import WorkflowHandoffPayload


def build_cognitive_context(payload: WorkflowHandoffPayload) -> dict:
    """
    Build the cognitive_context sub-dict for the planner prompt.
    Added as 6th key to compressed context when handoff_payload is present.
    """
    ctx: dict = {
        "conversation_turns": payload.turn_count,
        "conversation_summary": payload.conversation_summary,
    }
    if payload.goal_text:
        ctx["user_goal"] = payload.goal_text
        ctx["goal_status"] = payload.goal_status or "unknown"
    if payload.entities:
        ctx["tracked_entities"] = [
            {
                "name": e.name,
                "type": e.type,
                "confidence": round(e.confidence, 2),
            }
            for e in payload.entities
        ]
    return ctx


def build_bootstrap_facts(payload: WorkflowHandoffPayload) -> dict:
    """
    Build initial WorkflowState.facts from a handoff payload.
    Called once when the workflow session starts cold (no existing facts).

    The planner uses these facts as "what we already know" — it can skip
    re-confirming information the Cognitive Core already established.
    """
    facts: dict = {}

    if payload.goal_text:
        facts["user_goal"] = payload.goal_text
    if payload.goal_status:
        facts["goal_status"] = payload.goal_status
    if payload.conversation_summary:
        facts["conversation_context"] = payload.conversation_summary
    if payload.turn_count:
        facts["prior_conversation_turns"] = payload.turn_count
    for i, entity in enumerate(payload.entities):
        facts[f"entity_{i}_name"] = entity.name
        facts[f"entity_{i}_type"] = entity.type

    return facts


def summarize_for_planner(payload: Optional[WorkflowHandoffPayload]) -> str:
    """
    Return a brief natural-language summary of the handoff for use in
    supplemental context or log messages.
    """
    if payload is None:
        return ""
    parts = []
    if payload.goal_text:
        parts.append(f"Goal: {payload.goal_text}")
    if payload.entities:
        names = ", ".join(e.name for e in payload.entities[:3])
        parts.append(f"Entities: {names}")
    if payload.conversation_summary:
        parts.append(f"Context: {payload.conversation_summary}")
    return " | ".join(parts) if parts else ""
