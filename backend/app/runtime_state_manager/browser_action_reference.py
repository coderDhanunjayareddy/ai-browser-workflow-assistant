from __future__ import annotations

from app.runtime_state_manager.entity_binding import resolve_entity


_BROWSER_REFERENCE_PREFIXES = ("id:", "tab:", "ordinal:", "url:", "title:", "purpose:")


def to_browser_tab_reference(session_id: str, value: str | None) -> str | None:
    raw = _compact(value)
    if not raw:
        return None
    lowered = raw.lower()
    if lowered.startswith(_BROWSER_REFERENCE_PREFIXES):
        return raw
    if raw.startswith(("http://", "https://")):
        return f"url:{raw}"
    if raw.startswith("logical_tab_"):
        from app.runtime_state_manager.engine import resolve_logical_tab_url

        tab_url = resolve_logical_tab_url(session_id, raw) if session_id else None
        if tab_url:
            return f"url:{tab_url}"
        entity = resolve_entity(session_id, runtime_resource_id=raw) if session_id else None
        if entity and entity.canonical_url:
            return f"url:{entity.canonical_url}"
        return None
    return raw


def exposes_backend_logical_tab(value: str | None) -> bool:
    return _compact(value).startswith("logical_tab_")


def _compact(value: str | None) -> str:
    return (value or "").strip()
