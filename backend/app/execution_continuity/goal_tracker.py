from __future__ import annotations

import re
from typing import Any

from app.execution_continuity.action_history import SUCCESS_PREFIXES
from app.execution_continuity.models import Checkpoint, MissionProgress


def build_mission_progress(task: str, prior_steps: list[Any]) -> MissionProgress:
    planned = _derive_checkpoints(task)
    completed = _completed_descriptions(prior_steps)
    failed = _failed_descriptions(prior_steps)
    retry_counts = _retry_counts(prior_steps)
    checkpoints = _status_checkpoints(planned, completed, failed)
    completed_labels = [checkpoint.description for checkpoint in checkpoints if checkpoint.status == "completed"]
    remaining_labels = [checkpoint.description for checkpoint in checkpoints if checkpoint.status == "pending"]
    blocked = [checkpoint.description for checkpoint in checkpoints if checkpoint.status == "blocked"]
    failed_labels = [checkpoint.description for checkpoint in checkpoints if checkpoint.status == "failed"]
    progress_percent = int(round((len(completed_labels) / max(len(checkpoints), 1)) * 100))
    return MissionProgress(
        original_mission=task,
        current_objective=remaining_labels[0] if remaining_labels else "finalize output",
        completed_subtasks=completed_labels,
        remaining_subtasks=remaining_labels,
        blocked_objectives=blocked,
        failed_objectives=failed_labels,
        retry_counts=retry_counts,
        progress_percent=progress_percent,
        checkpoints=checkpoints,
    )


def _derive_checkpoints(task: str) -> list[str]:
    lines = [_clean(line) for line in task.splitlines()]
    numbered = [re.sub(r"^\d+[\).]\s*", "", line) for line in lines if re.match(r"^\d+[\).]\s+", line)]
    checkpoints = numbered or _imperative_sentences(task)
    count_match = re.search(r"\b(?:top|first)\s+(\d+)\b.*\b(?:results|items|jobs|entries|pages|sources)\b", task, re.IGNORECASE)
    if count_match and any("open" in item.lower() for item in checkpoints):
        count = min(int(count_match.group(1)), 20)
        expanded: list[str] = []
        for item in checkpoints:
            if "open" in item.lower() and re.search(r"\b(results|items|pages|sources)\b", item, re.IGNORECASE):
                expanded.extend([f"{item} #{i}" for i in range(1, count + 1)])
            else:
                expanded.append(item)
        checkpoints = expanded
    if not checkpoints:
        checkpoints = ["understand current page", "perform requested browser action", "return final answer"]
    if not any("final" in item.lower() or "return" in item.lower() or "report" in item.lower() for item in checkpoints):
        checkpoints.append("return final answer")
    return _dedupe(checkpoints)[:24]


def _imperative_sentences(task: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+", " ".join(task.split()))
    keywords = ("open", "search", "find", "collect", "extract", "capture", "return", "create", "verify", "read")
    return [_clean(piece.rstrip(".!?")) for piece in pieces if piece.lower().startswith(keywords)]


def _status_checkpoints(planned: list[str], completed: list[str], failed: list[str]) -> list[Checkpoint]:
    completed_text = " | ".join(completed).lower()
    failed_text = " | ".join(failed).lower()
    checkpoints: list[Checkpoint] = []
    first_pending_seen = False
    for index, item in enumerate(planned, 1):
        terms = _terms(item)
        status = "pending"
        evidence = None
        if terms and any(term in completed_text for term in terms[:4]):
            status = "completed"
            evidence = "matched successful action evidence"
        elif terms and any(term in failed_text for term in terms[:4]):
            status = "failed"
            evidence = "matched failed action evidence"
        elif first_pending_seen:
            status = "pending"
        else:
            first_pending_seen = True
        checkpoints.append(Checkpoint(id=f"cp_{index}", description=item, status=status, evidence=evidence))
    return checkpoints


def _completed_descriptions(prior_steps: list[Any]) -> list[str]:
    items: list[str] = []
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        if str(data.get("execution_result") or "").lower().startswith(SUCCESS_PREFIXES):
            items.append(_clean(data.get("description") or data.get("action_type") or "completed step"))
    return items


def _failed_descriptions(prior_steps: list[Any]) -> list[str]:
    items: list[str] = []
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        result = str(data.get("execution_result") or "")
        if result and not result.lower().startswith(SUCCESS_PREFIXES):
            items.append(_clean(data.get("description") or data.get("action_type") or "failed step"))
    return items


def _retry_counts(prior_steps: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        key = _clean(data.get("description") or data.get("target_selector") or data.get("action_type") or "step")[:80]
        counts[key] = counts.get(key, 0) + 1
    return {key: value for key, value in counts.items() if value > 1}


def _terms(text: str) -> list[str]:
    stop = {"the", "and", "for", "with", "from", "that", "this", "into", "page", "result"}
    return [term for term in re.findall(r"[a-z0-9]{3,}", text.lower()) if term not in stop]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
    return result
