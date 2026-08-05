from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urlparse

from app.knowledge_extraction.collection_policy import build_collection_policy, evaluate_collection_page
from app.knowledge_extraction.models import ExtractionRecord, FieldEvidence, PageReadArtifact


def required_fields_for_task(task: str) -> list[str]:
    text = task.lower()
    explicit = re.findall(r"(?m)^\s*-\s*([A-Za-z][A-Za-z /_-]{1,40})", task)
    if explicit:
        return [_normalize_field(item) for item in explicit[:12]]
    if "job" in text:
        return ["title", "company", "location", "experience", "apply_url"]
    if "documentation" in text or "docs" in text:
        return ["languages", "use_case", "browser_control", "setup_requirement", "url"]
    if "contact" in text or "directory" in text:
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


def extract_records(page: PageReadArtifact, task: str, phase: str | None, *, required_fields: list[str] | None = None) -> list[ExtractionRecord]:
    fields = list(required_fields or required_fields_for_task(task))
    extraction_type = extraction_type_for_task(task)
    if extraction_type == "research" and _is_search_results_page(page):
        return []
    policy = build_collection_policy(task)
    if policy is not None and policy.collection_type == "directory":
        collection_records = _collection_item_records(page, task, phase, fields, extraction_type)
        if collection_records:
            return collection_records
    field_evidence = {field: _evidence_for_field(field, page) for field in fields}
    values = {field: evidence.value for field, evidence in field_evidence.items()}
    entity_type, entity = _typed_entity(extraction_type, values, page)
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
        field_evidence=field_evidence,
        entity_type=entity_type,  # type: ignore[arg-type]
        entity=entity,
    )
    return [record]


def _collection_item_records(
    page: PageReadArtifact,
    task: str,
    phase: str | None,
    fields: list[str],
    extraction_type: str,
) -> list[ExtractionRecord]:
    policy = build_collection_policy(task)
    if policy is None:
        return []
    state = evaluate_collection_page(page, policy)
    now = int(time.time() * 1000)
    records: list[ExtractionRecord] = []
    for item in state.item_candidates:
        field_evidence = {field: _collection_field_evidence(field, item, page) for field in fields}
        values = {field: evidence.value for field, evidence in field_evidence.items()}
        entity = {
            "name": values.get("name") or values.get("title") or item.name,
            "category": values.get("category") or "",
            "city": values.get("city") or "",
            "website": values.get("website") or item.url,
            "email": values.get("email") or "",
            "phone": values.get("phone") or "",
            "source_url": item.source_url,
            "item_key": item.item_key,
        }
        records.append(
            ExtractionRecord(
                id=_record_id("collection_item", item.item_key, values),
                source_page=page.canonical_url,
                producing_action="collect_page_items",
                producing_phase=phase or "EXTRACT",
                extraction_type=extraction_type,
                fields=values,
                confidence=round(max(0.55, item.confidence), 3),
                validation={},
                timestamp_ms=now,
                field_evidence=field_evidence,
                entity_type="directory_entry",
                entity=entity,
            )
        )
    return records


def _collection_field_evidence(field: str, item: object, page: PageReadArtifact) -> FieldEvidence:
    key = field.lower().replace(" ", "_")
    name = str(getattr(item, "name", "") or "")
    url = str(getattr(item, "url", "") or "")
    source_text = str(getattr(item, "source_text", "") or "")
    source_url = str(getattr(item, "source_url", "") or page.canonical_url)
    value = ""
    confidence = 0.55
    if key in {"name", "title", "company", "tool"}:
        value = name
        confidence = 0.82
    elif key in {"website", "url", "source_url", "apply_url"}:
        value = url or source_url
        confidence = 0.86
    elif key in {"quote", "quote_text", "text"}:
        value = _quote_text(source_text) or name
        confidence = 0.82 if value else 0.55
    elif key == "author":
        value = _quote_author(source_text) or "Not mentioned"
        confidence = 0.82 if value != "Not mentioned" else 0.55
    elif key == "tags":
        value = _quote_tags(source_text) or "Not mentioned"
        confidence = 0.76 if value != "Not mentioned" else 0.55
    elif key == "email":
        match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", source_text)
        value = match.group(0) if match else "Not mentioned"
        confidence = 0.84 if match else 0.55
    elif key == "phone":
        match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", source_text)
        value = match.group(0) if match else "Not mentioned"
        confidence = 0.78 if match else 0.55
    elif key in {"category", "city", "location"}:
        value = _sentence_containing(source_text, (key.replace("_", " "),)) or "Not mentioned"
    else:
        value = _sentence_containing(source_text, (key.replace("_", " "),)) or "Not mentioned"
    evidence = FieldEvidence(
        field=field,
        value=_clip(value),
        source_url=source_url,
        source_text=_clip(source_text, 320),
        source_kind="collection_item",
        confidence=round(confidence, 3),
        missing_reason="" if value != "Not mentioned" else f"No {field} found in collection item.",
    )
    return evidence


