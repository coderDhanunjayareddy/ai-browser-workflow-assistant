from __future__ import annotations

import hashlib
import re
import time
from urllib.parse import urlparse

from app.knowledge_extraction.collection_policy import build_collection_policy, evaluate_collection_page
from app.knowledge_extraction.models import ExtractionRecord, FieldEvidence, PageReadArtifact


def required_fields_for_task(task: str) -> list[str]:
    text = task.lower()
    explicit = _explicit_bullet_fields(task)
    if explicit:
        return explicit
    columns = _fields_after_label(task, "columns?")
    if columns:
        return columns
    if "best practices" in text or "testing practices" in text or "checklist" in text:
        return ["practice", "category", "source_url"]
    if any(term in text for term in ("job", "jobs", "career", "careers", "opening", "openings")):
        return ["title", "company", "location", "posted_date", "experience", "apply_url"]
    if "documentation" in text or "docs" in text:
        return ["languages", "use_case", "browser_control", "setup_requirement", "url"]
    if "contact" in text or "directory" in text:
        return ["name", "category", "city", "website", "email", "phone"]
    if "upload" in text:
        return ["filename", "status", "location", "share_link"]
    if "form" in text:
        return ["field", "value", "validation", "errors"]
    if "purpose" in text or "limitation" in text:
        return ["tool", "purpose", "pricing", "limitation", "url"]
    if "pricing" in text:
        return ["tool", "free_plan", "paid_plan_starting_price", "trial_available", "feature", "url"]
    capture = _capture_fields(task)
    if capture:
        return capture
    if "pricing" in text or "comparison" in text or "summar" in text:
        return ["tool", "purpose", "pricing", "limitation", "url"]
    return ["title", "summary", "url"]


def extraction_type_for_task(task: str) -> str:
    text = task.lower()
    if any(term in text for term in ("job", "jobs", "career", "careers", "opening", "openings")):
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
    key = _canonical_field(field.lower().replace(" ", "_"))
    text = _page_text(page)
    content_text = " ".join([page.title, *page.headings, *page.paragraphs[:30]])
    if key in {"title", "company", "location", "posted_date", "experience", "apply_url", "employment_type", "salary"}:
        job = _job_field_evidence(field, key, page)
        if job:
            return job
    if key in {"url", "apply_url", "website", "location"} and key != "location":
        if key == "apply_url":
            apply_url = _link_url(page, ("apply", "application"))
            return _field_evidence(field, apply_url or page.canonical_url, page, "url", apply_url or page.canonical_url, 0.9 if apply_url else 0.72)
        if key == "website":
            website = _link_url(page, ("website", "visit site", "official site", "homepage"))
            return _field_evidence_or_missing(field, website, page, "url", "No website link found in observed page context.")
        return _field_evidence(field, page.canonical_url, page, "url", page.canonical_url, 0.98)
    if extraction_type_for_page(page) == "research" and key in {"tool", "product", "title", "name", "purpose", "summary", "pricing", "price", "limitation", "limitations"}:
        research = _research_field_evidence(field, key, page)
        if research:
            return research
    if key in {"tool", "product", "title", "name", "company"}:
        value = _company_from_title(page.title) if key == "company" else page.title or (page.headings[0] if page.headings else "")
        return _field_evidence(field, value, page, "title" if page.title else "heading", value, 0.84 if value else 0.0, "No title or heading found.")
    if key in {"purpose", "summary", "use_case", "main_use_case"}:
        value, source_kind = _first_non_empty_with_source(page.paragraphs, page.sections)
        return _field_evidence(field, value, page, source_kind, value, 0.72 if value else 0.0, "No descriptive paragraph found.")
    if key in {"pricing", "price", "paid_plan_starting_price", "free_plan"}:
        plan_value = _pricing_plan_value(key, page)
        if plan_value:
            return _field_evidence(field, plan_value, page, "pricing_plan", plan_value, 0.86)
        terms = _terms_for_field(key)
        value = _best_sentence(page.pricing_blocks, terms) or _sentence_containing(content_text, terms)
        return _field_evidence_or_missing(field, value, page, "pricing_block" if page.pricing_blocks else "paragraph", "No pricing mention found in visible page text.")
    if key in {"trial_available", "trial"}:
        trial = _trial_value(page)
        if trial:
            return _field_evidence(field, trial, page, "pricing_plan" if page.pricing_plans else "paragraph", trial, 0.82)
        value = _sentence_containing(text, ("trial", "free trial", "credit", "sandbox", "demo"))
        if value:
            return _field_evidence(field, value, page, "paragraph", value, 0.74)
        return _field_evidence(field, "Not mentioned", page, "missing", "", 0.55, "No trial availability mention found.")
    if key in {"feature", "features"}:
        feature = _pricing_feature(page)
        if feature:
            return _field_evidence(field, feature, page, "pricing_plan", feature, 0.8)
        value = _sentence_containing(content_text, ("feature", "features")) or _sentence_containing(
            content_text,
            ("includes", "supports", "offers", "automation", "integration", "workflow"),
        )
        return _field_evidence_or_missing(field, value, page, "paragraph", "No product feature mention found.")
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
    if key in {"languages", "sdks", "supported_languages", "setup_requirement", "requirements", "browser_control"}:
        doc = _documentation_field_evidence(field, key, page)
        if doc:
            return doc
        if key in {"languages", "sdks", "supported_languages"}:
            return _sentence_evidence(field, page, text, ("python", "javascript", "typescript", "java", "go", "ruby", "sdk"))
        if key in {"setup_requirement", "requirements"}:
            return _sentence_evidence(field, page, text, ("install", "setup", "require", "api key", "npm", "pip"))
        return _sentence_evidence(field, page, text, ("browser", "automation", "control"))
    if key in {"posted_date", "date_posted"}:
        return _sentence_evidence(field, page, text, ("posted", "past week", "today", "yesterday", "days ago", "week ago"))
    if key in {"practice"}:
        return _sentence_evidence(field, page, text, ("should", "recommend", "best practice", "use ", "avoid", "ensure"))
    if key in {"category"} and ("best practice" in text or "testing" in text):
        return _sentence_evidence(field, page, text, ("reliability", "observability", "recovery", "safety"))
    if key in {"city", "category", "experience", "filename", "share_link", "location"}:
        return _sentence_evidence(field, page, text, _terms_for_field(key))
    return _sentence_evidence(field, page, text, (key.replace("_", " "),))


