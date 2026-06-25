"""
EntityRegistry: extracts and tracks named entities within a CognitiveSession.

Two extraction paths (both zero-LLM):
  1. From StructuredSummary.entities  — LLM-structured, high confidence (0.9)
  2. From user message text            — pattern-based, lower confidence (0.6)

Bounded to MAX_ENTITIES entities per session; oldest evicted first.
Duplicate detection: same name → update confidence/metadata, no new entity created.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from app.cognitive_core.models import CognitiveSession, Entity, EntityType

MAX_ENTITIES = 20
_SUMMARY_CONFIDENCE = 0.9
_MESSAGE_CONFIDENCE = 0.6

# label → EntityType mappings (checked in order; first match wins)
_LABEL_TYPE_MAP: list[tuple[str, EntityType]] = [
    ("product", EntityType.product),
    ("brand", EntityType.product),
    ("device", EntityType.product),
    ("laptop", EntityType.product),
    ("phone", EntityType.product),
    ("item", EntityType.product),
    ("flight", EntityType.flight),
    ("airline", EntityType.flight),
    ("route", EntityType.flight),
    ("hotel", EntityType.hotel),
    ("accommodation", EntityType.hotel),
    ("property", EntityType.hotel),
    ("person", EntityType.person),
    ("author", EntityType.person),
    ("website", EntityType.website),
    ("url", EntityType.website),
    ("article", EntityType.article),
    ("post", EntityType.article),
    ("email", EntityType.email),
]

# Case-insensitive brand keywords that signal a product entity
_PRODUCT_BRANDS = frozenset({
    "macbook", "iphone", "ipad", "airpods", "apple watch",
    "dell", "xps", "samsung", "galaxy", "google pixel", "pixel",
    "microsoft", "surface", "lenovo", "thinkpad", "asus", "acer",
    "hp", "huawei", "oneplus", "xiaomi", "sony", "lg",
})

# "compare X and Y" or "X vs Y" extraction
_COMPARE_AND = re.compile(
    r"(?:compare|comparing|between)\s+(.+?)\s+(?:and|&)\s+(.+?)(?:\s*[,;?!]|$)",
    re.IGNORECASE,
)
_VS_PATTERN = re.compile(
    r"(.+?)\s+(?:vs\.?|versus)\s+(.+?)(?:\s*[,;?!]|$)",
    re.IGNORECASE,
)


def _classify_label(label: str) -> EntityType:
    lowered = label.lower()
    for keyword, etype in _LABEL_TYPE_MAP:
        if keyword in lowered:
            return etype
    return EntityType.generic


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


def _find_existing_id(session: CognitiveSession, name: str) -> Optional[str]:
    """Return entity_id if an entity with this name (or alias) already exists."""
    lowered = name.lower()
    for eid, entity in session.active_entities.items():
        if entity.name.lower() == lowered:
            return eid
        if any(a.lower() == lowered for a in entity.aliases):
            return eid
    return None


def _upsert_entity(session: CognitiveSession, entity: Entity) -> None:
    """Add entity to session; merge if duplicate, evict oldest if at capacity."""
    existing_id = _find_existing_id(session, entity.name)
    if existing_id:
        existing = session.active_entities[existing_id]
        if entity.confidence > existing.confidence:
            existing.confidence = entity.confidence
        for alias in entity.aliases:
            if alias not in existing.aliases:
                existing.aliases.append(alias)
        existing.metadata.update(entity.metadata)
        return

    while len(session.active_entities) >= MAX_ENTITIES:
        oldest_id = session.entity_order.pop(0)
        session.active_entities.pop(oldest_id, None)

    session.active_entities[entity.id] = entity
    session.entity_order.append(entity.id)


def extract_from_summary_entities(
    session: CognitiveSession,
    summary_entities: list[dict],
    turn: int,
) -> list[Entity]:
    """
    Extract entities from StructuredSummary.entities
    (list of {"label": ..., "value": ...} dicts produced by the LLM).
    """
    extracted: list[Entity] = []
    for item in summary_entities:
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", "")).strip()
        if not value or len(value) < 2:
            continue
        name = _normalize_name(value)
        etype = _classify_label(label)
        entity = Entity(
            id=str(uuid.uuid4()),
            type=etype,
            name=name,
            aliases=[],
            metadata={"label": label},
            confidence=_SUMMARY_CONFIDENCE,
            source_turn=turn,
        )
        _upsert_entity(session, entity)
        extracted.append(entity)
    return extracted


def _make_product_entity(name: str, turn: int) -> Entity:
    clean = _normalize_name(name)
    lower = clean.lower()
    etype = EntityType.product
    for brand in _PRODUCT_BRANDS:
        if brand in lower:
            etype = EntityType.product
            break
    return Entity(
        id=str(uuid.uuid4()),
        type=etype,
        name=clean,
        confidence=_MESSAGE_CONFIDENCE,
        source_turn=turn,
    )


def extract_from_message(
    session: CognitiveSession,
    message: str,
    turn: int,
) -> list[Entity]:
    """
    Extract named entities from a user message using pattern matching.

    Only targets explicit comparison patterns to avoid noisy extraction:
      - "compare X and Y"     → two entities
      - "X vs Y"              → two entities
      - known brand keywords  → one product entity
    """
    extracted: list[Entity] = []
    text = message.strip()

    # Compare/And pattern
    m = _COMPARE_AND.search(text)
    if m:
        for group in (m.group(1), m.group(2)):
            name = _normalize_name(group)
            if name and len(name) >= 2:
                e = _make_product_entity(name, turn)
                _upsert_entity(session, e)
                extracted.append(e)
        if extracted:
            return extracted

    # Vs pattern
    m = _VS_PATTERN.search(text)
    if m:
        for group in (m.group(1), m.group(2)):
            name = _normalize_name(group)
            if name and len(name) >= 2:
                e = _make_product_entity(name, turn)
                _upsert_entity(session, e)
                extracted.append(e)
        if extracted:
            return extracted

    # Known brand single-word detection (case-insensitive)
    lower_text = text.lower()
    for brand in sorted(_PRODUCT_BRANDS, key=len, reverse=True):  # longest match first
        if brand in lower_text:
            # Find original casing in the text
            idx = lower_text.find(brand)
            original = text[idx: idx + len(brand)]
            e = _make_product_entity(original, turn)
            _upsert_entity(session, e)
            extracted.append(e)
            break  # one brand per message for single-word detection

    return extracted


def get_ordered_entities(session: CognitiveSession) -> list[Entity]:
    """Return entities in insertion order (oldest first)."""
    return [
        session.active_entities[eid]
        for eid in session.entity_order
        if eid in session.active_entities
    ]
