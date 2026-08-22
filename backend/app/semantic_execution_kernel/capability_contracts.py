from __future__ import annotations

from dataclasses import dataclass

from app.contracts.generic_capability import (
    ExpectedEffect,
    GenericCapabilityRequest,
    TargetIdentity,
)


@dataclass(frozen=True)
class CapabilityTemplate:
    capability_id: str
    family: str
    effect_type: str
    postcondition: str
    evidence: tuple[str, ...]
    retry_budget: int = 0


_ACTION_TEMPLATES: dict[str, CapabilityTemplate] = {
    "navigate": CapabilityTemplate(
        "navigation.navigate", "navigation_context", "destination_loaded",
        "The resolved destination origin and page state are observable.",
        ("observed_origin", "page_state"), 1,
    ),
    "open_new_tab": CapabilityTemplate(
        "navigation.open_context", "navigation_context", "context_opened",
        "A new browser context is open at the resolved destination.",
        ("tab_identity", "observed_origin"), 1,
    ),
    "switch_tab": CapabilityTemplate(
        "navigation.focus_context", "navigation_context", "context_focused",
        "The requested existing browser context is focused.",
        ("tab_identity", "active_context"), 1,
    ),
    "focus_existing_tab": CapabilityTemplate(
        "navigation.focus_context", "navigation_context", "context_focused",
        "The requested existing browser context is focused.",
        ("tab_identity", "active_context"), 1,
    ),
    "close_tab": CapabilityTemplate(
        "navigation.close_context", "navigation_context", "context_closed",
        "The exact requested browser context is closed without changing another context.",
        ("tab_identity", "context_absent"), 0,
    ),
    "fill": CapabilityTemplate(
        "interaction.fill", "interaction", "value_present",
        "The grounded editable control contains the requested non-secret value.",
        ("target_identity", "observed_value"), 1,
    ),
    "click": CapabilityTemplate(
        "interaction.activate", "interaction", "declared_state_change",
        "The declared post-activation page state is observable.",
        ("target_identity", "page_state_change"), 0,
    ),
    "select_option": CapabilityTemplate(
        "interaction.select", "interaction", "selection_present",
        "The requested option is selected in the grounded control.",
        ("target_identity", "observed_selection"), 1,
    ),
    "choose_date": CapabilityTemplate(
        "interaction.select_date", "interaction", "date_present",
        "The requested date is selected in the grounded control.",
        ("target_identity", "observed_date"), 1,
    ),
    "hover": CapabilityTemplate(
        "interaction.hover", "interaction", "hover_state_visible",
        "The grounded hover target produced the declared visible state.",
        ("target_identity", "page_state_change"), 1,
    ),
    "keyboard_shortcut": CapabilityTemplate(
        "interaction.keyboard", "interaction", "declared_state_change",
        "The approved shortcut produced the declared observable state.",
        ("active_context", "page_state_change"), 0,
    ),
    "scroll": CapabilityTemplate(
        "interaction.scroll", "interaction", "viewport_changed",
        "The viewport changed and newly visible state was observed.",
        ("viewport_state",), 1,
    ),
    "wait": CapabilityTemplate(
        "discovery.observe_state", "discovery_reading", "state_observed",
        "The bounded wait ended with a newly observed page state or timeout outcome.",
        ("page_state", "elapsed_time"), 1,
    ),
    "navigate_next_page": CapabilityTemplate(
        "discovery.paginate", "discovery_reading", "result_page_changed",
        "A different result page is visible and its page identity is verified.",
        ("pagination_identity", "page_state_change"), 1,
    ),
    "upload_file": CapabilityTemplate(
        "content_transfer.insert", "content_transfer", "content_preview_visible",
        "The broker-bound content identity is visible at the exact destination before submission.",
        ("content_identity", "destination_identity", "preview_state"), 0,
    ),
    "download_file": CapabilityTemplate(
        "content_transfer.download", "content_transfer", "download_verified",
        "The downloaded content identity and approved destination are verified.",
        ("content_identity", "download_destination", "size_and_type"), 0,
    ),
}