def _value_for_field(field: str, page: PageReadArtifact) -> str:
    return _evidence_for_field(field, page).value


def _evidence_for_field(field: str, page: PageReadArtifact) -> FieldEvidence:
    key = field.lower().replace(" ", "_")
    text = " ".join(page.paragraphs[:8])
    if key in {"url", "apply_url", "website", "location"} and key != "location":
        return _field_evidence(field, page.canonical_url, page, "url", page.canonical_url, 0.98)
    if key in {"tool", "product", "title", "name", "company"}:
        value = page.title or (page.headings[0] if page.headings else "")
        return _field_evidence(field, value, page, "title" if page.title else "heading", value, 0.84 if value else 0.0, "No title or heading found.")
    if key in {"purpose", "summary", "use_case", "main_use_case"}:
        value, source_kind = _first_non_empty_with_source(page.paragraphs, page.sections)
        return _field_evidence(field, value, page, source_kind, value, 0.72 if value else 0.0, "No descriptive paragraph found.")
    if key in {"pricing", "price", "paid_plan_starting_price", "free_plan"}:
        value = page.pricing_blocks[0] if page.pricing_blocks else _sentence_containing(text, ("price", "free", "trial", "plan", "$"))
        return _field_evidence_or_missing(field, value, page, "pricing_block" if page.pricing_blocks else "paragraph", "No pricing mention found in visible page text.")
    if key in {"limitation", "limitations"}:
        value = _sentence_containing(text, ("limitation", "limited", "lack", "without", "requires", "cannot", "but "))
        return _field_evidence_or_missing(field, value, page, "paragraph", "No limitation mention found in visible page text.")
    if key in {"email"}:
        match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)
        value = match.group(0) if match else ""
        return _field_evidence(field, value, page, "contact_block", _sentence_containing(text, (value,)) if value else "", 0.85 if value else 0.0, "No email address found.")
    if key in {"phone"}:
        match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", text)
        value = match.group(0) if match else ""
        return _field_evidence(field, value, page, "contact_block", _sentence_containing(text, (value,)) if value else "", 0.78 if value else 0.0, "No phone number found.")
    if key in {"field"}:
        value = page.forms[0]["label"] if page.forms else ""
        return _field_evidence(field, value, page, "form", str(page.forms[0]) if page.forms else "", 0.75 if value else 0.0, "No form field found.")
    if key in {"validation", "errors", "status"}:
        return _sentence_evidence(field, page, text, ("valid", "error", "accepted", "status", "complete"))
    if key in {"languages", "sdks"}:
        return _sentence_evidence(field, page, text, ("python", "javascript", "typescript", "java", "go", "ruby", "sdk"))
    if key in {"setup_requirement", "requirements"}:
        return _sentence_evidence(field, page, text, ("install", "setup", "require", "api key", "npm", "pip"))
    if key in {"browser_control"}:
        return _sentence_evidence(field, page, text, ("browser", "automation", "control"))
    if key in {"city", "category", "experience", "filename", "share_link"}:
        return _sentence_evidence(field, page, text, (key.replace("_", " "),))
    return _sentence_evidence(field, page, text, (key.replace("_", " "),))


def _first_non_empty(paragraphs: list[str], sections: list[dict[str, str]]) -> str:
    value, _source_kind = _first_non_empty_with_source(paragraphs, sections)
    return value


