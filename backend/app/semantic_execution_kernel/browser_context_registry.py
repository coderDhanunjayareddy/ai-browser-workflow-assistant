from __future__ import annotations

import hashlib
from typing import Any

from app.semantic_execution_kernel.models import BrowserContext


def build_browser_context(page_context: Any, prior_steps: list[Any]) -> BrowserContext:
    current_url = str(getattr(page_context, "url", "") or "")
    title = str(getattr(page_context, "title", "") or "")
    history = _history(prior_steps, current_url)
    focused_tab_id = _tab_id(current_url or title)
    tabs = _tabs(prior_steps, focused_tab_id, current_url, title)
    redirects = [
        {"from": history[i], "to": history[i + 1]}
        for i in range(len(history) - 1)
        if _origin(history[i]) == _origin(history[i + 1]) and history[i] != history[i + 1]
    ][-8:]
    return BrowserContext(
        focused_tab_id=focused_tab_id,
        tabs=tabs,
        current_url=current_url,
        navigation_history=history[-16:],
        redirects=redirects,
        page_purpose=_purpose(title, current_url),
    )


def _history(prior_steps: list[Any], current_url: str) -> list[str]:
    values: list[str] = []
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        for candidate in (data.get("page_url"), data.get("value")):
            url = str(candidate or "")
            if url.startswith(("http://", "https://")) and url not in values:
                values.append(url)
    if current_url and current_url not in values:
        values.append(current_url)
    return values


def _tabs(prior_steps: list[Any], focused_tab_id: str, current_url: str, title: str) -> list[dict[str, str]]:
    tabs: list[dict[str, str]] = []
    seen: set[str] = set()
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        if str(data.get("action_type") or "").lower() not in {"open_new_tab", "switch_tab", "focus_existing_tab"}:
            continue
        url = str(data.get("value") or data.get("page_url") or "")
        if url.startswith("url:"):
            url = url[4:]
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        tab_id = _tab_id(url)
        tabs.append({"tab_id": tab_id, "url": url, "title": str(data.get("page_title") or ""), "focused": str(tab_id == focused_tab_id)})
    if current_url not in seen:
        tabs.append({"tab_id": focused_tab_id, "url": current_url, "title": title, "focused": "true"})
    return tabs[-12:]


def _tab_id(value: str) -> str:
    return f"tab_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:10]}"


def _purpose(title: str, url: str) -> str:
    return (" ".join(title.split()) or url or "current page")[:140]


def _origin(url: str) -> str:
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return ""
