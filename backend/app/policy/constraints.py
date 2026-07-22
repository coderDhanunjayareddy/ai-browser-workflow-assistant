from __future__ import annotations

from typing import Any

from app.policy.models import ExecutionConstraints
from app.schemas.response import SuggestedAction


def evaluate_constraints(
    *,
    action: SuggestedAction,
    constraints: ExecutionConstraints,
    runtime: dict[str, Any] | None = None,
) -> list[str]:
    runtime = runtime or {}
    violations: list[str] = []
    if int(runtime.get("retry_count") or 0) > constraints.max_retries:
        violations.append("max_retries_exceeded")
    if int(runtime.get("navigation_count") or 0) > constraints.max_navigation_count:
        violations.append("navigation_limit_exceeded")
    if int(runtime.get("download_count") or 0) > constraints.max_download_count:
        violations.append("download_limit_exceeded")
    if int(runtime.get("upload_count") or 0) > constraints.max_upload_count:
        violations.append("upload_limit_exceeded")
    if int(runtime.get("tab_count") or 0) > constraints.max_tab_count:
        violations.append("tab_limit_exceeded")
    if int(runtime.get("actions_last_minute") or 0) > constraints.rate_limit_per_minute:
        violations.append("rate_limit_exceeded")
    if constraints.budget_tokens_remaining is not None and constraints.budget_tokens_remaining <= 0:
        violations.append("budget_exhausted")
    if action.action_type == "wait" and int(runtime.get("wait_ms") or 0) > constraints.execution_timeout_ms:
        violations.append("execution_timeout_exceeded")
    return violations
