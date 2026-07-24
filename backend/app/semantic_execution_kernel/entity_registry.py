from __future__ import annotations

import hashlib
from typing import Any

from app.semantic_execution_kernel.models import BrowserBinding, SemanticEntity


def build_entity_registry(page_context: Any) -> list[SemanticEntity]:
    entities: list[SemanticEntity] = []
    source_page = str(getattr(page_context, "url", "") or "")
    for element in list(getattr(page_context, "interactive_elements", []) or [])[:120]:
        data = element.model_dump() if hasattr(element, "model_dump") else dict(element)
        title = _title(data)
        entity_type = _semantic_type(data)
        url = str(data.get("href") or "") or None
        selector = str(data.get("selector") or "") or None
        if not title and not url and not selector:
            continue
        entities.append(
            SemanticEntity(
                id=_entity_id(entity_type, title, url, selector),
                semantic_type=entity_type,
                title=title or entity_type,
                url=url,
                confidence=_confidence(data),
                source_page=source_page,
                metadata=_metadata(data),
                browser_bindings=BrowserBinding(
                    selector=selector,
                    selector_id=str(data.get("selector_id") or "") or None,
                    href=url,
                ),
            )
        )
    for block in list(getattr(page_context, "content_blocks", []) or [])[:60]:
        data = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        text = " ".join(str(data.get("text") or "").split())
        href = str(data.get("href") or "") or None
        if not text and not href:
            continue
        entity_type = "link" if href else "document"
        entities.append(
            SemanticEntity(
                id=_entity_id(entity_type, text[:120], href, data.get("selector")),
                semantic_type=entity_type,
                title=text[:180] or href or entity_type,
                url=href,
                confidence=0.78 if href else 0.65,
                source_page=source_page,
                metadata={"text": text[:300]},
                browser_bindings=BrowserBinding(selector=str(data.get("selector") or "") or None, href=href),
            )
        )
    return _dedupe_entities(entities)[:80]


def find_entity(entities: list[SemanticEntity], *, entity_id: str | None = None, url: str | None = None, selector: str | None = None) -> SemanticEntity | None:
    for entity in entities:
        if entity_id and entity.id == entity_id:
            return entity
        if url and entity.url and entity.url.rstrip("/") == url.rstrip("/"):
            return entity
        if selector and entity.browser_bindings.selector == selector:
            return entity
    return None


def _semantic_type(data: dict[str, Any]) -> str:
    role = str(data.get("role") or "").lower()
    input_type = str(data.get("input_type") or "").lower()
    tag = str(data.get("type") or data.get("tag") or "").lower()
    text = " ".join(str(data.get(key) or "") for key in ("text", "aria_label", "accessibility_name", "placeholder")).lower()
    if data.get("href") or tag == "a" or role == "link":
        return "link"
    if tag in {"button"} or role == "button":
        return "button"
    if input_type in {"file"}:
        return "file"
    if tag in {"input", "textarea", "select"} or input_type:
        return "form"
    if "table" in role or tag in {"tr", "td", "row"}:
        return "table_row"
    if any(word in text for word in ("message", "email")):
        return "message"
    if "job" in text:
        return "job_posting"
    if any(word in text for word in ("price", "plan", "product")):
        return "product"
    return "document"


def _title(data: dict[str, Any]) -> str:
    for key in ("text", "accessibility_name", "aria_label", "placeholder", "name"):
        value = " ".join(str(data.get(key) or "").split())
        if value:
            return value[:220]
    return ""


def _confidence(data: dict[str, Any]) -> float:
    score = 0.55
    if data.get("selector"):
        score += 0.12
    if data.get("href"):
        score += 0.15
    if _title(data):
        score += 0.12
    if data.get("role") or data.get("accessibility_name"):
        score += 0.06
    return min(score, 0.98)


def _metadata(data: dict[str, Any]) -> dict[str, str]:
    keys = ("role", "input_type", "placeholder", "aria_label", "accessibility_name", "state")
    return {key: str(data.get(key))[:180] for key in keys if data.get(key)}


def _entity_id(entity_type: str, title: Any, url: Any, selector: Any) -> str:
    raw = "|".join([entity_type, str(title or ""), str(url or ""), str(selector or "")])
    return f"ent_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}"


def _dedupe_entities(entities: list[SemanticEntity]) -> list[SemanticEntity]:
    seen: set[str] = set()
    out: list[SemanticEntity] = []
    for entity in entities:
        key = (entity.url or entity.browser_bindings.selector or entity.title).lower().rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(entity)
    return out
