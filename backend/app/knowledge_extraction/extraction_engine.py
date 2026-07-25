from __future__ import annotations

import hashlib
import re
import time

from app.knowledge_extraction.models import ExtractionRecord, PageReadArtifact


def required_fields_for_task(task: str) -> list[str]:
    text = task.lower()
    explicit = re.findall(r"-\s*([A-Za-z][A-Za-z /_-]{1,40})", task)
    if explicit:
        return [_normalize_field(item) for item in explicit[:12]]
    if "job" in text:
        return ["title", "company", "location", "experience", "apply_url"]
    if "documentation" in text or "docs" in text:
        return ["languages", "use_case", "browser_control", "setup_requirement", "url"]
    if "contact" in text:
        return ["name", "category", "city", "website", "email", "phone"]
    if "upload" in text:
        return ["filename", "status", "location", "share_link"]
    if "form" in text:
        return ["field", "value", "validation", "errors"]
    if "pricing" in text or "comparison" in text or "summar" in text:
        return ["tool", "purpose", "pricing", "limitation", "url"]
    return ["title", "summary", "url"]


def extraction_type_for_task(task: str) -> str:
    text = task.lower()
    if "job" in text:
        return "job"
    if "documentation" in text or "docs" in text:
        return "documentation"
    if "contact" in text or "directory" in text:
        return "contact"
    if "upload" in text:
        return "upload"
    if "form" in text:
        return "form"
    if "pricing" in text or "tool" in text or "comparison" in text:
        return "research"
    return "generic"


def extract_records(page: PageReadArtifact, task: str, phase: str | None) -> list[ExtractionRecord]:
    fields = required_fields_for_task(task)
    extraction_type = extraction_type_for_task(task)
    values = {field: _value_for_field(field, page) for field in fields}
    confidence = _confidence(values)
    now = int(time.time() * 1000)
    record = ExtractionRecord(
        id=_record_id(extraction_type, page.canonical_url, values),
        source_page=page.canonical_url,
        producing_action="read_page",
        producing_phase=phase or "READ",
        extraction_type=extraction_type,
        fields=values,
        confidence=confidence,
        validation={},
        timestamp_ms=now,
    )
    return [record]


def _value_for_field(field: str, page: PageReadArtifact) -> str:
    key = field.lower().replace(" ", "_")
    text = " ".join(page.paragraphs[:8])
    if key in {"url", "apply_url", "website", "location"} and key != "location":
        return page.canonical_url
    if key in {"tool", "product", "title", "name", "company"}:
        return page.title or (page.headings[0] if page.headings else "")
    if key in {"purpose", "summary", "use_case", "main_use_case"}:
        return _first_non_empty(page.paragraphs, page.sections)
    if key in {"pricing", "price", "paid_plan_starting_price", "free_plan"}:
        return page.pricing_blocks[0] if page.pricing_blocks else _sentence_containing(text, ("price", "free", "trial", "plan", "$"))
    if key in {"limitation", "limitations"}:
        return _sentence_containing(text, ("limitation", "limited", "lack", "without", "requires", "cannot", "but "))
    if key in {"email"}:
        match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)
        return match.group(0) if match else ""
    if key in {"phone"}:
        match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
        return match.group(0) if match else ""
    if key in {"field"}:
        return page.forms[0]["label"] if page.forms else ""
    if key in {"validation", "errors", "status"}:
        return _sentence_containing(text, ("valid", "error", "accepted", "status", "complete"))
    if key in {"languages", "sdks"}:
        return _sentence_containing(text, ("python", "javascript", "typescript", "java", "go", "ruby", "sdk"))
    if key in {"setup_requirement", "requirements"}:
        return _sentence_containing(text, ("install", "setup", "require", "api key", "npm", "pip"))
    if key in {"browser_control"}:
        return _sentence_containing(text, ("browser", "automation", "control"))
    if key in {"city", "category", "experience", "filename", "share_link"}:
        return _sentence_containing(text, (key.replace("_", " "),))
    return _sentence_containing(text, (key.replace("_", " "),))


def _first_non_empty(paragraphs: list[str], sections: list[dict[str, str]]) -> str:
    for paragraph in paragraphs:
        if len(paragraph) > 30:
            return paragraph[:500]
    for section in sections:
        if section.get("text"):
            return section["text"][:500]
    return ""


def _sentence_containing(text: str, terms: tuple[str, ...]) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if any(term in lower for term in terms):
            return sentence[:500]
    return ""


def _confidence(values: dict[str, str]) -> float:
    if not values:
        return 0.0
    filled = sum(1 for value in values.values() if value)
    return round(0.35 + 0.6 * (filled / len(values)), 3)


def _normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _record_id(extraction_type: str, source: str, values: dict[str, str]) -> str:
    raw = f"{extraction_type}|{source}|{values}"
    return "extraction_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