def _first_non_empty(paragraphs: list[str], sections: list[dict[str, str]]) -> str:
    value, _source_kind = _first_non_empty_with_source(paragraphs, sections)
    return value


def _page_text(page: PageReadArtifact) -> str:
    navigation = " ".join(f"{item.get('label', '')} {item.get('url', '')}" for item in page.navigation_context[:25])
    forms = " ".join(f"{item.get('label', '')} {item.get('type', '')}" for item in page.forms[:20])
    metadata = " ".join(page.metadata.values())
    jobs = " ".join(str(item.get("source_text") or "") for item in page.job_postings[:8])
    return " ".join([page.title, *page.headings, metadata, *page.paragraphs[:30], jobs, navigation, forms])


def _first_non_empty_with_source(paragraphs: list[str], sections: list[dict[str, str]]) -> tuple[str, str]:
    for paragraph in paragraphs:
        if len(paragraph) > 30:
            return _clip(paragraph), "paragraph"
    for section in sections:
        if section.get("text"):
            return _clip(section["text"]), "section"
    return "", "missing"


def _documentation_field_evidence(field: str, key: str, page: PageReadArtifact) -> FieldEvidence | None:
    if not page.documentation_sections:
        return None
    if key in {"languages", "sdks", "supported_languages"}:
        values = []
        sources = []
        for section in page.documentation_sections:
            languages = str(section.get("languages") or "")
            if languages:
                values.extend([item.strip() for item in languages.split(",") if item.strip()])
                sources.append(str(section.get("text") or ""))
        deduped = _dedupe_text(values)
        if deduped:
            source = next((item for item in sources if item), "")
            return _field_evidence(field, ", ".join(deduped), page, "documentation_section", source, 0.88)
    if key in {"setup_requirement", "requirements"}:
        section = _doc_section(page, "setup")
        value = str(section.get("setup_requirement") or "") if section else ""
        if not value and section:
            value = _sentence_containing(str(section.get("text") or ""), ("install", "setup", "require", "api key", "npm", "pip"))
        if value:
            return _field_evidence(field, value, page, "documentation_section", str(section.get("text") or value), 0.86)
    if key == "browser_control":
        section = _doc_section(page, "browser_control") or _doc_section(page, "use_case")
        value = str(section.get("browser_control") or "") if section else ""
        if not value and section:
            value = _sentence_containing(str(section.get("text") or ""), ("browser", "automation", "control", "navigate", "click"))
        if value:
            return _field_evidence(field, value, page, "documentation_section", str(section.get("text") or value), 0.84)
    return None


