from __future__ import annotations

import hashlib
from typing import Any

from app.execution_orchestrator.models import ExecutionOrchestratorSnapshot
from app.runtime_state_manager.entity_binding import UnifiedEntity, list_entities
from app.schemas.response import AnalyzeResponse, PhaseExecutionDirective, SuggestedAction


def attach_phase_execution_directive(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
) -> AnalyzeResponse:
    if result.outcome_kind != "act" or not result.suggested_actions:
        return result
    if snapshot.active_phase.name != "OPEN":
        return result
    action = result.suggested_actions[0]
    if action.action_type != "open_new_tab":
        return result

    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    opened = _opened_urls(snapshot)
    remaining_slots = max(0, target - len(opened) - 1)
    if remaining_slots <= 0:
        return result

    planner_identity = _canonical_identity(action.value)
    seen_identities: set[str] = set(opened)
    if planner_identity:
        seen_identities.add(planner_identity)
    continuation: list[SuggestedAction] = []
    for entity in _openable_entities(snapshot.session_id):
        identity = _entity_identity(entity)
        url = _normalize_url(entity.canonical_url)
        if not url or not identity or identity in seen_identities:
            continue
        seen_identities.add(identity)
        continuation.append(_open_action(entity, len(continuation) + 1))
        if len(continuation) >= remaining_slots:
            break

    if not continuation:
        return result
    result.execution_orchestrator = PhaseExecutionDirective(
        active_phase=snapshot.active_phase.name,
        should_replan=False,
        reason=(
            "Execution Orchestrator owns remaining deterministic OPEN phase work "
            "from the mission entity graph."
        ),
        continuation_actions=continuation,
    )
    return result


def _openable_entities(session_id: str) -> list[UnifiedEntity]:
    entities = [
        entity
        for entity in list_entities(session_id)
        if entity.canonical_url
        and entity.state != "INVALID"
        and entity.entity_type in {"search_result", "semantic_element", "link", "card", "list_item", "table_row"}
    ]
    sorted_entities = sorted(
        entities,
        key=lambda entity: (
            _rank(entity),
            0 if entity.entity_type == "search_result" else 1,
            -float(entity.confidence or 0.0),
            entity.title,
            entity.entity_id,
        ),
    )
    return _dedupe_entities(sorted_entities)


def _open_action(entity: UnifiedEntity, index: int) -> SuggestedAction:
    url = entity.canonical_url or ""
    rank = entity.metadata.get("rank")
    title = entity.title or url
    suffix = f" #{rank}" if rank else f" {index + 1}"
    return SuggestedAction(
        action_id=f"orchestrator_open_{_hash(entity.entity_id)}",
        action_type="open_new_tab",
        target_selector="",
        value=url,
        description=f"Open phase entity{suffix}: {title}",
        reasoning=(
            "Execution Orchestrator continuing the active OPEN phase from the "
            f"mission entity graph entity_id={entity.entity_id}."
        ),
        confidence=max(0.0, min(1.0, float(entity.confidence or 0.8))),
        safety_level="safe",
    )


def _opened_urls(snapshot: ExecutionOrchestratorSnapshot) -> set[str]:
    return {
        identity
        for url in snapshot.artifacts.opened_pages
        for identity in [_canonical_identity(url)]
        if identity
    }


def _rank(entity: UnifiedEntity) -> int:
    try:
        return int(entity.metadata.get("rank") or 1_000_000)
    except (TypeError, ValueError):
        return 1_000_000


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip()
    return text.rstrip("/")


def _canonical_identity(value: Any) -> str:
    text = _normalize_url(value)
    if not text:
        return ""
    try:
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

        parsed = urlparse(text)
        if not parsed.scheme or not parsed.netloc:
            return text.lower()
        path = parsed.path.rstrip("/") or "/"
        query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", query, "")).rstrip("/")
    except Exception:
        return text.lower()


def _entity_identity(entity: UnifiedEntity) -> str:
    return _canonical_identity(entity.canonical_url) or entity.entity_id


def _dedupe_entities(entities: list[UnifiedEntity]) -> list[UnifiedEntity]:
    seen: set[str] = set()
    out: list[UnifiedEntity] = []
    for entity in entities:
        identity = _entity_identity(entity)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        out.append(entity)
    return out


def _hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
