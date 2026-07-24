from __future__ import annotations

import hashlib
from typing import Any

from app.execution_continuity.models import BrowserStateSnapshot, BrowserTabSnapshot


def build_browser_state(page_context: Any, prior_steps: list[Any]) -> BrowserStateSnapshot:
    current_url = str(getattr(page_context, "url", "") or "")
    current_title = str(getattr(page_context, "title", "") or "")
    visited = _visited_urls(prior_steps, current_url)
    previous_url = visited[-2] if len(visited) > 1 else None
    active = BrowserTabSnapshot(
        tab_id=_stable_tab_id(current_url or current_title or "active"),
        url=current_url,
        title=current_title,
        purpose=_infer_purpose(current_title, current_url),
        active=True,
    )
    tabs = _infer_tabs(prior_steps, active)
    entities = _extract_entities(page_context)
    return BrowserStateSnapshot(
        active_tab=active,
        tabs=tabs,
        current_url=current_url,
        previous_url=previous_url,
        navigation_history=visited[-12:],
        visited_pages=visited,
        extracted_entities=entities,
    )


def _visited_urls(prior_steps: list[Any], current_url: str) -> list[str]:
    urls: list[str] = []
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        for candidate in (data.get("page_url"), data.get("value")):
            text = str(candidate or "")
            if text.startswith(("http://", "https://")) and text not in urls:
                urls.append(text)
    if current_url and current_url not in urls:
        urls.append(current_url)
    return urls


def _infer_tabs(prior_steps: list[Any], active: BrowserTabSnapshot) -> list[BrowserTabSnapshot]:
    tabs: list[BrowserTabSnapshot] = []
    seen: set[str] = set()
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        if str(data.get("action_type") or "").lower() not in {"open_new_tab", "switch_tab", "focus_existing_tab"}:
            continue
        url = _url_from_value(data.get("value")) or str(data.get("page_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        tabs.append(
            BrowserTabSnapshot(
                tab_id=_stable_tab_id(url),
                url=url,
                title=str(data.get("page_title") or ""),
                purpose=_infer_purpose(str(data.get("description") or ""), url),
                active=False,
            )
        )
    if active.url not in seen:
        tabs.append(active)
    else:
        tabs = [active if tab.url == active.url else tab for tab in tabs]
    return tabs[-12:]


def _extract_entities(page_context: Any) -> list[dict[str, str]]:
    entities: list[dict[str, str]] = []
    for block in list(getattr(page_context, "content_blocks", []) or [])[:8]:
        data = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        text = " ".join(str(data.get("text") or "").split())
        href = str(data.get("href") or "")
        if text:
            entities.append({"kind": "visible_content", "text": text[:180], "url": href[:220]})
    return entities


def _url_from_value(value: Any) -> str | None:
    text = str(value or "")
    if text.startswith("url:"):
        text = text[4:]
    if text.startswith(("http://", "https://")):
        return text
    return None


def _stable_tab_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def _infer_purpose(text: str, url: str) -> str:
    source = " ".join(str(text or "").split()) or url
    return source[:120]
