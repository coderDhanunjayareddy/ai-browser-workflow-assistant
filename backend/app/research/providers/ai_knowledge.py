"""
AIKnowledgeProvider: LLM-based fallback when web sources are insufficient.

Fires only when DDG returns < 2 sources. Generates synthetic knowledge
sources grounded in the model's training data. credibility_score=0.5
to signal these are model-generated, not authoritative web citations.
"""
from __future__ import annotations

import uuid
import json
import logging
from typing import Any

from app.research.models import ResearchSource, SourceType
from app.research.providers.base import SearchProvider

logger = logging.getLogger(__name__)

_CREDIBILITY = 0.5
_MAX_SNIPPET = 600


_SYSTEM = "You are a knowledge retrieval assistant. Return only valid JSON."

_USER_TMPL = (
    "Query: {query}\n\n"
    "Return a JSON array of up to 3 objects, each with:\n"
    '  "title": short title (5-10 words)\n'
    '  "snippet": concise factual paragraph (2-4 sentences)\n\n'
    "Only output the JSON array. No other text."
)


def _call_llm(query: str) -> list[dict[str, str]]:
    """Calls the configured AI provider via generate_text. Inline import avoids circular deps."""
    from app.services.ai_service import generate_text  # local import

    raw = generate_text(_SYSTEM, _USER_TMPL.format(query=query))
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        import re
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


class AIKnowledgeProvider(SearchProvider):
    """
    LLM-backed fallback provider. Activated when web search returns < 2 results.
    Sources are tagged source_type=ai_knowledge and credibility_score=0.5.
    """

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        try:
            items = _call_llm(query)
        except Exception as exc:
            logger.warning("AIKnowledgeProvider failed for %r: %s", query, exc)
            return []

        sources: list[ResearchSource] = []
        for item in items[:max_results]:
            if not isinstance(item, dict):
                continue
            snippet = (item.get("snippet") or "").strip()
            title = (item.get("title") or "AI Knowledge").strip()
            if not snippet:
                continue
            sources.append(ResearchSource(
                source_id=str(uuid.uuid4()),
                title=title,
                url="",
                source_type=SourceType.ai_knowledge,
                snippet=snippet[:_MAX_SNIPPET],
                credibility_score=_CREDIBILITY,
            ))
        return sources
