"""
WorkflowBridge: builds enriched handoff payloads when the ambient assistant
cannot handle a request and routes to the Workflow Engine.

Converts internal CognitiveSession state → WorkflowHandoffPayload (Pydantic)
which is embedded in AssistResponse.handoff_payload.

V3.0 will wire the Workflow Engine to consume this payload directly.
V2.6 makes the payload available; consumption is a future concern.
"""
from __future__ import annotations

from typing import Optional

from app.cognitive_core.models import CognitiveSession
from app.cognitive_core.entity_registry import get_ordered_entities
from app.schemas.assist import CognitiveEntitySchema, WorkflowHandoffPayload


def build_handoff_payload(
    query: str,
    session: CognitiveSession,
) -> WorkflowHandoffPayload:
    """
    Build an enriched handoff payload from the current cognitive session state.

    Args:
        query: the original user message that triggered the handoff
        session: the CognitiveSession for this conversation
    """
    entities = get_ordered_entities(session)
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
    if session.active_goal:
        goal_text = session.active_goal.goal_text
        goal_status = session.active_goal.status.value

    return WorkflowHandoffPayload(
        query=query,
        goal_text=goal_text,
        goal_status=goal_status,
        entities=entity_schemas,
        conversation_summary=session.conversation_summary,
        turn_count=session.turn_count,
    )