def compile_capability_request(
    *,
    action: object,
    mission_id: str,
    objective_id: str,
    objective_identity: str | None,
    run_id: str,
) -> GenericCapabilityRequest:
    action_type = str(getattr(action, "action_type", "") or "").strip().lower()
    template = _ACTION_TEMPLATES.get(action_type)
    if template is None:
        raise ValueError(f"Unsupported generic action type: {action_type or '[empty]'}")

    consequential = getattr(action, "consequential_submission", None)
    content_insertion = getattr(action, "content_insertion", None)
    safety_level = str(getattr(action, "safety_level", "safe") or "safe").lower()
    if consequential:
        template = CapabilityTemplate(
            "consequential.submit", "consequential_operation", "submission_delivered",
            "The exact content is delivered once to the exact confirmed destination.",
            ("confirmation_binding", "destination_identity", "content_identity", "delivery_state"), 0,
        )
        safety_class = "consequential"
    elif action_type == "upload_file" or content_insertion:
        safety_class = "caution"
    elif safety_level == "danger":
        safety_class = "consequential"
    elif safety_level == "caution":
        safety_class = "caution"
    else:
        safety_class = "safe"

    action_id = str(getattr(action, "intent_id", None) or getattr(action, "action_id", "") or action_type)
    target_selector = str(getattr(action, "target_selector", "") or "")
    grounding = getattr(action, "grounding", None) or {}
    tab_id = grounding.get("tab_id") if isinstance(grounding, dict) else None
    frame_id = str(grounding.get("frame_id") or "top") if isinstance(grounding, dict) else "top"
    allowed_origin = grounding.get("origin") if isinstance(grounding, dict) else None
    resolved_identity = objective_identity or _destination_identity(content_insertion, consequential)
    return GenericCapabilityRequest(
        run_id=run_id,
        mission_id=mission_id,
        objective_id=objective_id,
        capability_id=template.capability_id,
        family=template.family,
        target=TargetIdentity(
            user_supplied_identity=resolved_identity,
            entity_type=_entity_type_for(action_type, consequential=bool(consequential)),
            exact_match_required=bool(resolved_identity) or bool(consequential),
            allowed_origin=str(allowed_origin) if allowed_origin else None,
            tab_id=int(tab_id) if isinstance(tab_id, int) and tab_id >= 0 else None,
            frame_id=frame_id,
        ),
        inputs={
            "planner_action_ref": action_id,
            "live_grounding_required": bool(target_selector),
            "content_identity": _content_identity(content_insertion, consequential),
        },
        preconditions=["objective_capability_matched", "current_page_observed", "target_grounded_live"],
        expected_effect=ExpectedEffect(
            effect_type=template.effect_type,
            observable_postcondition=template.postcondition,
            required_evidence=list(template.evidence),
        ),
        safety_class=safety_class,
        retry_budget=template.retry_budget if safety_class in {"safe", "caution"} else 0,
        idempotency_key=f"{mission_id}:{objective_id}:{action_id}",
        confirmation_required=safety_class in {"consequential", "privileged"},
        intervention_kinds=["authentication", "mfa", "captcha", "privileged_ui", "identity_ambiguity"],
    )


def _entity_type_for(action_type: str, *, consequential: bool) -> str:
    if consequential:
        return "confirmed_submission_control"
    if action_type in {"navigate", "open_new_tab", "switch_tab", "focus_existing_tab"}:
        return "browser_context"
    if action_type in {"upload_file", "download_file"}:
        return "content_transfer_control"
    if action_type == "fill":
        return "editable_control"
    return "interactive_control"


def _content_identity(content_insertion: object, consequential: object) -> str | None:
    for declaration in (consequential, content_insertion):
        if isinstance(declaration, dict):
            value = declaration.get("content_identity") or declaration.get("resource_id")
            if value:
                return str(value)
    return None


def _destination_identity(content_insertion: object, consequential: object) -> str | None:
    for declaration in (consequential, content_insertion):
        if isinstance(declaration, dict):
            value = declaration.get("destination_entity") or declaration.get("destination_identity")
            if value:
                return str(value)
    return None
