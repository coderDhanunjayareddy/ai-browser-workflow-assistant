from __future__ import annotations

import re
from typing import Any

from app.runtime_state_manager.execution_result import is_successful_execution_result
from app.semantic_execution_kernel.models import MissionGoal, MissionState


def build_mission_state(task: str, prior_steps: list[Any]) -> MissionState:
    goals = _derive_goals(task)
    completed_text = " ".join(_successful_descriptions(prior_steps)).lower()
    failed_text = " ".join(_failed_descriptions(prior_steps)).lower()
    typed_goals: list[MissionGoal] = []
    current_goal_id: str | None = None
    for index, description in enumerate(goals, 1):
        terms = _terms(description)
        status = "pending"
        evidence: list[str] = []
        failure_reason = None
        retries = _retry_count(description, prior_steps)
        if terms and any(term in completed_text for term in terms[:4]):
            status = "completed"
            evidence = ["prior successful action matched goal terms"]
        elif terms and any(term in failed_text for term in terms[:4]):
            status = "failed"
            failure_reason = "prior failed action matched goal terms"
        goal = MissionGoal(
            id=f"goal_{index}",
            description=description,
            status=status,  # type: ignore[arg-type]
            evidence=evidence,
            retries=retries,
            failure_reason=failure_reason,
        )
        if current_goal_id is None and status == "pending":
            current_goal_id = goal.id
            goal = MissionGoal(**{**goal.to_dict(), "status": "running"})
        typed_goals.append(goal)
    blocked = any(goal.retries >= 3 and goal.status == "failed" for goal in typed_goals)
    return MissionState(
        mission=task,
        goals=typed_goals,
        current_goal_id=current_goal_id,
        blocked=blocked,
        failure_reason="retry budget exceeded" if blocked else None,
    )


def _derive_goals(task: str) -> list[str]:
    lines = [" ".join(line.split()) for line in task.splitlines()]
    numbered = [re.sub(r"^\d+[\).]\s*", "", line) for line in lines if re.match(r"^\d+[\).]\s+", line)]
    goals = numbered or [piece.strip(" .") for piece in re.split(r"(?<=[.!?])\s+", " ".join(task.split())) if piece.strip()]
    if not goals:
        goals = ["complete requested browser workflow"]
    if not any(goal.lower().startswith(("return", "report", "create final")) for goal in goals):
        goals.append("return final answer")
    return _dedupe(goals)[:24]


def _successful_descriptions(prior_steps: list[Any]) -> list[str]:
    return [
        str((step.model_dump() if hasattr(step, "model_dump") else dict(step)).get("description") or "")
        for step in prior_steps
        if is_successful_execution_result((step.model_dump() if hasattr(step, "model_dump") else dict(step)).get("execution_result"))
    ]


def _failed_descriptions(prior_steps: list[Any]) -> list[str]:
    return [
        str((step.model_dump() if hasattr(step, "model_dump") else dict(step)).get("description") or "")
        for step in prior_steps
        if not is_successful_execution_result((step.model_dump() if hasattr(step, "model_dump") else dict(step)).get("execution_result"))
    ]


def _retry_count(description: str, prior_steps: list[Any]) -> int:
    terms = set(_terms(description)[:4])
    if not terms:
        return 0
    count = 0
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        if is_successful_execution_result(data.get("execution_result")):
            continue
        if terms & set(_terms(data.get("description") or "")):
            count += 1
    return count


def _terms(text: Any) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "page", "result"}
    return [term for term in re.findall(r"[a-z0-9]{3,}", str(text).lower()) if term not in stop]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out
