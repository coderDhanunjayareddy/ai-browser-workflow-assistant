"""
ReferenceResolver: deterministic resolution of anaphoric references.

Resolution order:
  1. Ordinal  — "first", "second", "third" → index into entity_order
  2. Proximal — "it", "this", "that", "those", "them" → most recent entity
  3. Name match — partial name in message → entity whose name is contained

LLM fallback is NOT used in V2.6 (deterministic only).
Returns ResolutionResult with entity_id=None and method="none" when unresolvable.
"""
from __future__ import annotations

import re

from app.cognitive_core.models import CognitiveSession, Entity, ResolutionResult
from app.cognitive_core.entity_registry import get_ordered_entities

# ── Ordinal reference mapping ─────────────────────────────────────────────────

_ORDINAL_MAP: dict[str, int] = {
    "first": 0, "1st": 0, "first one": 0, "the first": 0,
    "second": 1, "2nd": 1, "second one": 1, "the second": 1,
    "third": 2, "3rd": 2, "third one": 2, "the third": 2,
    "last": -1, "the last": -1, "most recent": -1,
}

# ── Proximal reference terms ───────────────────────────────────────────────────

_PROXIMAL_TERMS = frozenset({
    "it", "its", "this", "that", "those", "these", "them", "they",
    "the one", "that one", "this one",
})

# ── Patterns for quick detection ──────────────────────────────────────────────

_ORDINAL_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_ORDINAL_MAP, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_PROXIMAL_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(_PROXIMAL_TERMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _result_from_entity(entity: Entity, method: str, reasoning: str) -> ResolutionResult:
    return ResolutionResult(
        entity_id=entity.id,
        entity_name=entity.name,
        confidence=0.9 if method == "ordinal" else 0.7,
        method=method,
        reasoning=reasoning,
    )


def _no_result(reasoning: str = "no entities in session") -> ResolutionResult:
    return ResolutionResult(
        entity_id=None,
        entity_name=None,
        confidence=0.0,
        method="none",
        reasoning=reasoning,
    )


def resolve(message: str, session: CognitiveSession) -> ResolutionResult:
    """
    Attempt to resolve a reference in `message` against entities in `session`.
    Returns ResolutionResult(method="none") if resolution fails.
    """
    entities = get_ordered_entities(session)
    if not entities:
        return _no_result("no entities in session")

    lowered = message.lower().strip()

    # 1. Ordinal resolution
    m = _ORDINAL_PATTERN.search(lowered)
    if m:
        key = m.group(1).lower()
        idx = _ORDINAL_MAP.get(key)
        if idx is not None:
            try:
                entity = entities[idx]
                return _result_from_entity(
                    entity, "ordinal",
                    f"'{key}' → entity at index {idx}: '{entity.name}'"
                )
            except IndexError:
                pass  # fall through to proximal

    # 2. Proximal resolution (most recent entity)
    if _PROXIMAL_PATTERN.search(lowered):
        entity = entities[-1]
        return _result_from_entity(
            entity, "proximal",
            f"proximal reference → most recent entity: '{entity.name}'"
        )

    # 3. Partial name match in the message
    for entity in reversed(entities):  # most recent first
        if entity.name.lower() in lowered:
            return ResolutionResult(
                entity_id=entity.id,
                entity_name=entity.name,
                confidence=0.95,
                method="name_match",
                reasoning=f"name '{entity.name}' found in message",
            )

    return _no_result("no reference term or name match found in message")


def has_reference(message: str) -> bool:
    """Quick check: does the message contain any resolvable reference term?"""
    lowered = message.lower()
    return bool(
        _ORDINAL_PATTERN.search(lowered) or _PROXIMAL_PATTERN.search(lowered)
    )


def resolve_all(message: str, session: CognitiveSession) -> list[ResolutionResult]:
    """
    Resolve ALL reference terms found in the message.
    Used when a message references multiple entities ("compare the first and second").
    """
    entities = get_ordered_entities(session)
    if not entities:
        return [_no_result()]

    results: list[ResolutionResult] = []
    lowered = message.lower()

    for m in _ORDINAL_PATTERN.finditer(lowered):
        key = m.group(1).lower()
        idx = _ORDINAL_MAP.get(key)
        if idx is not None:
            try:
                entity = entities[idx]
                results.append(_result_from_entity(
                    entity, "ordinal",
                    f"'{key}' → '{entity.name}'"
                ))
            except IndexError:
                pass

    seen_ids = {r.entity_id for r in results}
    if not results and _PROXIMAL_PATTERN.search(lowered):
        entity = entities[-1]
        if entity.id not in seen_ids:
            results.append(_result_from_entity(entity, "proximal", "proximal reference"))
            seen_ids.add(entity.id)

    return results or [_no_result("no references resolved")]
