"""
Internal domain models for the Cognitive Core.
Pure Python dataclasses — no Pydantic here.
Pydantic serialization lives at schemas/assist.py (the API boundary).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class EntityType(str, Enum):
    product = "product"
    flight = "flight"
    hotel = "hotel"
    article = "article"
    email = "email"
    person = "person"
    website = "website"
    generic = "generic"


class GoalStatus(str, Enum):
    active = "active"
    completed = "completed"
    blocked = "blocked"
    handed_off = "handed_off"


@dataclass
class Entity:
    id: str
    type: EntityType
    name: str
    aliases: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    confidence: float = 1.0
    source_turn: int = 0


@dataclass
class Goal:
    goal_id: str
    goal_text: str
    status: GoalStatus = GoalStatus.active
    subgoals: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ResolutionResult:
    entity_id: Optional[str]
    entity_name: Optional[str]
    confidence: float
    method: str  # "ordinal" | "proximal" | "name_match" | "none"
    reasoning: str


@dataclass
class EnrichedMessage:
    original: str
    enriched: str       # equals original when no enrichment applied
    resolved_entities: list[Entity] = field(default_factory=list)
    enrichment_applied: bool = False


@dataclass
class CognitiveSession:
    conversation_id: str
    turn_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    conversation_summary: str = ""
    # Entities keyed by entity.id; entity_order tracks insertion order for ordinal refs
    active_entities: dict[str, Entity] = field(default_factory=dict)
    entity_order: list[str] = field(default_factory=list)
    active_goal: Optional[Goal] = None
    active_intent: str = "unknown"