def _job_field_evidence(field: str, key: str, page: PageReadArtifact) -> FieldEvidence | None:
    job = _primary_job(page)
    if not job:
        return None
    source = str(job.get("source_text") or "")
    value = str(job.get(key) or "")
    if key == "apply_url":
        value = str(job.get("apply_url") or "")
        source = value or source
    if key == "company" and not value:
        value = _company_from_title(page.title)
    if key == "title" and not value:
        value = page.title or (page.headings[0] if page.headings else "")
    if value:
        confidence = 0.9 if key in {"title", "apply_url"} else 0.84
        return _field_evidence(field, value, page, "job_posting", source or value, confidence)
    return None


def _primary_job(page: PageReadArtifact) -> dict[str, str] | None:
    if not page.job_postings:
        return None
    return max(page.job_postings, key=_job_candidate_score)


def _job_candidate_score(job: dict[str, str]) -> float:
    score = 0.0
    for field, weight in {
        "title": 0.25,
        "company": 0.12,
        "location": 0.14,
        "experience": 0.12,
        "posted_date": 0.1,
        "apply_url": 0.2,
        "employment_type": 0.04,
        "salary": 0.03,
    }.items():
        if str(job.get(field) or ""):
            score += weight
    return score


def _doc_section(page: PageReadArtifact, section_type: str) -> dict[str, str] | None:
    for section in page.documentation_sections:
        if section.get("section_type") == section_type:
            return section
    return None


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _sentence_containing(text: str, terms: tuple[str, ...]) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lower = sentence.lower()
        if any(term in lower for term in terms):
            return _clip(sentence)
    return ""


def _best_sentence(candidates: list[str], terms: tuple[str, ...]) -> str:
    for candidate in candidates:
        value = _sentence_containing(candidate, terms)
        if value:
            return value
    return candidates[0] if candidates else ""


def extraction_type_for_page(page: PageReadArtifact) -> str:
    text = " ".join([page.title, *page.headings, *page.paragraphs[:8]]).lower()
    if any(term in text for term in ("browser automation", "ai browser", "automation tool", "web scraper", "agentic")):
        return "research"
    return "generic"


def _research_field_evidence(field: str, key: str, page: PageReadArtifact) -> FieldEvidence | None:
    if key in {"tool", "product", "title", "name"}:
        value = _research_tool_name(page)
        return _field_evidence(field, value, page, "title", value, 0.86 if value else 0.0, "No product/tool name found.")
    if key in {"purpose", "summary"}:
        value = _research_purpose(page)
        return _field_evidence_or_missing(field, value, page, "paragraph", "No clear product purpose found.")
    if key in {"pricing", "price"}:
        value = _research_pricing(page)
        return _field_evidence(field, value or "Not mentioned", page, "pricing_block" if value else "missing", value, 0.82 if value else 0.55, "No clear pricing mention found.")
    if key in {"limitation", "limitations"}:
        value = _research_limitation(page)
        return _field_evidence(field, value or "Not mentioned", page, "paragraph" if value else "missing", value, 0.74 if value else 0.55, "No clear limitation mention found.")
    return None


def _research_tool_name(page: PageReadArtifact) -> str:
    host = urlparse(page.canonical_url).netloc.lower().removeprefix("www.")
    title = _clean_page_title(page.title)
    patterns = (
        r"\b(best\s+for\s+[^:]{1,60}:\s*)?([A-Z][A-Za-z0-9 ._-]{1,35})\s+(?:[-–—:]\s*)?(?:is|automates|offers|provides|helps|lets)\b",
        r"\b([A-Z][A-Za-z0-9 ._-]{1,35})\s+(?:browser automation|web scraper|ai agent|automation platform)\b",
    )
    source = " ".join([title, *page.headings[:8], *page.paragraphs[:8]])
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            value = match.group(match.lastindex or 1).strip(" -–—:")
            if _is_reasonable_tool_name(value):
                return _clip(value, 80)
    if title and not _looks_like_listicle_title(title):
        return _clip(title, 80)
    brand = host.split(".")[0].replace("-", " ").replace("_", " ").strip()
    return _clip(brand.title(), 80) if brand else _clip(title, 80)


