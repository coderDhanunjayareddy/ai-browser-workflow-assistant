"""
IntentContinuityLayer: enriches user messages with entity context before
they reach the QA service or handoff builder.

Activation conditions (ALL must hold):
  - message is short (≤ 12 words)
  - session has at least one entity
  - message contains a reference term OR a comparative keyword

Enrichment strategy:
  Prepend "Considering [EntityA, EntityB, ...]: " to the message so that
  the QA service has full entity context without a new intent classification.

This layer does NOT change the classified intent — it only makes answers
richer when reference resolution succeeds.
"""
from __future__ import annotations

import re

from app.cognitive_core.models import CognitiveSession, EnrichedMessage
from app.cognitive_core.entity_registry import get_ordered_entities
from app.cognitive_core import reference_resolver

_MAX_ENRICH_WORDS = 12
_MAX_ENTITY_NAMES = 3

# Comparative keywords that signal the user is contrasting entities
_COMPARATIVE_KEYWORDS = frozenset({
    "cheaper", "cheapest", "expensive", "better", "worse", "faster", "slower",
    "larger", "smaller", "lighter", "heavier", "newer", "older", "cheaper one",
    "more expensive", "less expensive", "which one", "compared to",
})

_COMPARATIVE_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in sorted(_COMPARATIVE_KEYWORDS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _has_comparative(message: str) -> bool:
    return bool(_COMPARATIVE_PATTERN.search(message))


def enrich(message: str, session: CognitiveSession) -> EnrichedMessage:
    """
    Attempt to enrich `message` with entity context.
    Returns EnrichedMessage where .enriched == .original if no enrichment applied.
    """
    base = EnrichedMessage(original=message, enriched=message)

    entities = get_ordered_entities(session)
    if not entities:
        return base

    word_count = len(message.split())
    if word_count > _MAX_ENRICH_WORDS:
        return base

    has_ref = reference_resolver.has_reference(message)
    has_comp = _has_comparative(message)

    if not has_ref and not has_comp:
        return base

    # Build context prefix from tracked entities
    top_entities = entities[-_MAX_ENTITY_NAMES:]  # most recent N
    names = ", ".join(e.name for e in top_entities)
    enriched_text = f"Considering {names}: {message}"

    # Collect resolved entities for callers
    resolved = reference_resolver.resolve_all(message, session)
    resolved_entities = [
        session.active_entities[r.entity_id]
        for r in resolved
        if r.entity_id and r.entity_id in session.active_entities
    ]

    return EnrichedMessage(
        original=message,
        enriched=enriched_text,
        resolved_entities=resolved_entities,
        enrichment_applied=True,
    )
