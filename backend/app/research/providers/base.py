"""
SearchProvider: abstract base class for all research source providers.

Future providers plug in by implementing search().
Provider registry: page_context, duckduckgo, ai_knowledge (V3.5)
Extension points:  youtube, reddit, documentation, pdf (V4.0)
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.research.models import ResearchSource


class SearchProvider(ABC):
    """
    Single contract for all source providers.

    search() returns a list of ResearchSource objects with:
      - source_id: unique per source
      - title: human-readable title
      - url: canonical URL (empty string for ai_knowledge sources)
      - source_type: web | page_context | ai_knowledge
      - snippet: 1-3 sentence extract
      - credibility_score: 0.0-1.0

    Callers deduplicate by URL before passing to the synthesizer.
    """

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        """Run a single query and return up to max_results sources."""
        ...

    @property
    def name(self) -> str:
        return self.__class__.__name__