def _research_purpose(page: PageReadArtifact) -> str:
    text = _clean_research_text(" ".join([*page.paragraphs[:16], *page.headings[:4]]))
    terms = ("automates", "automation", "browser", "scrape", "workflow", "testing", "agent", "extract")
    return _clean_research_text(_sentence_containing(text, terms))


def _research_pricing(page: PageReadArtifact) -> str:
    value = _pricing_plan_value("pricing", page)
    if value:
        return _clean_research_text(value)
    text = _clean_research_text(" ".join([*page.pricing_blocks, *page.paragraphs[:20]]))
    sentence = _sentence_containing(text, ("$", "free", "pricing", "plan", "/mo", "per month", "trial"))
    if not sentence:
        return ""
    if _noisy_research_sentence(sentence):
        return ""
    return _clean_research_text(sentence)


def _research_limitation(page: PageReadArtifact) -> str:
    section_text = [str(value) for section in page.sections[:4] for value in section.values()]
    text = _clean_research_text(" ".join([*page.paragraphs[:24], *section_text]))
    sentence = _sentence_containing(text, ("limitation", "limited", "requires", "cannot", "drawback", "downside", "but "))
    if not sentence or _noisy_research_sentence(sentence):
        return ""
    return _clean_research_text(sentence)


def _clean_page_title(title: str) -> str:
    value = re.sub(r"\s+", " ", str(title or "")).strip()
    value = re.sub(r"\s*\|\s*(.+)$", "", value) if len(value) > 90 else value
    value = re.sub(r"\s+[-–—]\s+(Google Search|Search|DuckDuckGo|Bing)$", "", value, flags=re.IGNORECASE)
    return value.strip()


def _looks_like_listicle_title(title: str) -> bool:
    return bool(re.search(r"\b(?:top|best|tools?|compared|ranked|tested|guide|reviews?)\b", title, flags=re.IGNORECASE))


def _is_reasonable_tool_name(value: str) -> bool:
    lower = value.lower()
    if len(value) < 2 or len(value) > 80:
        return False
    if any(term in lower for term in ("top ", "best ", "browser automation", "tools compared", "search")):
        return False
    return True


def _clean_research_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"(Only include results for this site|Redo search without this site|Block this site from all results|Share feedback about this site)", " ", text)
    return _clip(text)


def _noisy_research_sentence(value: str) -> bool:
    text = str(value or "")
    lower = text.lower()
    return (
        len(text) > 260
        or lower.count("free") > 2
        or lower.count("plan") > 3
        or "slack scraper" in lower
        or "product hunt" in lower
        or "trusted by" in lower and "$" not in lower
    )


def _link_url(page: PageReadArtifact, terms: tuple[str, ...]) -> str:
    for item in page.navigation_context:
        label = str(item.get("label") or "").lower()
        url = str(item.get("url") or "")
        if url and any(term in label or term in url.lower() for term in terms):
            return url
    return ""


def _terms_for_field(key: str) -> tuple[str, ...]:
    aliases: dict[str, tuple[str, ...]] = {
        "free_plan": ("free", "free plan", "starter", "$0"),
        "paid_plan_starting_price": ("starts", "starting", "per month", "/mo", "$", "paid", "pro plan"),
        "pricing": ("price", "pricing", "free", "trial", "plan", "$", "per month", "/mo"),
        "location": ("location", "remote", "hyderabad", "onsite", "on-site", "hybrid"),
        "city": ("city", "hyderabad", "bangalore", "mumbai", "delhi", "remote"),
        "category": ("category", "industry", "type", "reliability", "observability", "recovery", "safety"),
        "experience": ("experience", "years", "entry level", "associate", "senior", "junior"),
        "filename": ("file", "filename", "pdf", "image", "upload"),
        "share_link": ("share", "link", "url"),
    }
    return aliases.get(key, (key.replace("_", " "),))


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
    if _looks_like_pricing(text, page):
        return "pricing_plan", _pricing_entity(values, page)
    if extraction_type == "contact" or _looks_like_directory(text, page):
        return "directory_entry", _directory_entity(values, page)
    if extraction_type == "form":
        return "form_result", _form_entity(values, page)
    if extraction_type == "upload":
        return "file_result", _file_entity(values, page)
    if extraction_type == "research":
        return "research_source", _research_entity(values, page)
    return "generic", {"title": page.title, "url": page.canonical_url}


