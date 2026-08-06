from __future__ import annotations

import re
from typing import Any

from app.execution_orchestrator.models import ArtifactRegistry, ProgressLedger


def build_progress_ledger(task: str, artifacts: ArtifactRegistry, prior_steps: list[Any]) -> ProgressLedger:
    targets = _targets(task)
    current = {
        "opened_pages": len(artifacts.opened_pages),
        "visited_urls": len(artifacts.visited_urls),
        "extracted_records": len(artifacts.extracted_records),
        "uploaded_files": len(artifacts.uploaded_files),
        "downloads": len(artifacts.downloads),
        "forms": len(artifacts.forms),
        "collected_items": max(len(artifacts.opened_pages), len(artifacts.extracted_records), _count_collected(prior_steps)),
    }
    completed = {
        "discover": current["visited_urls"] > 0,
        "collect": current["collected_items"] >= targets.get("collected_items", 1),
        "open": current["opened_pages"] >= targets.get("opened_pages", targets.get("collected_items", 1)),
        "read": _read_complete(task, artifacts, prior_steps),
        "extract": current["extracted_records"] >= targets.get("extracted_records", 1) if _requires_extraction(task) else True,
        "validate": _validate_complete(task, artifacts),
        "synthesize": bool(artifacts.reports or artifacts.tables or artifacts.summaries),
        "report": bool(artifacts.reports),
        "complete": False,
    }
    notes = [
        f"opened_pages={current['opened_pages']}/{targets.get('opened_pages', targets.get('collected_items', 1))}",
        f"extracted_records={current['extracted_records']}/{targets.get('extracted_records', 1)}",
    ]
    return ProgressLedger(target_counts=targets, current_counts=current, completed=completed, notes=notes)


def _targets(task: str) -> dict[str, int]:
    text = task.lower()
    targets: dict[str, int] = {}
    count = _first_count(text) or 1
    if any(term in text for term in ("top", "first", "results", "sources", "pages", "entries", "jobs", "companies")):
        targets["collected_items"] = count
        targets["opened_pages"] = count if any(term in text for term in ("open", "read each", "each page")) else 1
    if any(term in text for term in ("extract", "capture", "collect")):
        targets["extracted_records"] = count
    if "upload" in text:
        targets["uploaded_files"] = 1
    if "download" in text:
        targets["downloads"] = 1
    return targets or {"collected_items": 1, "opened_pages": 1, "extracted_records": 1}


def _first_count(text: str) -> int | None:
    patterns = (
        r"\b(?:top|first|at least)\s+(\d+)\b",
        r"\bcollect\s+(\d+)\b",
        r"\bchoose\s+(\d+)\b",
        r"\b(\d+)\s+(?:entries|jobs|companies|sources|results|pages|tools)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return min(max(int(match.group(1)), 1), 100)
    return None


def _count_collected(prior_steps: list[Any]) -> int:
    count = 0
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        description = str(data.get("description") or "").lower()
        result = str(data.get("execution_result") or "").lower()
        if "collect" in description and result.startswith("success"):
            count += _collected_result_count(result) or 1
    return count


def _collected_result_count(result: str) -> int:
    match = re.search(r"\bcollected\s+(\d{1,3})\b|\bsearch_result_count[=:]\s*(\d{1,3})\b|\bresult_count[=:]\s*(\d{1,3})\b", result)
    if not match:
        return 0
    return max(0, min(next((int(group) for group in match.groups() if group), 0), 100))


def _read_complete(task: str, artifacts: ArtifactRegistry, prior_steps: list[Any]) -> bool:
    target = _targets(task).get("opened_pages", 1)
    read_steps = 0
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        text = f"{data.get('description', '')} {data.get('page_analysis', '')}".lower()
        if any(term in text for term in ("read", "extract", "summarize", "pricing", "limitation")):
            read_steps += 1
    return read_steps >= min(target, max(len(artifacts.opened_pages), 1))


def _requires_extraction(task: str) -> bool:
    return any(term in task.lower() for term in ("extract", "capture", "table", "summar", "pricing", "limitation", "location", "job"))


def _validate_complete(task: str, artifacts: ArtifactRegistry) -> bool:
    text = task.lower()
    if "upload" in text:
        return bool(artifacts.uploaded_files)
    if "download" in text:
        return bool(artifacts.downloads)
    if "form" in text:
        return bool(artifacts.forms)
    return bool(artifacts.extracted_records or artifacts.opened_pages)
