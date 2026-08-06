from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from app.knowledge_extraction.models import PageReadArtifact


def read_page(page_context: Any) -> PageReadArtifact:
    started = int(time.time() * 1000)
    url = str(_read(page_context, "url", "") or "")
    title = str(_read(page_context, "title", "") or "")
    headings = [str(item) for item in _as_list(_read(page_context, "headings"))[:20]]
    blocks = [_to_dict(item) for item in _as_list(_read(page_context, "content_blocks"))]
    paragraphs = _paragraphs(page_context, blocks)
    sections = _sections(headings, paragraphs)
    metadata = {str(k): str(v)[:300] for k, v in dict(_read(page_context, "metadata", {}) or {}).items() if v}
    interactions = [_to_dict(item) for item in _as_list(_read(page_context, "interactive_elements"))]
    forms = _forms(interactions)
    links = _links(interactions, blocks)
    pricing = [text for text in paragraphs if _contains_any(text, ("price", "pricing", "$", "free", "trial", "plan", "subscription", "credit"))][:8]
    pricing_plans = _pricing_plans(headings, paragraphs)
    documentation_sections = _documentation_sections(url, title, headings, paragraphs)
    job_postings = _job_postings(url, title, headings, paragraphs, links)
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
        pricing_plans=pricing_plans,
        documentation_sections=documentation_sections,
        job_postings=job_postings,
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
    visible = str(_read(page_context, "visible_text", "") or "")
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


