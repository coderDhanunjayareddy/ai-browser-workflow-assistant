from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from app.knowledge_extraction.models import PageReadArtifact


def read_page(page_context: Any) -> PageReadArtifact:
    started = int(time.time() * 1000)
    url = str(getattr(page_context, "url", "") or "")
    title = str(getattr(page_context, "title", "") or "")
    headings = [str(item) for item in (getattr(page_context, "headings", []) or [])[:20]]
    blocks = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in (getattr(page_context, "content_blocks", []) or [])]
    paragraphs = _paragraphs(page_context, blocks)
    sections = _sections(headings, paragraphs)
    metadata = {str(k): str(v)[:300] for k, v in dict(getattr(page_context, "metadata", {}) or {}).items() if v}
    interactions = [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in (getattr(page_context, "interactive_elements", []) or [])]
    forms = _forms(interactions)
    links = _links(interactions, blocks)
    pricing = [text for text in paragraphs if _contains_any(text, ("price", "pricing", "$", "free", "trial", "plan", "subscription", "credit"))][:8]
    contacts = [text for text in paragraphs if re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text) or _contains_any(text, ("contact", "phone", "email"))][:8]
    return PageReadArtifact(
        id=_id("read", url, title, str(started)),
        title=title,
        canonical_url=url,
        headings=headings,
        sections=sections,
        paragraphs=paragraphs[:40],
        metadata=metadata,
        tables=[],
        lists=_lists(paragraphs),
        forms=forms,
        pricing_blocks=pricing,
        contact_blocks=contacts,
        navigation_context=links[:25],
        timestamp_ms=started,
    )


def _paragraphs(page_context: Any, blocks: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for block in blocks:
        text = _compact(block.get("text", ""))
        if text:
            values.append(text)
    visible = str(getattr(page_context, "visible_text", "") or "")
    for line in visible.splitlines():
        text = _compact(line)
        if len(text) > 20:
            values.append(text)
    return _dedupe(values)


def _sections(headings: list[str], paragraphs: list[str]) -> list[dict[str, str]]:
    if not headings:
        return [{"heading": "Page", "text": " ".join(paragraphs[:3])[:900]}] if paragraphs else []
    sections: list[dict[str, str]] = []
    for index, heading in enumerate(headings[:12]):
        text = paragraphs[index] if index < len(paragraphs) else ""
        sections.append({"heading": heading[:160], "text": text[:900]})
    return sections


def _forms(interactions: list[dict[str, Any]]) -> list[dict[str, str]]:
    forms: list[dict[str, str]] = []
    for item in interactions:
        tag = str(item.get("type") or "").lower()
        input_type = str(item.get("input_type") or "").lower()
        if tag in {"input", "textarea", "select"} or input_type:
            forms.append({
                "selector": str(item.get("selector") or ""),
                "label": str(item.get("text") or item.get("aria_label") or item.get("placeholder") or "")[:180],
                "type": input_type or tag,
            })
    return forms[:50]


def _links(interactions: list[dict[str, Any]], blocks: list[dict[str, Any]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for item in [*interactions, *blocks]:
        href = str(item.get("href") or "")
        label = _compact(item.get("text") or item.get("aria_label") or item.get("accessibility_name") or href)
        if href:
            links.append({"label": label[:180], "url": href[:300]})
    return _dedupe_links(links)


def _lists(paragraphs: list[str]) -> list[list[str]]:
    candidates = [text for text in paragraphs if text.startswith(("-", "*")) or re.match(r"^\d+[\).]\s+", text)]
    return [candidates[:50]] if candidates else []


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _dedupe_links(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for value in values:
        key = value["url"].rstrip("/").lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _id(*parts: str) -> str:
    return "page_read_" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
