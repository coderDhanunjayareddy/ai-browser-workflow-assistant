"""
V5.5 Mission Intelligence — MissionInformationGapAnalyzer.

Determines what information is still missing before a mission can execute.

Strategy:
  1. Detect action intent from mission objective (reuses intelligence.opportunity_detector)
  2. Look up required entities for that action type
  3. Compare required entities against mission memory entities
  4. Return gaps as MissionInformationGap list

Rule-based only. No AI. No LLM. No DB. <2ms p95.
"""
from __future__ import annotations

from app.mission.context_registry import MissionContext
from app.mission.intelligence.models import MissionInformationGap, GapCategory

# ── Category mapping for known entity field names ─────────────────────────────
_FIELD_CATEGORY: dict[str, GapCategory] = {
    "origin":          GapCategory.geographic,
    "destination":     GapCategory.geographic,
    "location":        GapCategory.geographic,
    "departure_date":  GapCategory.temporal,
    "return_date":     GapCategory.temporal,
    "check_in_date":   GapCategory.temporal,
    "check_out_date":  GapCategory.temporal,
    "date":            GapCategory.temporal,
    "time":            GapCategory.temporal,
    "budget":          GapCategory.financial,
    "price":           GapCategory.financial,
    "payment_method":  GapCategory.financial,
    "traveler_count":  GapCategory.demographic,
    "guest_count":     GapCategory.demographic,
    "passenger_count": GapCategory.demographic,
    "headcount":       GapCategory.demographic,
    "email":           GapCategory.identity,
    "name":            GapCategory.identity,
    "username":        GapCategory.identity,
    "product_name":    GapCategory.product,
    "model":           GapCategory.product,
    "software_name":   GapCategory.product,
    "item":            GapCategory.product,
    "recipient":       GapCategory.contact,
    "phone":           GapCategory.contact,
    "position":        GapCategory.credential,
    "password":        GapCategory.credential,
}

# Human-readable labels for entity keys
_FIELD_LABELS: dict[str, str] = {
    "origin":          "departure city or airport",
    "destination":     "destination city or airport",
    "location":        "location",
    "departure_date":  "departure date",
    "return_date":     "return date",
    "check_in_date":   "check-in date",
    "check_out_date":  "check-out date",
    "date":            "date",
    "time":            "specific time",
    "budget":          "budget",
    "price":           "price limit",
    "payment_method":  "payment method",
    "traveler_count":  "number of travelers",
    "guest_count":     "number of guests",
    "passenger_count": "number of passengers",
    "headcount":       "headcount",
    "email":           "email address",
    "name":            "full name",
    "username":        "username",
    "product_name":    "product name or model",
    "model":           "model or variant",
    "software_name":   "software or application name",
    "item":            "item or product",
    "recipient":       "message recipient",
    "phone":           "phone number",
    "position":        "job position or role",
    "password":        "password",
}


def _known_entity_keys(ctx: MissionContext) -> set[str]:
    """
    Extract all known entity keys from mission memory.
    Keys are lowercased and stripped.
    Also checks task goals for implicit entity presence.
    """
    known: set[str] = set()
    for key in ctx.entities.keys():
        known.add(key.lower().strip())
    # Also treat goal text as potential entity presence indicator
    # (rough heuristic: if "date" appears in any goal, treat "date" as known)
    combined_goals = " ".join(ctx.goals).lower()
    for field in _FIELD_LABELS:
        if field.replace("_", " ") in combined_goals:
            known.add(field)
    return known


def _gap(field_name: str) -> MissionInformationGap:
    return MissionInformationGap(
        field_name=field_name,
        description=_FIELD_LABELS.get(field_name, field_name.replace("_", " ")),
        category=_FIELD_CATEGORY.get(field_name, GapCategory.unknown),
    )


def analyze(ctx: MissionContext) -> list[MissionInformationGap]:
    """
    Return gaps between required entities (from action type) and known entities.
    Uses intelligence.opportunity_detector to classify mission objective.
    """
    # Detect action type from mission title
    from app.intelligence.opportunity_detector import detector
    opportunity = detector.detect(ctx.mission_title, cognitive_session=None)

    required_entities: list[str] = opportunity.required_entities
    known = _known_entity_keys(ctx)

    gaps: list[MissionInformationGap] = []
    seen: set[str] = set()

    for entity in required_entities:
        if entity not in known and entity not in seen:
            seen.add(entity)
            gaps.append(_gap(entity))

    # Additional heuristic gaps based on task count and research
    # If no tasks have research → flag "research_data" as a soft gap
    if not any(ts["has_research"] for ts in ctx.task_summaries):
        if "research_data" not in seen:
            gaps.append(MissionInformationGap(
                field_name="research_data",
                description="Research data (no task has completed research yet)",
                category=GapCategory.unknown,
            ))

    return gaps
