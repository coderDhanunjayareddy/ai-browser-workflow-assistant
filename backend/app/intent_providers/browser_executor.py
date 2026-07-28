from __future__ import annotations

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentExecutionEvidence
from app.intent_dispatcher.registry import IntentOwnerRegistration, register_intent_executor, register_intent_owner
from app.intent_providers.common import execution_result


BROWSER_INTENTS = (
    "click",
    "fill",
    "scroll",
    "navigate",
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
    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}:browser_action_required",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Browser Control must execute {directive.intent}.",
        payload={"browser_action": action},
    )
    return execution_result(
        directive,
        status="browser_action_required",
        reason=f"Browser action required: {directive.intent}.",
        evidence=[evidence],
        blocking_reason="browser_control_required",
    )
