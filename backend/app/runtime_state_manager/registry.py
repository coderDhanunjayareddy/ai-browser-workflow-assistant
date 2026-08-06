from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

from app.runtime_state_manager.models import RuntimeTab, RuntimeWindow
from app.runtime_state_manager.entity_binding import bind_runtime_resource, resolve_entity


class BrowserRuntimeRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tabs: dict[str, dict[str, RuntimeTab]] = {}
        self._windows: dict[str, dict[str, RuntimeWindow]] = {}

    def synchronize(self, session_id: str, page_context: Any, prior_steps: list[Any]) -> tuple[list[RuntimeWindow], list[RuntimeTab]]:
        now = int(time.time() * 1000)
        with self._lock:
            tabs = dict(self._tabs.get(session_id, {}))
            windows = dict(self._windows.get(session_id, {}))
            window_id = "logical_window_1"
            active_url = str(getattr(page_context, "url", "") or "")
            active_title = str(getattr(page_context, "title", "") or "")
            focus_index = len(tabs) + 1
            active_tab = _runtime_tab(
                url=active_url,
                title=active_title,
                window_id=window_id,
                active=True,
                focus_index=focus_index,
                now=now,
                previous=tabs.get(_logical_tab_id(active_url or active_title)),
            )
            tabs[active_tab.logical_id] = active_tab
            _bind_url_entity(session_id, active_tab.url, active_tab.logical_id)
            for step in prior_steps:
                data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
                action_type = str(data.get("action_type") or "").lower()
                if action_type not in {"open_new_tab", "switch_tab", "focus_existing_tab", "navigate"}:
                    continue
                evidence = data.get("browser_evidence") if isinstance(data.get("browser_evidence"), dict) else {}
                url = _evidence_url(evidence) or _extract_url(str(data.get("value") or "")) or str(data.get("page_url") or "")
                if not url.startswith(("http://", "https://")):
                    continue
                logical_id = _logical_tab_id(url)
                existing = tabs.get(logical_id)
                tabs[logical_id] = _runtime_tab(
                    url=url,
                    title=str(evidence.get("page_title") or data.get("page_title") or ""),
                    window_id=window_id,
                    active=(url == active_url),
                    focus_index=focus_index if url == active_url else 0,
                    now=now,
                    previous=existing,
                    opener_logical_id=None,
                )
                _bind_url_entity(session_id, url, logical_id)
            tab_ids = list(tabs)
            windows[window_id] = RuntimeWindow(logical_id=window_id, runtime_id=None, active=True, tab_ids=tab_ids)
            self._tabs[session_id] = tabs
            self._windows[session_id] = windows
            return list(windows.values()), list(tabs.values())

    def get_tab(self, session_id: str, logical_id: str) -> RuntimeTab | None:
        with self._lock:
            return self._tabs.get(session_id, {}).get(logical_id)

    def restore(self, session_id: str, tabs: list[RuntimeTab], windows: list[RuntimeWindow]) -> None:
        with self._lock:
            self._tabs[session_id] = {tab.logical_id: tab for tab in tabs}
            self._windows[session_id] = {window.logical_id: window for window in windows}


def _runtime_tab(
    *,
    url: str,
    title: str,
    window_id: str,
    active: bool,
    focus_index: int,
    now: int,
    previous: RuntimeTab | None = None,
    opener_logical_id: str | None = None,
) -> RuntimeTab:
    history = list(previous.navigation_history) if previous else []
    if url and (not history or history[-1] != url):
        history.append(url)
    return RuntimeTab(
        logical_id=_logical_tab_id(url or title),
        runtime_id=None,
        window_id=window_id,
        url=url,
        title=title,
        page_type=_page_type(url, title),
        opener_logical_id=opener_logical_id or (previous.opener_logical_id if previous else None),
        lifecycle="active" if active else ("navigated" if previous and previous.url != url else "opened"),
        active=active,
        focus_index=focus_index,
        navigation_history=history[-20:],
        created_at_ms=previous.created_at_ms if previous else now,
        updated_at_ms=now,
    )


def _logical_tab_id(value: str) -> str:
    return f"logical_tab_{hashlib.sha1(value.encode('utf-8')).hexdigest()[:10]}"


def _page_type(url: str, title: str) -> str:
    text = f"{url} {title}".lower()
    if "login" in text or "signin" in text:
        return "login"
    if "signup" in text or "register" in text:
        return "signup"
    if "pdf" in text:
        return "pdf"
    if "docs" in text or "documentation" in text:
        return "documentation"
    if "search" in text:
        return "search"
    return "web_page"


def _extract_url(value: str) -> str | None:
    if value.startswith("url:"):
        value = value[4:]
    if value.startswith(("http://", "https://")):
        return value
    return None


def _evidence_url(evidence: dict[str, Any]) -> str | None:
    for key in ("page_url", "requested_url", "opened_url", "url"):
        url = _extract_url(str(evidence.get(key) or ""))
        if url:
            return url
    return None


def _bind_url_entity(session_id: str, url: str, logical_tab_id: str) -> None:
    if not url.startswith(("http://", "https://")):
        return
    entity = resolve_entity(session_id, canonical_url=url)
    if entity is not None:
        bind_runtime_resource(session_id, entity_id=entity.entity_id, runtime_resource_id=logical_tab_id)
