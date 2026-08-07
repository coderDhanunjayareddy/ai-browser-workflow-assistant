from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable

from app.browser_url_policy import is_openable_browser_url
from app.execution_orchestrator.models import ExecutionOrchestratorSnapshot, PhaseName
from app.intent_dispatcher import dispatch_intent
from app.intent_dispatcher.models import IntentDispatchDirective
from app.runtime_state_manager.entity_binding import UnifiedEntity, list_entities
from app.schemas.response import AnalyzeResponse, IntentQueueDirective, SuggestedAction


@dataclass(frozen=True)
class PhaseWorkItem:
    phase: str
    identity: str
    action: IntentDispatchDirective
    evidence_kind: str


PhaseAdapter = Callable[[ExecutionOrchestratorSnapshot, SuggestedAction], list[PhaseWorkItem]]


def attach_phase_execution_directive(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
) -> AnalyzeResponse:
    if result.outcome_kind != "act" or not result.suggested_actions:
        return result

    action = result.suggested_actions[0]
    continuation = _continuation_actions(snapshot, action)
    if not continuation:
        return result

    result.execution_orchestrator = IntentQueueDirective(
        active_phase=snapshot.active_phase.name,
        should_replan=False,
        reason=(
            "Execution Orchestrator owns remaining deterministic "
            f"{snapshot.active_phase.name} phase work through the generalized phase execution queue."
        ),
        continuation_actions=continuation,
    )
    return result


def _continuation_actions(
    snapshot: ExecutionOrchestratorSnapshot,
    planner_action: SuggestedAction,
) -> list[IntentDispatchDirective]:
    adapter = _ADAPTERS.get(snapshot.active_phase.name)
    if adapter is None:
        return []
    items = adapter(snapshot, planner_action)
    return [item.action for item in items]


def _open_phase_items(
    snapshot: ExecutionOrchestratorSnapshot,
    planner_action: SuggestedAction,
) -> list[PhaseWorkItem]:
    if planner_action.action_type != "open_new_tab":
        return []

    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    opened = _opened_urls(snapshot)
    remaining_slots = max(0, target - len(opened) - 1)
    if remaining_slots <= 0:
        return []

    planner_identity = _canonical_identity(planner_action.value)
    seen_identities: set[str] = set(opened)
    if planner_identity:
        seen_identities.add(planner_identity)

    items: list[PhaseWorkItem] = []
    for entity in _openable_entities(snapshot.session_id):
        identity = _entity_identity(entity)
        url = _normalize_url(entity.canonical_url)
        if not url or not identity or identity in seen_identities:
            continue
        seen_identities.add(identity)
        items.append(
            PhaseWorkItem(
                phase="OPEN",
                identity=identity,
                evidence_kind="entity_opened",
                action=_open_action(entity, len(items) + 1),
            )
        )
        if len(items) >= remaining_slots:
            break
    return items


def _resource_read_phase_items(
    snapshot: ExecutionOrchestratorSnapshot,
    planner_action: SuggestedAction,
) -> list[PhaseWorkItem]:
    if planner_action.action_type not in {"focus_existing_tab", "switch_tab"}:
        return []

    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    opened = _opened_resource_urls(snapshot)
    if not opened:
        return []

    planner_identity = _canonical_identity(planner_action.value)
    seen = {identity for identity in [_canonical_identity(url) for url in _read_resource_urls(snapshot)] if identity}
    if planner_identity:
        seen.add(planner_identity)

    remaining = max(0, min(target, len(opened)) - len(seen))
    if remaining <= 0:
        return []

    items: list[PhaseWorkItem] = []
    for url in opened:
        identity = _canonical_identity(url)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        items.append(
            PhaseWorkItem(
                phase=snapshot.active_phase.name,
                identity=identity,
                evidence_kind=_phase_evidence_kind(snapshot.active_phase.name),
                action=_focus_action(snapshot.active_phase.name, url, len(items) + 1),
            )
        )
        if len(items) >= remaining:
            break
    return items


