from __future__ import annotations

from app.runtime_state_manager.models import RuntimeConsistencyResult, RuntimeRecoveryEvent, RuntimeTab


def recover_runtime_state(consistency: RuntimeConsistencyResult, tabs: list[RuntimeTab]) -> RuntimeRecoveryEvent:
    if consistency.valid:
        return RuntimeRecoveryEvent("none", "runtime state is consistent", True)
    if "planner_references_missing_logical_tab" in consistency.violations:
        return RuntimeRecoveryEvent("focus_by_url", "logical tab missing; recover by canonical URL if available", bool(tabs))
    if "focused_logical_tab_missing" in consistency.violations:
        return RuntimeRecoveryEvent("recover_runtime_id", "focused logical tab missing from registry", bool(tabs))
    return RuntimeRecoveryEvent("notify_orchestrator", consistency.reason, False)
