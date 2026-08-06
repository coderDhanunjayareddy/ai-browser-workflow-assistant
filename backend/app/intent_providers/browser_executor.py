from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentExecutionEvidence
from app.intent_dispatcher.registry import IntentOwnerRegistration, dispatch_intent, register_intent_executor, register_intent_owner
from app.intent_providers.common import execution_result


BROWSER_INTENTS = (
    "click",
    "fill",
    "scroll",
    "navigate",
    "navigate_next_page",
    "wait",
    "select_option",
    "choose_date",
    "hover",
    "keyboard_shortcut",
    "open_new_tab",
    "switch_tab",
    "close_tab",
    "focus_existing_tab",
)


def register() -> None:
    for intent in BROWSER_INTENTS:
        register_intent_owner(
            IntentOwnerRegistration(
                provider_id="browser_control",
                capability=intent,
                dispatch_target="browser_control",
                reason=f"Browser Control owns browser intent {intent}.",
                matcher=lambda candidate, _payload, expected=intent: candidate == expected,
                browser_executable=True,
            )
        )
    register_intent_executor("browser_control", execute)


def execute(context: ExecutionContext, directive: IntentDispatchDirective):
    action = dict(directive.payload)
    action.setdefault("action_type", directive.intent)
    action["intent_id"] = directive.intent_id
    action["mission_id"] = context.mission_id
    next_intents = []
    for item in list(action.get("next_intents") or []):
        if not isinstance(item, dict):
            continue
        next_intent = item.get("intent") or item.get("action_type")
        if not next_intent:
            continue
        payload = dict(item.get("payload") or item)
        payload.setdefault("mission_id", context.mission_id)
        payload.setdefault("parent_intent_id", directive.intent_id)
        dispatched = dispatch_intent(intent=str(next_intent), payload=payload)
        if dispatched is not None:
            dispatched.mission_id = context.mission_id
            dispatched.parent_intent_id = directive.intent_id
            next_intents.append(dispatched)
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}:browser_action_required",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Browser Control must execute {directive.intent}.",
        payload={"browser_action": action, "intent_id": directive.intent_id},
    )
    return execution_result(
        directive,
        status="waiting_browser",
        reason=f"Browser action required: {directive.intent}.",
        evidence=[evidence],
        next_intents=next_intents,
        blocking_reason="browser_control_required",
    )