def _pricing_plans(headings: list[str], paragraphs: list[str]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    plan_names = ("free", "starter", "pro", "professional", "team", "business", "enterprise", "scale", "growth", "standard", "hobby", "pay as you go")
    for index, paragraph in enumerate(paragraphs[:40]):
        lower = paragraph.lower()
        if not _contains_any(lower, ("$", "free", "trial", "month", "/mo", "year", "/yr", "credits", "plan", "subscription")):
            continue
        heading = headings[index] if index < len(headings) else ""
        plan_name = _plan_name_from_text(heading) or _plan_name_from_text(paragraph)
        price = _price_from_text(paragraph)
        billing_period = _billing_period(paragraph)
        features = _features_from_text(paragraph)
        if plan_name or price or any(name in lower for name in plan_names):
            candidates.append({
                "name": plan_name or "Plan",
                "price": price,
                "billing_period": billing_period,
                "features": features,
                "source_text": paragraph[:500],
            })
    return _dedupe_plans(candidates)[:12]


def _documentation_sections(url: str, title: str, headings: list[str], paragraphs: list[str]) -> list[dict[str, str]]:
    text = f"{url} {title} {' '.join(headings[:8])}".lower()
    doc_like = any(term in text for term in ("docs", "documentation", "quickstart", "api reference", "developer", "sdk"))
    candidates: list[dict[str, str]] = []
    for index, paragraph in enumerate(paragraphs[:40]):
        heading = headings[index] if index < len(headings) else _doc_heading_from_text(paragraph)
        combined = f"{heading} {paragraph}"
        lower = combined.lower()
        if not doc_like and not _contains_any(lower, ("install", "quickstart", "sdk", "api key", "browser", "automation", "playwright", "python", "javascript", "typescript")):
            continue
        section_type = _documentation_section_type(combined)
        if section_type == "general" and not doc_like:
            continue
        candidates.append({
            "heading": heading or section_type.title(),
            "section_type": section_type,
            "text": paragraph[:700],
            "languages": ", ".join(_languages_from_text(combined)),
            "setup_requirement": _setup_requirement_from_text(combined),
            "browser_control": _browser_control_from_text(combined),
        })
    return _dedupe_doc_sections(candidates)[:16]


def _job_postings(url: str, title: str, headings: list[str], paragraphs: list[str], links: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    page_job_like = _contains_any(f"{url} {title} {' '.join(headings[:6])}", ("job", "career", "careers", "opening", "position", "role"))
    for index, paragraph in enumerate(paragraphs[:60]):
        combined = f"{headings[index] if index < len(headings) else ''} {paragraph}"
        lower = combined.lower()
        if not page_job_like and not _contains_any(lower, _JOB_SIGNALS):
            continue
        if not _contains_any(lower, _JOB_ROLE_SIGNALS) and not _contains_any(lower, ("apply", "posted", "experience", "full-time", "part-time", "hybrid", "remote")):
            continue
        apply_url = _job_apply_url(links, paragraph) or _job_apply_url(links, title)
        candidates.append({
            "title": _job_title_from_text(paragraph) or _job_title_from_text(combined) or _job_title_from_text(title),
            "company": _job_company_from_text(combined) or _company_from_title(title),
            "location": _job_location_from_text(combined),
            "experience": _job_experience_from_text(combined),
            "posted_date": _job_posted_date_from_text(combined),
            "employment_type": _employment_type_from_text(combined),
            "salary": _salary_from_text(combined),
            "apply_url": apply_url or url,
            "source_text": paragraph[:700],
        })
    if not candidates and page_job_like:
        text = " ".join([title, *headings[:4], *paragraphs[:6]])
        candidates.append({
            "title": _job_title_from_text(text) or title,
            "company": _job_company_from_text(text) or _company_from_title(title),
            "location": _job_location_from_text(text),
            "experience": _job_experience_from_text(text),
            "posted_date": _job_posted_date_from_text(text),
            "employment_type": _employment_type_from_text(text),
            "salary": _salary_from_text(text),
            "apply_url": _job_apply_url(links, text) or url,
            "source_text": text[:700],
        })
    return _dedupe_job_postings(candidates)[:20]


def _lists(paragraphs: list[str]) -> list[list[str]]:
    candidates = [text for text in paragraphs if text.startswith(("-", "*")) or re.match(r"^\d+[\).]\s+", text)]
    return [candidates[:50]] if candidates else []


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def _documentation_section_type(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ("install", "setup", "quickstart", "api key", "npm ", "pip ", "pnpm ", "npx ")):
        return "setup"
    if any(term in lower for term in ("python", "javascript", "typescript", "java", "go", "ruby", "sdk")):
        return "languages"
    if any(term in lower for term in ("browser", "automation", "control", "navigate", "click", "page.")):
        return "browser_control"
    if any(term in lower for term in ("use case", "workflow", "automate", "scrape", "testing", "extract")):
        return "use_case"
    return "general"


def _doc_heading_from_text(text: str) -> str:
    match = re.search(r"\b(Quickstart|Installation|Setup|SDKs?|Supported Languages|Browser Control|API Reference|Use Cases?)\b", str(text or ""), flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _languages_from_text(text: str) -> list[str]:
    labels = {
        "python": "Python",
        "javascript": "JavaScript",
        "typescript": "TypeScript",
        "node.js": "Node.js",
        "node": "Node.js",
        "java": "Java",
        "go": "Go",
        "ruby": "Ruby",
        "c#": "C#",
    }
    lower = str(text or "").lower()
    values: list[str] = []
    for needle, label in labels.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lower) and label not in values:
            values.append(label)
    return values


def _setup_requirement_from_text(text: str) -> str:
    match = re.search(r"(?:npm|pnpm|yarn|pip|uv|npx)\s+(?:install|add|exec)?\s*[A-Za-z0-9@/_\-.]*|(?:requires?|set)\s+(?:an?\s+)?(?:api key|environment variable|browser|chromium)[^.]*", str(text or ""), flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _browser_control_from_text(text: str) -> str:
    return _sentence_containing(text, "browser") or _sentence_containing(text, "automation") or _sentence_containing(text, "control")


_JOB_SIGNALS = (
    "job",
    "jobs",
    "career",
    "careers",
    "opening",
    "position",
    "role",
    "apply",
    "posted",
    "experience",
)

_JOB_ROLE_SIGNALS = (
    "developer",
    "engineer",
    "software",
    "full stack",
    "frontend",
    "backend",
    "java",
    "python",
    "javascript",
    "data scientist",
    "product manager",
    "designer",
    "analyst",
    "qa",
)


def _job_title_from_text(text: str) -> str:
    patterns = (
        r"\b(?:(?:Senior|Junior|Lead|Principal|Staff|Entry Level|Associate)\s+)?(?:(?:Full Stack|Frontend|Front End|Backend|Back End|Software|QA|Data)\s+)?(?:(?:Java|Python|JavaScript|React|Node\.?js)\s+)?(?:Developer|Engineer|Tester|Analyst|Scientist)\b",
        r"\b(?:Product Manager|UX Designer|UI Designer|DevOps Engineer|Site Reliability Engineer)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, str(text or ""), flags=re.IGNORECASE)
        if match:
            return match.group(0).strip(" -|")
    return ""


def _company_from_title(title: str) -> str:
    parts = [part.strip() for part in re.split(r"\s[-|]\s| at ", str(title or ""), flags=re.IGNORECASE) if part.strip()]
    if len(parts) >= 2:
        return parts[-1][:120]
    cleaned = re.sub(r"\b(?:careers?|jobs?|openings?|hiring)\b", "", str(title or ""), flags=re.IGNORECASE)
    return _compact(cleaned)[:120]


def _job_company_from_text(text: str) -> str:
    match = re.search(r"\bat\s+([A-Z][A-Za-z0-9&.,' -]{1,80}?)(?:[.;|,]|\s+-\s+|\s+Location\b|\s+Hyderabad\b|\s+Remote\b|$)", str(text or ""))
    return _compact(match.group(1)).strip(" .,-") if match else ""


def _job_location_from_text(text: str) -> str:
    match = re.search(r"\b(?:Location|Work location|Job location)\s*[:\-]\s*([^.;|]+)", str(text or ""), flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"\b(Hyderabad|Bengaluru|Bangalore|Mumbai|Pune|Chennai|Delhi|Gurugram|Noida|Remote|Hybrid|On-site|Onsite)\b(?:,\s*[A-Za-z ]+)?", str(text or ""), flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _job_experience_from_text(text: str) -> str:
    match = re.search(r"\b(?:Experience|Exp\.?|Years?)\s*[:\-]?\s*(?:required\s*)?(\d+\s*(?:\+|-\s*\d+)?\s*(?:years?|yrs?)[^.;&|]*)", str(text or ""), flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"\b(?:Entry level|Fresher|Internship)\b", str(text or ""), flags=re.IGNORECASE)
    if match:
        return match.group(0).strip()
    match = re.search(r"\b(?:Associate|Junior|Senior)\b", str(text or ""), flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _job_posted_date_from_text(text: str) -> str:
    match = re.search(r"\b(?:Posted|Date posted)\s*[:\-]?\s*(today|yesterday|\d+\s+days?\s+ago|\d+\s+weeks?\s+ago|past week|[A-Za-z]+\s+\d{1,2},?\s+\d{4})", str(text or ""), flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _employment_type_from_text(text: str) -> str:
    match = re.search(r"\b(Full-time|Part-time|Contract|Internship|Temporary|Permanent|Remote|Hybrid|On-site|Onsite)\b", str(text or ""), flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _salary_from_text(text: str) -> str:
    match = re.search(r"(?:[$â‚¬Â£â‚¹]\s?\d[\d,]*(?:\s*-\s*[$â‚¬Â£â‚¹]?\s?\d[\d,]*)?|\b\d+\s*(?:LPA|lakhs?|k)\b)", str(text or ""), flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _job_apply_url(links: list[dict[str, str]], text: str) -> str:
    text_lower = str(text or "").lower()
    direct_apply: list[dict[str, str]] = []
    preferred: list[dict[str, str]] = []
    for link in links:
        label = str(link.get("label") or "").lower()
        url = str(link.get("url") or "")
        lower_url = url.lower()
        if not url:
            continue
        if "apply" in label or "application" in label or "apply" in lower_url or "application" in lower_url:
            direct_apply.append(link)
        elif any(term in label or term in lower_url for term in ("job", "career", "lever.co", "greenhouse.io", "workdayjobs")):
            preferred.append(link)
    for link in direct_apply:
        label = str(link.get("label") or "").lower()
        if not label or label in text_lower or "apply" in label:
            return str(link.get("url") or "")
    for link in preferred:
        label = str(link.get("label") or "").lower()
        if label and label in text_lower:
            return str(link.get("url") or "")
    return str(preferred[0].get("url") or "") if preferred else ""


def _dedupe_job_postings(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for value in values:
        key = "|".join([
            value.get("title", "").lower(),
            value.get("company", "").lower(),
            value.get("location", "").lower(),
            value.get("apply_url", "").rstrip("/").lower(),
            value.get("source_text", "")[:100].lower(),
        ])
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _dedupe_doc_sections(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for value in values:
        key = "|".join([value.get("section_type", ""), value.get("heading", "").lower(), value.get("text", "")[:100].lower()])
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _plan_name_from_text(text: str) -> str:
    match = re.search(r"\b(Pay As You Go|Free|Starter|Hobby|Standard|Pro|Professional|Team|Business|Enterprise|Scaleup|Scale|Growth)\b", str(text or ""), flags=re.IGNORECASE)
    return match.group(0) if match else ""


def _price_from_text(text: str) -> str:
    match = re.search(r"(?:USD\s*)?[$€£₹]\s?\d[\d,]*(?:\.\d+)?(?:\s*/\s?(?:mo|month|yr|year))?|\b\d+\s+credits\b", str(text or ""), flags=re.IGNORECASE)
    if match:
        return match.group(0)
    if re.search(r"\bfree\b|\$0\b", str(text or ""), flags=re.IGNORECASE):
        return "$0"
    return ""


def _billing_period(text: str) -> str:
    lower = str(text or "").lower()
    if "month" in lower or "/mo" in lower:
        return "monthly"
    if "year" in lower or "/yr" in lower or "annual" in lower:
        return "annual"
    if "credit" in lower:
        return "usage"
    return "unknown"


def _features_from_text(text: str) -> str:
    parts = []
    for term in ("seat", "user", "credit", "request", "completion", "chat", "support", "integration", "repository", "code", "workspace", "security"):
        sentence = _sentence_containing(text, term)
        if sentence and sentence not in parts:
            parts.append(sentence)
    return "; ".join(parts[:3])


def _sentence_containing(text: str, term: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+|\s{2,}", str(text or "")):
        if term in sentence.lower():
            return sentence.strip()[:220]
    return ""


def _dedupe_plans(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for value in values:
        key = "|".join([value.get("name", "").lower(), value.get("price", "").lower(), value.get("source_text", "")[:80].lower()])
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


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


def _read(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}
