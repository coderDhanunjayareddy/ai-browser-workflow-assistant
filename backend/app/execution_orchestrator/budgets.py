from __future__ import annotations

from typing import Any

from app.execution_orchestrator.models import ArtifactRegistry, ExecutionBudgets
from app.runtime_state_manager.execution_result import is_successful_execution_result


def build_budgets(prior_steps: list[Any], artifacts: ArtifactRegistry) -> ExecutionBudgets:
    consumed = {
        "tabs": len(artifacts.opened_pages),
        "pages": len(artifacts.visited_urls),
        "extractions": len(artifacts.extracted_records),
        "planner_turns": len(prior_steps),
        "retries": _retry_count(prior_steps),
    }
    budget = ExecutionBudgets(consumed=consumed)
    exhausted: list[str] = []
    if consumed["tabs"] >= budget.max_tabs:
        exhausted.append("max_tabs")
    if consumed["pages"] >= budget.max_pages:
        exhausted.append("max_pages")
    if consumed["extractions"] >= budget.max_extractions:
        exhausted.append("max_extractions")
    if consumed["planner_turns"] >= budget.max_planner_turns:
        exhausted.append("max_planner_turns")
    if consumed["retries"] >= budget.max_retries:
        exhausted.append("max_retries")
    return ExecutionBudgets(consumed=consumed, exhausted=exhausted)


def _retry_count(prior_steps: list[Any]) -> int:
    signatures: dict[str, int] = {}
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        result = str(data.get("execution_result") or "")
        result_text = result.lower()
        if is_successful_execution_result(result) and not any(
            marker in result_text
            for marker in ("no_effect", "no visible change", "retrying", "failed", "error")
        ):
            continue
        signature = "|".join([
            str(data.get("action_type") or ""),
            str(data.get("target_selector") or ""),
            str(data.get("value") or ""),
            str(data.get("page_url") or ""),
        ])
        signatures[signature] = signatures.get(signature, 0) + 1
    return max(signatures.values(), default=0)
