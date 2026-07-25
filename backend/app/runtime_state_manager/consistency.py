from __future__ import annotations

from app.runtime_state_manager.models import RuntimeConsistencyResult, RuntimeTab
from app.schemas.response import AnalyzeResponse


def validate_runtime_consistency(
    *,
    tabs: list[RuntimeTab],
    focused_tab_id: str | None,
    planner_response: AnalyzeResponse | None = None,
) -> RuntimeConsistencyResult:
    violations: list[str] = []
    tab_ids = {tab.logical_id for tab in tabs}
    if focused_tab_id and focused_tab_id not in tab_ids:
        violations.append("focused_logical_tab_missing")
    if not any(tab.active for tab in tabs):
        violations.append("no_active_tab")
    if planner_response and planner_response.suggested_actions:
        action = planner_response.suggested_actions[0]
        value = action.value or action.target_selector or ""
        if action.action_type in {"switch_tab", "focus_existing_tab"} and value.startswith("logical_tab_") and value not in tab_ids:
            violations.append("planner_references_missing_logical_tab")
    return RuntimeConsistencyResult(
        valid=not violations,
        violations=violations,
        repairable=any(item in violations for item in {"focused_logical_tab_missing", "planner_references_missing_logical_tab"}),
        reason="consistent" if not violations else ", ".join(violations),
    )
