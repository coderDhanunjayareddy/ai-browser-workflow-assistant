from __future__ import annotations

from collections import deque
from typing import Any

from app.browser_intelligence.models import BrowserMemorySnapshot, BrowserStateModel, SemanticPageModel


class BrowserMemory:
    def __init__(self, max_pages: int = 12) -> None:
        self.max_pages = max_pages
        self._pages: dict[str, deque[dict[str, Any]]] = {}
        self._recent_elements: dict[str, deque[dict[str, Any]]] = {}
        self._recent_results: dict[str, deque[dict[str, Any]]] = {}
        self._recent_tabs: dict[str, deque[dict[str, Any]]] = {}

    def remember(self, scope_id: str, page_model: SemanticPageModel, state: BrowserStateModel) -> BrowserMemorySnapshot:
        pages = self._pages.setdefault(scope_id, deque(maxlen=self.max_pages))
        if not pages or pages[-1].get("url") != page_model.url:
            pages.append({
                "url": page_model.url,
                "title": page_model.title,
                "page_type": page_model.classification.page_type,
                "adapter": page_model.adapter,
            })

        elements = self._recent_elements.setdefault(scope_id, deque(maxlen=20))
        for element in page_model.elements[:5]:
            elements.append({
                "element_id": element.element_id,
                "kind": element.kind,
                "label": element.label,
                "selector_id": element.selector_id,
                "selector": element.selector,
            })

        results = self._recent_results.setdefault(scope_id, deque(maxlen=20))
        for result in page_model.search_results[:10]:
            if not any(item.get("url") == result.url for item in results):
                results.append(result.to_dict())

        tabs = self._recent_tabs.setdefault(scope_id, deque(maxlen=20))
        for tab in state.open_tabs:
            if tab and not any(item.get("id") == tab.get("id") for item in tabs):
                tabs.append(tab)

        previous_pages = list(pages)
        navigation_chain = [str(page.get("url", "")) for page in previous_pages]
        redirects = [
            {"from": navigation_chain[i - 1], "to": navigation_chain[i]}
            for i in range(1, len(navigation_chain))
            if _same_host(navigation_chain[i - 1], navigation_chain[i])
        ]
        login_transitions = [
            {"from": previous_pages[i - 1]["url"], "to": previous_pages[i]["url"]}
            for i in range(1, len(previous_pages))
            if previous_pages[i - 1].get("page_type") == "login"
        ]
        checkpoints = [
            {"url": page_model.url, "page_type": page_model.classification.page_type, "result_count": len(page_model.search_results)}
        ]
        return BrowserMemorySnapshot(
            previous_pages=previous_pages[-self.max_pages:],
            navigation_chain=navigation_chain[-self.max_pages:],
            redirects=redirects[-5:],
            login_transitions=login_transitions[-5:],
            workflow_checkpoints=checkpoints,
            recently_interacted_elements=list(elements)[-10:],
            recent_search_results=list(results)[-10:],
            recently_opened_tabs=list(tabs)[-10:],
        )


def _same_host(left: str, right: str) -> bool:
    from urllib.parse import urlparse

    return urlparse(left).netloc == urlparse(right).netloc
