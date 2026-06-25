import json
import re

from app.schemas.assist import StructuredSummary
from app.services import ai_service

_SYSTEM_PROMPT = """You are a web page summarizer. Given page content, return a structured JSON summary.

Return ONLY this JSON structure, no markdown fences, no explanation:
{
  "tldr": "One clear sentence describing what this page is about",
  "key_points": ["Important point 1", "Important point 2", "Important point 3", "Important point 4"],
  "entities": [{"label": "Price", "value": "$99"}],
  "available_actions": ["What the user can do on this page"]
}

Rules:
- tldr: one concise sentence starting with the subject directly — never open with "This page",
  "The page", "This article", "The article", "This post", "The post", or any similar
  page-referencing phrase; state the subject itself
- key_points: 4 to 5 specific points drawn directly from the page content; use 3 only when
  the page has very little content; never collapse distinct facts into one point just to stay
  at the minimum
- entities: notable prices, dates, names, or figures found on the page; empty list if none;
  for news or blog pages always extract author name and publish date when present, labelled
  "Author" and "Published"; for product pages always extract price, star rating, and review
  count when present, labelled "Price", "Rating", "Reviews"
- available_actions: 2 to 4 specific actions a user can take directly on this page right now
  (clicking a button, submitting a form, navigating a link that exists on this page) — never
  list research goals, follow-up reading suggestions, or off-page tasks; never include
  "Read the article" or "Read the post" if the user is already on the page
- Answer only from provided content, never invent information
- Return valid JSON only"""


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_summary(raw: str) -> StructuredSummary:
    cleaned = _strip_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start != -1 and end > start:
            try:
                data = json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                return StructuredSummary(
                    tldr=cleaned[:300] if cleaned else "Could not parse summary.",
                    key_points=[],
                    entities=[],
                    available_actions=[],
                )
        else:
            return StructuredSummary(
                tldr=cleaned[:300] if cleaned else "Could not parse summary.",
                key_points=[],
                entities=[],
                available_actions=[],
            )

    return StructuredSummary(
        tldr=str(data.get("tldr", "")).strip(),
        key_points=[str(p).strip() for p in data.get("key_points", []) if p],
        entities=[e for e in data.get("entities", []) if isinstance(e, dict)],
        available_actions=[str(a).strip() for a in data.get("available_actions", []) if a],
    )


def summarize(read_view_str: str, selection_scope: str = "page") -> StructuredSummary:
    scope_note = (
        "Summarize the SELECTED TEXT provided below."
        if selection_scope == "selection"
        else "Summarize the full page content provided below."
    )
    user_message = f"{scope_note}\n\nPAGE CONTENT:\n{read_view_str}"
    raw = ai_service.generate_text(_SYSTEM_PROMPT, user_message)
    return _parse_summary(raw)
