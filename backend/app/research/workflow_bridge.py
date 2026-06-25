"""
ResearchWorkflowBridge: detects action intent in research queries and escalates to Workflow.

When a research query contains action keywords (book, buy, reserve, etc.), a
WorkflowHandoffPayload is emitted so the Workflow Engine can take over.

This is the only point where V3.5 and the Workflow Engine touch each other.
"""
from __future__ import annotations

from typing import Optional

from app.research.models import ResearchSession
from app.cognitive_core.models import CognitiveSession
from app.schemas.assist import CognitiveEntitySchema, WorkflowHandoffPayload

_ACTION_KEYWORDS = frozenset({
    "book", "buy", "purchase", "reserve", "order", "sign up",
    "register", "subscribe", "schedule", "apply", "enroll",
    "hire", "rent", "lease", "download", "install",
})


def _has_action_intent(query: str) -> bool:
    lowered = query.lower()
    return any(kw in lowered for kw in _ACTION_KEYWORDS)


def build_research_handoff(
    query: str,
    research_session: ResearchSession,
    cognitive_session: CognitiveSession,
) -> Optional[WorkflowHandoffPayload]:
    """
    Return a WorkflowHandoffPayload if the research query has workflow-escalation intent.
    Returns None if this is a pure research query with no action keywords.
    """
    if not _has_action_intent(query):
        return None

    from app.cognitive_core.entity_registry import get_ordered_entities
    entities = get_ordered_entities(cognitive_session)
    entity_schemas = [
        CognitiveEntitySchema(
            id=e.id,
            type=e.type.value,
            name=e.name,
            aliases=e.aliases,
            metadata=e.metadata,
            confidence=e.confidence,
            source_turn=e.source_turn,
        )
        for e in entities
    ]

    goal_text: Optional[str] = None
    goal_status: Optional[str] = None
    if cognitive_session.active_goal:
        goal_text = cognitive_session.active_goal.goal_text
        goal_status = cognitive_session.active_goal.status.value

    # Enrich the conversation summary with research context
    topic_context = f"Research topic: {research_session.topic}"
    summary = cognitive_session.conversation_summary
    if summary:
        summary = f"{summary}\n\n{topic_context}"
    else:
        summary = topic_context

    return WorkflowHandoffPayload(
        query=query,
        goal_text=goal_text,
        goal_status=goal_status,
        entities=entity_schemas,
        conversation_summary=summary,
        turn_count=cognitive_session.turn_count,
    )
