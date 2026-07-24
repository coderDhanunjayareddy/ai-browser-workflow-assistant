from __future__ import annotations

import re
from typing import Any

from app.execution_orchestrator.models import ArtifactRegistry


def build_artifacts(page_context: Any, prior_steps: list[Any]) -> ArtifactRegistry:
    opened_pages: list[str] = []
    visited_urls: list[str] = []
    uploaded_files: list[str] = []
    downloads: list[str] = []
    screenshots: list[str] = []
    reports: list[str] = []
    tables: list[str] = []
    generated_files: list[str] = []
    forms: list[dict[str, str]] = []

    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        action_type = str(data.get("action_type") or "").lower()
        result = str(data.get("execution_result") or "")
        value = str(data.get("value") or "")
        page_url = str(data.get("page_url") or "")
        if page_url.startswith(("http://", "https://")):
            _append_unique(visited_urls, page_url)
        if action_type == "open_new_tab" and _success(result):
            url = _url(value) or page_url
            if url:
                _append_unique(opened_pages, url)
        if action_type == "fill" and _success(result):
            forms.append({"field": str(data.get("target_selector") or ""), "value": value[:120]})
        metadata = data.get("page_metadata") or {}
        if isinstance(metadata, dict):
            _append_metadata(screenshots, metadata, "screenshot")
            _append_metadata(uploaded_files, metadata, "uploaded_file")
            _append_metadata(downloads, metadata, "download")
            _append_metadata(reports, metadata, "report")
            _append_metadata(tables, metadata, "table")
            _append_metadata(generated_files, metadata, "generated_file")

    current_url = str(getattr(page_context, "url", "") or "")
    if current_url.startswith(("http://", "https://")):
        _append_unique(visited_urls, current_url)
    extracted_records = _records_from_page(page_context)
    return ArtifactRegistry(
        opened_pages=opened_pages,
        visited_urls=visited_urls,
        extracted_records=extracted_records,
        screenshots=screenshots,
        uploaded_files=uploaded_files,
        downloads=downloads,
        reports=reports,
        tables=tables,
        summaries=[],
        contacts=[],
        forms=forms,
        generated_files=generated_files,
    )


def _records_from_page(page_context: Any) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for block in list(getattr(page_context, "content_blocks", []) or [])[:12]:
        data = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        text = " ".join(str(data.get("text") or "").split())
        href = str(data.get("href") or "")
        if text:
            records.append({"text": text[:240], "url": href[:240]})
    return records


def _append_metadata(target: list[str], metadata: dict[str, Any], key: str) -> None:
    value = metadata.get(key) or metadata.get(f"{key}_url") or metadata.get(f"{key}_path")
    if value:
        _append_unique(target, str(value))


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _success(result: str) -> bool:
    return result.lower().startswith(("success", "clicked", "filled", "navigating", "opened", "waited", "scrolled"))


def _url(value: str) -> str | None:
    match = re.search(r"https?://[^\s<>'\"]+", value or "", flags=re.IGNORECASE)
    return match.group(0).rstrip("),.;]") if match else None
