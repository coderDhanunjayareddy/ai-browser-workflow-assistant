from __future__ import annotations

from typing import Any


def expected_outcomes(action_type: str) -> list[str]:
    expectations = {
        "navigate": ["url_changed", "document_loaded"],
        "click": ["dom_changed", "navigation_occurred", "modal_opened", "target_state_changed"],
        "fill": ["field_value_changed"],
        "select_option": ["selected_value_changed"],
        "choose_date": ["field_value_changed", "date_picker_closed"],
        "open_new_tab": ["tab_count_increased", "new_tab_loaded"],
        "switch_tab": ["active_tab_changed"],
        "focus_existing_tab": ["active_tab_changed"],
        "close_tab": ["tab_count_decreased"],
        "scroll": ["viewport_changed", "new_content_visible"],
        "wait": ["readiness_changed", "time_elapsed"],
        "keyboard_shortcut": ["dom_changed", "selection_changed", "application_state_changed"],
        "hover": ["hover_state_visible", "tooltip_visible"],
    }
    return expectations.get(action_type.lower(), ["browser_state_changed"])


def action_completed(step: Any) -> bool:
    data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
    result = str(data.get("execution_result") or "").lower()
    if not result:
        return False
    if result.startswith(("success", "clicked", "filled", "navigating", "waited", "scrolled", "opened")):
        return True
    verification = (data.get("page_metadata") or {}).get("verification_result") if isinstance(data.get("page_metadata"), dict) else None
    return str(verification or "").lower() in {"true", "success", "verified"}


def completed_action_count(prior_steps: list[Any]) -> int:
    return sum(1 for step in prior_steps if action_completed(step))
