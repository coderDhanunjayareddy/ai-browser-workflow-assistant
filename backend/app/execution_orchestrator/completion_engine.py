from __future__ import annotations

import re
from typing import Any

from app.browser_url_policy import is_openable_browser_url
from app.execution_orchestrator.models import ArtifactRegistry, ProgressLedger
from app.task_language import affirmative_task_text


def build_progress_ledger(
    task: str,
    artifacts: ArtifactRegistry,
    prior_steps: list[Any],
    *,
    session_id: str | None = None,
) -> ProgressLedger:
    targets = _targets(task)
    current = {
        "opened_pages": len(artifacts.opened_pages),
        "visited_urls": len(artifacts.visited_urls),
        "extracted_records": len(artifacts.extracted_records),
        "uploaded_files": len(artifacts.uploaded_files),
        "downloads": len(artifacts.downloads),
        "forms": len(artifacts.forms),
        "collected_items": max(
            len(artifacts.opened_pages),
            len(artifacts.extracted_records),
            _count_collected(prior_steps),
            _count_registered_collected(session_id),
        ),
    }
    completed = {
        "discover": current["visited_urls"] > 0,
        "collect": current["collected_items"] >= targets.get("collected_items", 1),
        "open": current["opened_pages"] >= targets.get("opened_pages", targets.get("collected_items", 1)),
        "read": _read_complete(task, artifacts, prior_steps),
        "extract": current["extracted_records"] >= targets.get("extracted_records", 1) if _requires_extraction(task) else True,
        "validate": _validate_complete(task, artifacts, prior_steps),
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
    text = affirmative_task_text(task)
    targets: dict[str, int] = {}
    count = _first_count(text) or 1
    if any(term in text for term in (
        "top", "first", "results", "sources", "pages", "entries", "jobs", "companies",
        "products", "tools", "websites",
    )):
        targets["collected_items"] = count
        targets["opened_pages"] = count if any(term in text for term in (
            "open", "read each", "each page", "for each", "each one", "different tools",
        )) else 1
    if any(term in text for term in ("extract", "capture", "collect")):
        targets["extracted_records"] = count
    if "upload" in text or "attach" in text:
        targets["uploaded_files"] = 1
    if "download" in text:
        targets["downloads"] = 1
    return targets or {"collected_items": 1, "opened_pages": 1, "extracted_records": 1}


def _first_count(text: str) -> int | None:
    patterns = (
        r"\b(?:top|first|at least)\s+(\d+)\b",
        r"\bcollect\s+(\d+)\b",
        r"\bchoose\s+(\d+)\b",
        r"\b(?:pick|choose|open|compare)\s+(\d+)(?:\s+[\w-]+){0,5}\s+(?:products|tools|websites|sources|pages)\b",
        r"\b(\d+)(?:\s+[\w-]+){0,5}\s+(?:entries|jobs|companies|sources|results|pages|products|tools|websites)\b",
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


def _count_registered_collected(session_id: str | None) -> int:
    if not session_id:
        return 0
    try:
        from app.runtime_state_manager.entity_binding import list_entities

        return len(
            [
                entity
                for entity in list_entities(session_id)
                if entity.entity_type == "search_result"
                and entity.state != "INVALID"
                and entity.canonical_url
                and is_openable_browser_url(entity.canonical_url)
            ]
        )
    except Exception:
        return 0


def _collected_result_count(result: str) -> int:
    match = re.search(r"\bcollected\s+(\d{1,3})\b|\bsearch_result_count[=:]\s*(\d{1,3})\b|\bresult_count[=:]\s*(\d{1,3})\b", result)
    if not match:
        return 0
    return max(0, min(next((int(group) for group in match.groups() if group), 0), 100))


def _read_complete(task: str, artifacts: ArtifactRegistry, prior_steps: list[Any]) -> bool:
    if artifacts.opened_pages and _is_current_page_interaction(affirmative_task_text(task)):
        return True
    target = _targets(task).get("opened_pages", 1)
    read_steps = 0
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        action_type = str(data.get("action_type") or "").lower()
        result = str(data.get("execution_result") or "")
        text = f"{data.get('description', '')} {data.get('page_analysis', '')}".lower()
        result_text = result.lower()
        if action_type in {"read_page", "read"} and any(
            marker in result_text
            for marker in (
                "intent execution queue completed",
                "knowledge extraction executed read_page",
                "executed read_page",
                "read page",
                "success",
            )
        ):
            read_steps += 1
        elif action_type in {"focus_existing_tab", "switch_tab"} and is_openable_browser_url(str(data.get("value") or "")):
            read_steps += 1
        elif result.startswith("success") and action_type in {"focus_existing_tab", "switch_tab"}:
            read_steps += 1
        elif any(term in text for term in ("read", "extract", "summarize", "pricing", "limitation")):
            read_steps += 1
    return read_steps >= min(target, max(len(artifacts.opened_pages), 1))


def _is_current_page_interaction(text: str) -> bool:
    return _is_simple_search_interaction(text) or any(
        term in text
        for term in (
            "log in",
            "login",
            "sign in",
            "fill",
            "form",
            "modal",
            "setting",
            "upload",
            "signup",
            "sign up",
            "page 2",
            "next page",
            "paged list",
            "pagination",
            "play",
            "listen",
            "music",
            "song",
            "video",
        )
    )


def _requires_extraction(task: str) -> bool:
    return any(term in affirmative_task_text(task) for term in ("extract", "capture", "table", "summar", "pricing", "limitation", "location", "job"))


def _validate_complete(task: str, artifacts: ArtifactRegistry, prior_steps: list[Any]) -> bool:
    text = affirmative_task_text(task)
    if _is_interactive_task(text) or _is_simple_search_interaction(text):
        return _target_state_reached(prior_steps)
    if "upload" in text:
        return bool(artifacts.uploaded_files)
    if "download" in text:
        return bool(artifacts.downloads)
    if "form" in text:
        return bool(artifacts.forms)
    return bool(artifacts.extracted_records or artifacts.opened_pages)


def _is_simple_search_interaction(text: str) -> bool:
    if "search for" not in text:
        return False
    return not any(
        term in text
        for term in (
            "compare",
            "comparison",
            "multiple sources",
            "each page",
            "each source",
            "top 5",
            "top five",
            "first page of results",
        )
    )


def _is_interactive_task(text: str) -> bool:
    return any(
        term in text
        for term in (
            "send",
            "message",
            "whatsapp",
            "gmail",
            "mail",
            "chat",
            "profile",
            "setting",
            "dashboard",
            "create",
            "update",
            "save",
            "log in",
            "login",
            "sign in",
            "modal",
            "fill",
            "form",
            "upload",
            "page 2",
            "next page",
            "paged list",
            "pagination",
            "play",
            "listen",
            "music",
            "song",
            "video",
        )
    )


def _target_state_reached(prior_steps: list[Any]) -> bool:
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        result = str(data.get("execution_result") or "").lower()
        description = str(data.get("description") or "").lower()
        evidence = str(data.get("page_analysis") or "").lower()
        combined = " ".join((result, description, evidence))
        if any(
            marker in combined
            for marker in (
                "message sent",
                "sent successfully",
                "submitted successfully",
                "saved successfully",
                "dashboard loaded",
                "welcome page",
                "target state reached",
                "media play completed",
                "playback started",
                "video playing",
            )
        ):
            return True
    return False
