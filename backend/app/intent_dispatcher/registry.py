from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.intent_dispatcher.models import IntentDispatchDirective, IntentOwnership


Matcher = Callable[[str, dict[str, Any]], bool]


@dataclass(frozen=True)
class IntentOwnerRegistration:
    owner: str
    capability: str
    dispatch_target: str
    reason: str
    matcher: Matcher
    browser_executable: bool = False


_REGISTRY: list[IntentOwnerRegistration] = []


def register_intent_owner(registration: IntentOwnerRegistration) -> None:
    _REGISTRY.append(registration)


def resolve_intent_owner(intent: str, payload: dict[str, Any] | None = None) -> IntentOwnership:
    normalized = _normalize_intent(intent)
    payload = payload or {}
    for registration in _REGISTRY:
        if registration.matcher(normalized, payload):
            return IntentOwnership(
                owner=registration.owner,  # type: ignore[arg-type]
                capability=registration.capability,
                reason=registration.reason,
                browser_executable=registration.browser_executable,
            )
    return IntentOwnership(
        owner="unknown",
        capability=normalized,
        reason=f"No runtime owner registered for planner intent '{intent}'.",
        browser_executable=False,
    )


def dispatch_intent(
    *,
    intent: str,
    payload: dict[str, Any] | None = None,
) -> IntentDispatchDirective | None:
    ownership = resolve_intent_owner(intent, payload)
    if ownership.owner == "unknown":
        return None
    target = next(
        (
            registration.dispatch_target
            for registration in _REGISTRY
            if registration.owner == ownership.owner
            and registration.capability == ownership.capability
        ),
        ownership.owner,
    )
    return IntentDispatchDirective(
        intent=_normalize_intent(intent),
        owner=ownership.owner,
        capability=ownership.capability,
        dispatch_target=target,
        browser_executable=ownership.browser_executable,
        reason=ownership.reason,
        payload=dict(payload or {}),
        handled=False,
    )


def intent_dispatch_context() -> dict[str, Any]:
    return {
        "schema_version": "intent_dispatch.v1",
        "contract": (
            "Planner output expresses intent. Browser suggested_actions are "
            "browser-control only; backend semantic work is owned and routed by "
            "the runtime before it can reach Browser Control."
        ),
        "registered_owners": [
            {
                "owner": registration.owner,
                "capability": registration.capability,
                "dispatch_target": registration.dispatch_target,
                "browser_executable": registration.browser_executable,
            }
            for registration in _REGISTRY
        ],
    }


def _normalize_intent(intent: str) -> str:
    return str(intent or "").strip().lower().replace("-", "_")


def _intent_in(*names: str) -> Matcher:
    normalized = {_normalize_intent(name) for name in names}
    return lambda intent, _payload: intent in normalized


register_intent_owner(
    IntentOwnerRegistration(
        owner="knowledge_extraction",
        capability="page_reading",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Reading page content is backend knowledge work, not browser control.",
        matcher=_intent_in("read_page", "read"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="knowledge_extraction",
        capability="field_extraction",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Field extraction is backend semantic work over observed page content.",
        matcher=_intent_in("extract_fields", "extract", "structured_extraction"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="knowledge_extraction",
        capability="knowledge_synthesis",
        dispatch_target="knowledge_extraction_pipeline",
        reason="Knowledge synthesis is backend artifact computation.",
        matcher=_intent_in("synthesize_knowledge", "synthesize_report", "synthesize"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="mission_completion",
        capability="completion_evaluation",
        dispatch_target="mission_completion_controller",
        reason="Mission completion is evaluated from success criteria and evidence.",
        matcher=_intent_in("evaluate_completion", "mark_complete", "complete"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="execution_orchestrator",
        capability="phase_continuation",
        dispatch_target="execution_orchestrator",
        reason="Deterministic phase continuation is owned by the Execution Orchestrator.",
        matcher=_intent_in("continue_phase", "next_phase_item"),
    )
)
register_intent_owner(
    IntentOwnerRegistration(
        owner="runtime_state_manager",
        capability="runtime_state_update",
        dispatch_target="runtime_state_manager",
        reason="Runtime bindings and progress updates are owned by Runtime State Manager.",
        matcher=_intent_in("update_runtime_state", "bind_resource", "record_progress"),
    )
)