def _pricing_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    price_text = values.get("pricing") or values.get("price") or (page.pricing_blocks[0] if page.pricing_blocks else "")
    paid_plan = _paid_plan(page)
    free_plan = _free_plan(page)
    return {
        "plan_name": _plan_name(page, price_text),
        "price_text": price_text,
        "billing_period": _billing_period(price_text),
        "free_tier": bool(free_plan) or "free" in price_text.lower(),
        "free_plan": free_plan,
        "paid_plan_starting_price": _paid_plan_price(paid_plan) if paid_plan else values.get("paid_plan_starting_price", ""),
        "trial_available": values.get("trial_available") or _trial_value(page) or "Not mentioned",
        "feature": values.get("feature") or _pricing_feature(page),
        "plans": page.pricing_plans[:8],
        "source_url": page.canonical_url,
    }


def _documentation_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    return {
        "title": page.title,
        "url": page.canonical_url,
        "section_headings": page.headings[:8],
        "documentation_sections": page.documentation_sections[:8],
        "setup_requirement": values.get("setup_requirement") or values.get("requirements") or "",
        "browser_control": values.get("browser_control") or "",
        "languages": values.get("languages") or values.get("sdks") or "",
        "official_source_hint": _official_docs_hint(page.canonical_url),
        "official_source_score": _official_docs_score(page),
        "citation_url": page.canonical_url,
    }


