"""
DuckDuckGoProvider: web search using DuckDuckGo's Instant Answer API.

Endpoint: https://api.duckduckgo.com/?q={q}&format=json&no_html=1&skip_disambig=1
No API key required. Returns Wikipedia abstracts and related topics.
Timeout: 4 seconds. Falls back gracefully to empty list on any error.

Credibility: 0.8 for Wikipedia abstract, 0.7 for related topics.
"""
from __future__ import annotations

import uuid
import logging
from urllib.parse import quote_plus

import httpx

from app.research.models import ResearchSource, SourceType
from app.research.providers.base import SearchProvider

logger = logging.getLogger(__name__)

_DDG_URL = "https://api.duckduckgo.com/"
_TIMEOUT = 4.0
_MAX_SNIPPET = 600
_MAX_RELATED = 4


class DuckDuckGoProvider(SearchProvider):
    """
    Queries DuckDuckGo's zero-click Instant Answer API for a search query.
    Returns up to max_results sources.

    Source quality:
    - AbstractText present → Wikipedia article (credibility=0.8)
    - RelatedTopics      → related DuckDuckGo topic snippets (credibility=0.7)
    """

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        try:
            return self._fetch(query, max_results)
        except Exception as exc:
            logger.warning("DuckDuckGoProvider.search failed for %r: %s", query, exc)
            return []

    def _fetch(self, query: str, max_results: int) -> list[ResearchSource]:
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.get(_DDG_URL, params=params)
        response.raise_for_status()
        data = response.json()
        return self._parse(data, max_results)

    def _parse(self, data: dict, max_results: int) -> list[ResearchSource]:
        sources: list[ResearchSource] = []

        abstract = (data.get("AbstractText") or "").strip()
        abstract_url = (data.get("AbstractURL") or "").strip()
        abstract_source = (data.get("AbstractSource") or "DuckDuckGo").strip()
        heading = (data.get("Heading") or "").strip()

        if abstract and len(sources) < max_results:
            sources.append(ResearchSource(
                source_id=str(uuid.uuid4()),
                title=heading or abstract_source,
                url=abstract_url,
                source_type=SourceType.web,
                snippet=abstract[:_MAX_SNIPPET],
                credibility_score=0.8,
            ))

        # Related topics
        related = data.get("RelatedTopics") or []
        for item in related[:_MAX_RELATED]:
            if len(sources) >= max_results:
                break
            if not isinstance(item, dict):
                continue
            text = (item.get("Text") or "").strip()
            url = (item.get("FirstURL") or "").strip()
            if not text:
                continue
            title = text.split(" - ")[0][:80] if " - " in text else text[:80]
            sources.append(ResearchSource(
                source_id=str(uuid.uuid4()),
                title=title,
                url=url,
                source_type=SourceType.web,
                snippet=text[:_MAX_SNIPPET],
                credibility_score=0.7,
            ))

        return sources