def _backend_phase_items(
    snapshot: ExecutionOrchestratorSnapshot,
    planner_action: SuggestedAction,
) -> list[PhaseWorkItem]:
    return []


_ADAPTERS: dict[PhaseName, PhaseAdapter] = {
    "OPEN": _open_phase_items,
    "READ": _resource_read_phase_items,
    "EXTRACT": _resource_read_phase_items,
    "VALIDATE": _resource_read_phase_items,
    "SYNTHESIZE": _backend_phase_items,
    "REPORT": _backend_phase_items,
}


def _openable_entities(session_id: str) -> list[UnifiedEntity]:
    entities = [
        entity
        for entity in list_entities(session_id)
        if entity.canonical_url
        and is_openable_browser_url(entity.canonical_url)
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


def _open_action(entity: UnifiedEntity, index: int) -> IntentDispatchDirective:
    url = entity.canonical_url or ""
    rank = entity.metadata.get("rank")
    title = entity.title or url
    suffix = f" #{rank}" if rank else f" {index + 1}"
    return _browser_intent(
        "open_new_tab",
        {
            "action_id": f"orchestrator_open_{_hash(entity.entity_id)}",
            "target_selector": "",
            "value": url,
            "description": f"Open phase entity{suffix}: {title}",
            "reasoning": (
                "Execution Orchestrator continuing the active OPEN phase from the "
                f"mission entity graph entity_id={entity.entity_id}."
            ),
            "confidence": max(0.0, min(1.0, float(entity.confidence or 0.8))),
            "safety_level": "safe",
        },
    )


def _focus_action(phase: str, url: str, index: int) -> IntentDispatchDirective:
    identity = _canonical_identity(url) or url
    return _browser_intent(
        "focus_existing_tab",
        {
            "action_id": f"orchestrator_{phase.lower()}_{_hash(identity)}",
            "target_selector": "",
            "value": f"url:{url}",
            "description": f"{phase.title()} phase resource #{index}: {url}",
            "reasoning": (
                "Execution Orchestrator continuing deterministic "
                f"{phase} phase work from opened runtime resources."
            ),
            "confidence": 0.86,
            "safety_level": "safe",
        },
    )


def _browser_intent(intent: str, payload: dict[str, Any]) -> IntentDispatchDirective:
    payload = {"action_type": intent, **payload}
    directive = dispatch_intent(intent=intent, payload=payload)
    if directive is None:
        raise ValueError(f"No provider registered for phase intent {intent}")
    return directive


def _opened_urls(snapshot: ExecutionOrchestratorSnapshot) -> set[str]:
    return {
        identity
        for url in snapshot.artifacts.opened_pages
        for identity in [_canonical_identity(url)]
        if identity
    }


def _opened_resource_urls(snapshot: ExecutionOrchestratorSnapshot) -> list[str]:
    return _dedupe_urls(snapshot.artifacts.opened_pages)


def _read_resource_urls(snapshot: ExecutionOrchestratorSnapshot) -> list[str]:
    opened = {_canonical_identity(url) for url in snapshot.artifacts.opened_pages}
    return _dedupe_urls([
        url
        for url in snapshot.artifacts.visited_urls
        if _canonical_identity(url) in opened
    ])


def _phase_evidence_kind(phase: str) -> str:
    return {
        "READ": "page_read",
        "EXTRACT": "field_extracted",
        "VALIDATE": "artifact_validated",
    }.get(phase, "phase_progress")


def _rank(entity: UnifiedEntity) -> int:
    try:
        return int(entity.metadata.get("rank") or 1_000_000)
    except (TypeError, ValueError):
        return 1_000_000


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("url:"):
        text = text[4:]
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


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        identity = _canonical_identity(url)
        clean = _normalize_url(url)
        if not identity or not clean or identity in seen:
            continue
        seen.add(identity)
        out.append(clean)
    return out


def _hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