def _first_non_empty_with_source(paragraphs: list[str], sections: list[dict[str, str]]) -> tuple[str, str]:
    for paragraph in paragraphs:
        if len(paragraph) > 30:
            return _clip(paragraph), "paragraph"
    for section in sections:
        if section.get("text"):
            return _clip(section["text"]), "section"
    return "", "missing"


def _sentence_containing(text: str, terms: tuple[str, ...]) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if any(term in lower for term in terms):
            return _clip(sentence)
    return ""


def _clip(value: str, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _sentence_evidence(field: str, page: PageReadArtifact, text: str, terms: tuple[str, ...]) -> FieldEvidence:
    value = _sentence_containing(text, terms)
    return _field_evidence(field, value, page, "paragraph", value, 0.68 if value else 0.0, f"No visible text found for {field}.")


def _field_evidence_or_missing(field: str, value: str, page: PageReadArtifact, source_kind: str, missing_reason: str) -> FieldEvidence:
    if value:
        return _field_evidence(field, value, page, source_kind, value, 0.74)
    return _field_evidence(field, "Not mentioned", page, "missing", "", 0.55, missing_reason)


def _field_evidence(
    field: str,
    value: str,
    page: PageReadArtifact,
    source_kind: str,
    source_text: str,
    confidence: float,
    missing_reason: str = "",
) -> FieldEvidence:
    clipped_value = _clip(value)
    return FieldEvidence(
        field=field,
        value=clipped_value,
        source_url=page.canonical_url,
        source_text=_clip(source_text, 320) if source_text else "",
        source_kind=source_kind,  # type: ignore[arg-type]
        confidence=round(confidence, 3),
        missing_reason=missing_reason if not clipped_value or clipped_value == "Not mentioned" else "",
    )


def _quote_text(text: str) -> str:
    compact = _clip(text, 500)
    match = re.search(r"[\"“](.+?)[\"”]\s+by\s+", compact)
    if match:
        return _clip(match.group(1))
    if " by " in compact.lower():
        return _clip(re.split(r"\s+by\s+", compact, maxsplit=1, flags=re.IGNORECASE)[0].strip(" \"'“”"))
    return ""


def _quote_author(text: str) -> str:
    compact = _clip(text, 500)
    match = re.search(r"\s+by\s+(.+?)(?:\s+Tags:|$)", compact, flags=re.IGNORECASE)
    return _clip(match.group(1).strip()) if match else ""


def _quote_tags(text: str) -> str:
    compact = _clip(text, 500)
    match = re.search(r"\bTags:\s*(.+)$", compact, flags=re.IGNORECASE)
    if not match:
        return ""
    tags = [tag.strip(" ,") for tag in re.split(r",|\s{2,}", match.group(1)) if tag.strip(" ,")]
    return ", ".join(tags) if tags else _clip(match.group(1))


def _confidence(values: dict[str, str]) -> float:
    if not values:
        return 0.0
    filled = sum(1 for value in values.values() if value)
    return round(0.35 + 0.6 * (filled / len(values)), 3)


def _typed_entity(extraction_type: str, values: dict[str, str], page: PageReadArtifact) -> tuple[str, dict[str, object]]:
    text = " ".join([page.title, *page.headings, *page.paragraphs[:8]]).lower()
    if extraction_type == "job" or _looks_like_job(text):
        return "job_posting", _job_entity(values, page)
    if extraction_type == "documentation" or _looks_like_documentation(text, page.canonical_url):
        return "documentation_page", _documentation_entity(values, page)
    if extraction_type == "contact" or _looks_like_directory(text, page):
        return "directory_entry", _directory_entity(values, page)
    if extraction_type == "form":
        return "form_result", _form_entity(values, page)
    if extraction_type == "upload":
        return "file_result", _file_entity(values, page)
    if _looks_like_pricing(text, page):
        return "pricing_plan", _pricing_entity(values, page)
    if extraction_type == "research":
        return "research_source", _research_entity(values, page)
    return "generic", {"title": page.title, "url": page.canonical_url}


def _pricing_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    price_text = values.get("pricing") or values.get("price") or (page.pricing_blocks[0] if page.pricing_blocks else "")
    return {
        "plan_name": _plan_name(page, price_text),
        "price_text": price_text,
        "billing_period": _billing_period(price_text),
        "free_tier": "free" in price_text.lower(),
        "source_url": page.canonical_url,
    }


def _documentation_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    return {
        "title": page.title,
        "url": page.canonical_url,
        "section_headings": page.headings[:8],
        "setup_requirement": values.get("setup_requirement") or values.get("requirements") or "",
        "browser_control": values.get("browser_control") or "",
        "languages": values.get("languages") or values.get("sdks") or "",
        "official_source_hint": _official_docs_hint(page.canonical_url),
    }


def _job_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    return {
        "title": values.get("title") or page.title,
        "company": values.get("company") or _company_from_title(page.title),
        "location": values.get("location") or "",
        "experience": values.get("experience") or "",
        "apply_url": values.get("apply_url") or page.canonical_url,
        "source_url": page.canonical_url,
    }


def _directory_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    return {
        "name": values.get("name") or values.get("title") or page.title,
        "category": values.get("category") or "",
        "city": values.get("city") or "",
        "website": values.get("website") or page.canonical_url,
        "email": values.get("email") or "",
        "phone": values.get("phone") or "",
        "source_url": page.canonical_url,
    }


def _form_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    return {
        "field": values.get("field") or "",
        "validation": values.get("validation") or "",
        "errors": values.get("errors") or "",
        "form_count": len(page.forms),
        "source_url": page.canonical_url,
    }


def _file_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    return {
        "filename": values.get("filename") or "",
        "status": values.get("status") or "",
        "location": values.get("location") or page.canonical_url,
        "share_link": values.get("share_link") or "",
        "source_url": page.canonical_url,
    }


def _research_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    return {
        "name": values.get("tool") or values.get("title") or page.title,
        "purpose": values.get("purpose") or values.get("summary") or "",
        "pricing": values.get("pricing") or "",
        "limitation": values.get("limitation") or "",
        "source_url": values.get("url") or page.canonical_url,
    }


def _looks_like_pricing(text: str, page: PageReadArtifact) -> bool:
    return bool(page.pricing_blocks) or any(term in text for term in ("pricing", "plan", "per month", "free tier", "$"))


def _looks_like_documentation(text: str, url: str) -> bool:
    lower_url = url.lower()
    return any(term in lower_url for term in ("/docs", "docs.", "developer.", "developers.")) or any(
        term in text for term in ("documentation", "quickstart", "api reference", "sdk", "install")
    )


def _looks_like_job(text: str) -> bool:
    return any(term in text for term in ("job", "career", "apply now", "remote", "salary", "experience"))


def _looks_like_directory(text: str, page: PageReadArtifact) -> bool:
    return bool(page.contact_blocks) or any(term in text for term in ("directory", "phone", "email", "contact", "address"))


def _plan_name(page: PageReadArtifact, price_text: str) -> str:
    for heading in page.headings:
        if any(term in heading.lower() for term in ("free", "pro", "team", "enterprise", "starter", "business")):
            return heading
    match = re.search(r"\b(Free|Starter|Pro|Team|Business|Enterprise)\b", price_text, flags=re.IGNORECASE)
    return match.group(0) if match else page.title


def _billing_period(price_text: str) -> str:
    lower = price_text.lower()
    if "month" in lower or "/mo" in lower:
        return "monthly"
    if "year" in lower or "/yr" in lower or "annual" in lower:
        return "annual"
    return "unknown"


def _official_docs_hint(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(term in host for term in ("docs.", "developer.", "developers.")) or "/docs" in url.lower()


def _company_from_title(title: str) -> str:
    parts = [part.strip() for part in re.split(r"[-|]", title or "") if part.strip()]
    return parts[-1] if len(parts) > 1 else ""


def _normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _record_id(extraction_type: str, source: str, values: dict[str, str]) -> str:
    raw = f"{extraction_type}|{source}|{values}"
    return "extraction_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _is_search_results_page(page: PageReadArtifact) -> bool:
    parsed = urlparse(page.canonical_url)
    host = parsed.netloc.lower()
    if host in {"www.google.com", "google.com"} and parsed.path.startswith("/search"):
        return True
    title = (page.title or "").lower()
    return "google search" in title or title.endswith("- google search")
