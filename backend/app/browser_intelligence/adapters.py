from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from app.browser_intelligence.models import SearchResult, SemanticElement
from app.browser_intelligence.selector_engine import SelectorIntelligenceEngine, stable_id


_GOOGLE_HOSTS = {"www.google.com", "google.com"}
_BING_HOSTS = {"www.bing.com", "bing.com"}
_GOOGLE_BLOCKED_HOSTS = {
    "accounts.google.com",
    "maps.google.com",
    "news.google.com",
    "shopping.google.com",
    "support.google.com",
    "policies.google.com",
    "translate.google.com",
    "www.youtube.com",
    "youtube.com",
}
_SERP_EXCLUSION_TERMS = (
    "ai overview",
    "ai mode",
    "people also ask",
    "sponsored",
    "ad ",
    "ads ",
    "images",
    "videos",
    "shopping",
    "news",
    "maps",
    "related searches",
)


def _getattr(item: Any, name: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _normalize_url(raw: str, base_url: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if raw.startswith("/url?"):
        query = parse_qs(urlparse(raw).query)
        if query.get("q"):
            return str(query["q"][0])
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        if parsed.netloc.endswith("google.com") and parsed.path == "/url":
            query = parse_qs(parsed.query)
            if query.get("q"):
                return str(query["q"][0])
        return raw
    try:
        parsed_base = urlparse(base_url)
        if raw.startswith("/"):
            return f"{parsed_base.scheme}://{parsed_base.netloc}{raw}"
    except Exception:
        pass
    return raw


def _display_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    path = unquote(parsed.path or "").strip("/")
    return parsed.netloc + (f"/{path[:60]}" if path else "")


def _is_external_organic(url: str, *, engine_hosts: set[str]) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if not host:
        return False
    if host in {h.removeprefix("www.") for h in engine_hosts}:
        return False
    if host in {h.removeprefix("www.") for h in _GOOGLE_BLOCKED_HOSTS}:
        return False
    if parsed.path.startswith(("/search", "/preferences", "/advanced_search")):
        return False
    return True


def _looks_excluded(text: str) -> bool:
    lower = " ".join(text.lower().split())
    return any(term in lower for term in _SERP_EXCLUSION_TERMS)


@dataclass(frozen=True)
class AdapterResult:
    adapter_name: str
    semantic_elements: list[SemanticElement]
    search_results: list[SearchResult]
    metadata: dict[str, Any]


class SiteAdapter:
    name = "generic"

    def matches(self, page_context: Any) -> bool:
        return True

    def extract(self, page_context: Any, selectors: SelectorIntelligenceEngine) -> AdapterResult:
        elements: list[SemanticElement] = []
        selector_map = {candidate.selector: candidate for candidate in selectors.build_candidates(page_context)}
        seen: set[tuple[str, str, str | None]] = set()
        for index, element in enumerate(getattr(page_context, "interactive_elements", []) or []):
            if _getattr(element, "visible", True) is False:
                continue
            selector = str(_getattr(element, "selector", "") or "")
            label = str(_getattr(element, "text", "") or _getattr(element, "placeholder", "") or "").strip()
            kind = classify_element_kind(element)
            key = (kind, label[:80], selector)
            if key in seen:
                continue
            seen.add(key)
            candidate = selector_map.get(selector)
            elements.append(
                SemanticElement(
                    element_id=stable_id("el", f"{kind}|{label}|{selector}|{index}"),
                    kind=kind,
                    label=label,
                    selector_id=candidate.selector_id if candidate else None,
                    selector=selector or None,
                    role=_getattr(element, "role", None),
                    href=_getattr(element, "href", None),
                    visible=True,
                    confidence=candidate.confidence if candidate else 0.55,
                    metadata={
                        "input_type": _getattr(element, "input_type", None),
                        "placeholder": _getattr(element, "placeholder", None),
                    },
                )
            )
        return AdapterResult(self.name, elements, [], {"adapter_confidence": 0.5})


class GoogleSearchAdapter(SiteAdapter):
    name = "google_search"

    def matches(self, page_context: Any) -> bool:
        parsed = urlparse(str(getattr(page_context, "url", "") or ""))
        return parsed.netloc.lower() in _GOOGLE_HOSTS and parsed.path.startswith("/search")

    def extract(self, page_context: Any, selectors: SelectorIntelligenceEngine) -> AdapterResult:
        generic = super().extract(page_context, selectors)
        results = extract_search_results(page_context, engine_hosts=_GOOGLE_HOSTS, limit=10)
        result_elements = [
            SemanticElement(
                element_id=stable_id("result", result.url),
                kind="search_result",
                label=result.title,
                selector_id=result.selector_id,
                selector=result.open_selector,
                href=result.url,
                confidence=0.92,
                metadata={"rank": result.rank, "displayed_url": result.displayed_url},
            )
            for result in results
        ]
        return AdapterResult(
            self.name,
            result_elements + generic.semantic_elements,
            results,
            {
                "adapter_confidence": 0.94,
                "organic_result_count": len(results),
                "excluded_sections": list(_SERP_EXCLUSION_TERMS),
            },
        )

    def getOrganicResults(self, page_context: Any) -> list[SearchResult]:
        return extract_search_results(page_context, engine_hosts=_GOOGLE_HOSTS, limit=10)

    def openResult(self, page_context: Any, index: int) -> dict[str, Any]:
        results = self.getOrganicResults(page_context)
        if index < 1 or index > len(results):
            return {"ok": False, "reason": "result_index_out_of_range", "index": index}
        result = results[index - 1]
        return {
            "ok": True,
            "action_type": "open_new_tab",
            "value": result.url,
            "expected": {"tab_count_delta": 1, "new_tab_url": result.url},
            "result": result.to_dict(),
        }

    def findResult(self, page_context: Any, predicate: Callable[[SearchResult], bool]) -> SearchResult | None:
        return next((result for result in self.getOrganicResults(page_context) if predicate(result)), None)


class BingSearchAdapter(GoogleSearchAdapter):
    name = "bing_search"

    def matches(self, page_context: Any) -> bool:
        parsed = urlparse(str(getattr(page_context, "url", "") or ""))
        return parsed.netloc.lower() in _BING_HOSTS and parsed.path.startswith("/search")

    def getOrganicResults(self, page_context: Any) -> list[SearchResult]:
        return extract_search_results(page_context, engine_hosts=_BING_HOSTS, limit=10)


class LinkedInJobsAdapter(SiteAdapter):
    name = "linkedin_jobs"

    def matches(self, page_context: Any) -> bool:
        parsed = urlparse(str(getattr(page_context, "url", "") or ""))
        return "linkedin.com" in parsed.netloc.lower() and "/jobs" in parsed.path


class GitHubAdapter(SiteAdapter):
    name = "github"

    def matches(self, page_context: Any) -> bool:
        return "github.com" in urlparse(str(getattr(page_context, "url", "") or "")).netloc.lower()


class GmailAdapter(SiteAdapter):
    name = "gmail"

    def matches(self, page_context: Any) -> bool:
        parsed = urlparse(str(getattr(page_context, "url", "") or ""))
        return "mail.google.com" in parsed.netloc.lower()


class OutlookAdapter(SiteAdapter):
    name = "outlook"

    def matches(self, page_context: Any) -> bool:
        parsed = urlparse(str(getattr(page_context, "url", "") or ""))
        host = parsed.netloc.lower()
        return "outlook." in host or "office.com" in host and "mail" in parsed.path.lower()


class NotionAdapter(SiteAdapter):
    name = "notion"

    def matches(self, page_context: Any) -> bool:
        return "notion.so" in urlparse(str(getattr(page_context, "url", "") or "")).netloc.lower()


class JiraAdapter(SiteAdapter):
    name = "jira"

    def matches(self, page_context: Any) -> bool:
        url = str(getattr(page_context, "url", "") or "").lower()
        text = f"{getattr(page_context, 'title', '')} {getattr(page_context, 'visible_text', '')[:1000]}".lower()
        return "atlassian.net" in url and ("jira" in url or "issue" in text or "sprint" in text)


class ConfluenceAdapter(SiteAdapter):
    name = "confluence"

    def matches(self, page_context: Any) -> bool:
        url = str(getattr(page_context, "url", "") or "").lower()
        text = f"{getattr(page_context, 'title', '')} {getattr(page_context, 'visible_text', '')[:1000]}".lower()
        return "atlassian.net" in url and ("wiki" in url or "confluence" in text)


class DocumentationAdapter(SiteAdapter):
    name = "documentation"

    def matches(self, page_context: Any) -> bool:
        text = " ".join([
            str(getattr(page_context, "title", "") or ""),
            str(getattr(page_context, "visible_text", "") or "")[:1000],
        ]).lower()
        return any(term in text for term in ("documentation", "docs", "api reference", "quickstart"))


class ReactSpaAdapter(SiteAdapter):
    name = "generic_react_spa"

    def matches(self, page_context: Any) -> bool:
        metadata = getattr(page_context, "metadata", {}) or {}
        text = f"{metadata} {getattr(page_context, 'visible_text', '')[:1000]}".lower()
        return any(term in text for term in ("react", "__next", "vite", "root", "app"))


class DashboardAdapter(SiteAdapter):
    name = "generic_dashboard"

    def matches(self, page_context: Any) -> bool:
        text = f"{getattr(page_context, 'title', '')} {getattr(page_context, 'visible_text', '')[:1200]}".lower()
        return any(term in text for term in ("dashboard", "analytics", "overview", "metrics", "reports"))


class DataTableAdapter(SiteAdapter):
    name = "generic_data_table"

    def matches(self, page_context: Any) -> bool:
        elements = getattr(page_context, "interactive_elements", []) or []
        text = str(getattr(page_context, "visible_text", "") or "").lower()
        row_count = sum(1 for element in elements if str(_getattr(element, "role", "") or "").lower() == "row")
        return row_count >= 3 or any(term in text for term in ("rows per page", "sort by", "filter table", "export csv"))


def classify_element_kind(element: Any) -> str:
    tag = str(_getattr(element, "type", "") or "").lower()
    role = str(_getattr(element, "role", "") or "").lower()
    text = str(_getattr(element, "text", "") or "").lower()
    input_type = str(_getattr(element, "input_type", "") or "").lower()
    if tag in {"input", "textarea", "select"} or role in {"textbox", "searchbox", "combobox"}:
        return "input"
    if tag == "button" or role == "button" or input_type in {"button", "submit"}:
        return "button"
    if tag == "a":
        return "link"
    if role == "dialog":
        return "dialog"
    if role in {"menu", "menuitem"}:
        return "menu"
    if role == "tab":
        return "tab"
    if role in {"row", "listitem", "option"}:
        return "list"
    if role in {"grid", "table"} or tag == "table":
        return "table"
    if "search result" in text:
        return "search_result"
    return "widget"


def extract_search_results(page_context: Any, *, engine_hosts: set[str], limit: int) -> list[SearchResult]:
    candidates: list[tuple[int, SearchResult]] = []
    seen_urls: set[str] = set()
    all_blocks = list(getattr(page_context, "content_blocks", []) or [])
    all_elements = list(getattr(page_context, "interactive_elements", []) or [])
    page_url = str(getattr(page_context, "url", "") or "")

    for index, element in enumerate(all_elements):
        href = _normalize_url(str(_getattr(element, "href", "") or ""), page_url)
        selector = str(_getattr(element, "selector", "") or "")
        text = str(_getattr(element, "text", "") or "").strip()
        if not href and selector.startswith('a[href="'):
            href = _normalize_url(selector[len('a[href="'):-2], page_url)
        if not href or not _is_external_organic(href, engine_hosts=engine_hosts):
            continue
        block_text = _matching_block_text(text, selector, all_blocks)
        combined = f"{text} {block_text}"
        if _looks_excluded(combined):
            continue
        if href in seen_urls:
            continue
        seen_urls.add(href)
        title = text or _title_from_block(block_text) or _display_url(href)
        candidate_selector = selectors_id_for(selector) if selector else None
        candidates.append((
            index,
            SearchResult(
                rank=len(candidates) + 1,
                title=title[:160],
                description=_description_from_block(block_text, title),
                url=href,
                displayed_url=_display_url(href),
                open_selector=selector or None,
                selector_id=candidate_selector,
                metadata={"source": "interactive_anchor", "engine_hosts": sorted(engine_hosts)},
            ),
        ))

    # If the extension did not provide hrefs, fall back to content text with URL-shaped tokens.
    if not candidates:
        for index, block in enumerate(all_blocks):
            text = str(_getattr(block, "text", "") or "")
            if _looks_excluded(text):
                continue
            for raw_url in _extract_urls(text):
                href = _normalize_url(raw_url, page_url)
                if href in seen_urls or not _is_external_organic(href, engine_hosts=engine_hosts):
                    continue
                seen_urls.add(href)
                title = _title_from_block(text) or _display_url(href)
                candidates.append((
                    index,
                    SearchResult(
                        rank=len(candidates) + 1,
                        title=title[:160],
                        description=_description_from_block(text, title),
                        url=href,
                        displayed_url=_display_url(href),
                        open_selector=str(_getattr(block, "selector", "") or "") or None,
                        selector_id=None,
                        metadata={"source": "content_block_url", "engine_hosts": sorted(engine_hosts)},
                    ),
                ))

    ordered = [result for _, result in sorted(candidates, key=lambda row: row[0])[:limit]]
    return [
        SearchResult(
            rank=index + 1,
            title=result.title,
            description=result.description,
            url=result.url,
            displayed_url=result.displayed_url,
            open_selector=result.open_selector,
            selector_id=result.selector_id,
            metadata=result.metadata,
        )
        for index, result in enumerate(ordered)
    ]


def selectors_id_for(selector: str) -> str:
    return stable_id("sel", selector)


def _matching_block_text(title: str, selector: str, blocks: list[Any]) -> str:
    for block in blocks:
        text = str(_getattr(block, "text", "") or "")
        if title and title in text:
            return text
    return ""


def _title_from_block(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if lines:
        return lines[0]
    parts = [part.strip() for part in str(text or "").split("  ") if part.strip()]
    return parts[0] if parts else ""


def _description_from_block(text: str, title: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if title and cleaned.startswith(title):
        cleaned = cleaned[len(title):].strip(" -|")
    return cleaned[:260]


def _extract_urls(text: str) -> list[str]:
    import re

    return re.findall(r"https?://[^\s)>\"]+", text or "")


class AdapterRegistry:
    def __init__(self) -> None:
        self.adapters: list[SiteAdapter] = [
            GoogleSearchAdapter(),
            BingSearchAdapter(),
            LinkedInJobsAdapter(),
            GitHubAdapter(),
            GmailAdapter(),
            OutlookAdapter(),
            NotionAdapter(),
            JiraAdapter(),
            ConfluenceAdapter(),
            DocumentationAdapter(),
            DataTableAdapter(),
            DashboardAdapter(),
            ReactSpaAdapter(),
            SiteAdapter(),
        ]

    def select(self, page_context: Any) -> SiteAdapter:
        return next(adapter for adapter in self.adapters if adapter.matches(page_context))
