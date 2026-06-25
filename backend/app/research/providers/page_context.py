"""
PageContextProvider: uses the current browser page as a research source.

Always credible (score=0.9) because it is the authoritative page the user is viewing.
Returns a single source representing the full visible page content.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.research.models import ResearchSource, SourceType
from app.research.providers.base import SearchProvider

if TYPE_CHECKING:
    from app.schemas.assist import ReadView

_MAX_SNIPPET_CHARS = 1500


def _build_snippet(read_view: "ReadView") -> str:
    parts = []
    if read_view.visible_text:
        parts.append(read_view.visible_text[:_MAX_SNIPPET_CHARS])
    return " ".join(parts).strip()


class PageContextProvider(SearchProvider):
    """Wraps the current page's ReadView as a high-credibility research source."""

    def search(self, query: str, max_results: int = 5) -> list[ResearchSource]:
        raise NotImplementedError("PageContextProvider requires read_view — use search_page() instead.")

    def search_page(self, query: str, read_view: "ReadView") -> list[ResearchSource]:
        """
        Return a single ResearchSource from the current page.
        The query is unused because page content is always included in full.
        """
        snippet = _build_snippet(read_view)
        if not snippet:
            return []

        return [
            ResearchSource(
                source_id=str(uuid.uuid4()),
                title=read_view.title or "Current Page",
                url=read_view.url or "",
                source_type=SourceType.page_context,
                snippet=snippet,
                credibility_score=0.9,
            )
        ]