def _job_entity(values: dict[str, str], page: PageReadArtifact) -> dict[str, object]:
    job = _primary_job(page) or {}
    return {
        "title": values.get("title") or job.get("title") or page.title,
        "company": values.get("company") or job.get("company") or _company_from_title(page.title),
        "location": values.get("location") or job.get("location") or "",
        "experience": values.get("experience") or job.get("experience") or "",
        "posted_date": values.get("posted_date") or job.get("posted_date") or "",
        "employment_type": values.get("employment_type") or job.get("employment_type") or "",
        "salary": values.get("salary") or job.get("salary") or "",
        "apply_url": values.get("apply_url") or job.get("apply_url") or page.canonical_url,
        "job_candidates": page.job_postings[:8],
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
    return any(term in text for term in ("job", "career", "opening", "apply now", "remote", "salary", "experience"))


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


def _pricing_plan_value(key: str, page: PageReadArtifact) -> str:
    if key == "free_plan":
        plan = _free_plan(page)
        if plan:
            return _plan_summary(plan)
    if key == "paid_plan_starting_price":
        plan = _paid_plan(page)
        if plan:
            return _plan_summary(plan)
    if key in {"pricing", "price"} and page.pricing_plans:
        summaries = [_plan_summary(plan) for plan in page.pricing_plans[:4] if _plan_summary(plan)]
        if summaries:
            return "; ".join(summaries)
    return ""


def _free_plan(page: PageReadArtifact) -> dict[str, str] | None:
    for plan in page.pricing_plans:
        text = " ".join([plan.get("name", ""), plan.get("price", ""), plan.get("source_text", "")]).lower()
        if "free" in text or "$0" in text:
            return plan
    return None


def _paid_plan(page: PageReadArtifact) -> dict[str, str] | None:
    paid = [
        plan for plan in page.pricing_plans
        if _paid_plan_price(plan) and not ("free" in " ".join([plan.get("name", ""), plan.get("price", "")]).lower() or plan.get("price") == "$0")
    ]
    if not paid:
        return None
    return sorted(paid, key=lambda plan: _price_amount(plan.get("price", "")) or 10**9)[0]


def _paid_plan_price(plan: dict[str, str]) -> str:
    price = str(plan.get("price") or "")
    if price and price != "$0":
        return price
    match = re.search(r"[$€£₹]\s?\d[\d,]*(?:\.\d+)?(?:\s*/\s?(?:mo|month|yr|year))?", str(plan.get("source_text") or ""), flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _price_amount(price: str) -> float | None:
    match = re.search(r"\d[\d,]*(?:\.\d+)?", price)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _plan_summary(plan: dict[str, str]) -> str:
    parts = [plan.get("name", ""), plan.get("price", ""), plan.get("billing_period", "")]
    features = plan.get("features", "")
    if features:
        parts.append(features)
    summary = " ".join(part for part in parts if part and part != "unknown")
    return _clip(summary or plan.get("source_text", ""))


def _trial_value(page: PageReadArtifact) -> str:
    text = " ".join([*page.pricing_blocks, *[plan.get("source_text", "") for plan in page.pricing_plans], *page.paragraphs[:20]])
    value = _sentence_containing(text, ("free trial", "trial", "demo"))
    return value


def _pricing_feature(page: PageReadArtifact) -> str:
    for plan in page.pricing_plans:
        feature = str(plan.get("features") or "")
        if feature:
            return _clip(feature)
    text = " ".join([*page.pricing_blocks, *page.paragraphs[:20]])
    return _sentence_containing(text, ("includes", "features", "support", "integration", "requests", "credits", "users"))


def _official_docs_hint(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(term in host for term in ("docs.", "developer.", "developers.")) or "/docs" in url.lower()


def _official_docs_score(page: PageReadArtifact) -> float:
    score = 0.0
    url = page.canonical_url.lower()
    host = urlparse(page.canonical_url).netloc.lower()
    if _official_docs_hint(page.canonical_url):
        score += 0.55
    if any(term in host for term in ("github.io", "readthedocs.io", "mintlify.app")):
        score += 0.2
    if page.documentation_sections:
        score += 0.2
    if any(term in url for term in ("quickstart", "reference", "api", "docs")):
        score += 0.05
    return round(min(score, 1.0), 3)


def _company_from_title(title: str) -> str:
    parts = [part.strip() for part in re.split(r"[-|]", title or "") if part.strip()]
    return parts[-1] if len(parts) > 1 else ""


def _normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _explicit_bullet_fields(task: str) -> list[str]:
    if not re.search(r"(?im)^\s*(extract|fields?|columns?)\s*:", task):
        return []
    fields = [
        _normalize_field(item)
        for item in re.findall(r"(?m)^\s*-\s*([A-Za-z][A-Za-z /_-]{1,40})", task)
        if item.strip()
    ]
    return [field for field in fields if field][:12]


def _fields_after_label(task: str, label: str) -> list[str]:
    match = re.search(rf"{label}\s*:\s*([^.\n]+)", task, flags=re.IGNORECASE)
    if not match:
        return []
    return _field_list(match.group(1))


def _capture_fields(task: str) -> list[str]:
    captures = re.findall(
        r"\b(?:capture|extract|collect)\s+(?:the\s+)?(.+?)(?:\.|\n| for each| and (?:return|whether|if)| then:|$)",
        task,
        flags=re.IGNORECASE,
    )
    fields: list[str] = []
    for capture in captures:
        fields.extend(_field_list(capture))
    normalized = [_canonical_field(field) for field in fields if field]
    deduped: list[str] = []
    for field in normalized:
        if field and field not in deduped:
            deduped.append(field)
    return deduped[:12]


def _field_list(value: str) -> list[str]:
    cleaned = re.sub(r"\b(?:whether|if|available|clearly mentioned|current|any|one)\b", "", value, flags=re.IGNORECASE)
    fields = [_normalize_field(item) for item in re.split(r",|;|\band\b", cleaned) if item.strip()]
    ignored = {"the", "result", "results", "details", "information", "first_10_relevant_jobs", "top_recommended_testing_practices"}
    return [field for field in fields if field and field not in ignored]


def _canonical_field(field: str) -> str:
    aliases = {
        "job_title": "title",
        "application_link": "apply_url",
        "application_url": "apply_url",
        "job_link": "apply_url",
        "job_url": "apply_url",
        "apply_link": "apply_url",
        "experience_needed": "experience",
        "experience_required": "experience",
        "date": "posted_date",
        "posted": "posted_date",
        "employment": "employment_type",
        "employment_type": "employment_type",
        "link": "url",
        "source_urls": "url",
        "source_url": "url",
        "contact_email": "email",
        "email_address": "email",
        "paid_plan_starting_price": "paid_plan_starting_price",
        "trial": "trial_available",
        "a_trial_is": "trial_available",
        "a_trial_is_available": "trial_available",
        "trial_is": "trial_available",
        "feature_that_is_on_the_pricing_or_product_page": "feature",
        "feature_that_is_clearly_mentioned_on_the_pricing_or_product_page": "feature",
        "feature": "feature",
        "supported_languages": "languages",
        "main_use_case": "use_case",
        "it_supports_browser_control": "browser_control",
        "supports_browser_control": "browser_control",
        "whether_it_supports_browser_control": "browser_control",
        "one_setup_requirement": "setup_requirement",
        "setup_requirement": "setup_requirement",
        "posted_date": "posted_date",
        "date_posted": "posted_date",
        "browser_control_from_documentation": "browser_control",
    }
    return aliases.get(field, field)


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
