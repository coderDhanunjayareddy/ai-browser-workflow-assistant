from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal
from urllib.parse import urlparse

from app.knowledge_extraction.models import PageReadArtifact


@dataclass(frozen=True)
class CollectionPolicy:
    policy_id: str
    collection_type: Literal["directory", "search_results", "generic_list"]
    requested_count: int
    minimum_pages: int
    max_pages: int
    stop_conditions: list[str]
    dedupe_keys: list[str]
    pagination_modes: list[Literal["next_link", "numbered_pages", "infinite_scroll"]]
    item_selectors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CollectionItemCandidate:
    item_id: str
    name: str
    url: str
    source_url: str
    source_text: str
    item_key: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaginationCandidate:
    label: str
    url: str
    mode: Literal["next_link", "numbered_pages", "infinite_scroll"]
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CollectionPageState:
    policy: CollectionPolicy
    page_url: str
    item_candidates: list[CollectionItemCandidate]
    pagination_candidates: list[PaginationCandidate]
    stop_reason: str
    should_continue: bool
    next_url: str | None
    total_seen_count: int
    new_item_count: int
    pages_visited_count: int
    visited_pages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["policy"] = self.policy.to_dict()
        data["item_candidates"] = [item.to_dict() for item in self.item_candidates]
        data["pagination_candidates"] = [item.to_dict() for item in self.pagination_candidates]
        return data


def build_collection_policy(task: str) -> CollectionPolicy | None:
    text = str(task or "").lower()
    if not _looks_like_collection_task(text):
        return None
    collection_type: Literal["directory", "search_results", "generic_list"] = "generic_list"
    if any(term in text for term in ("directory", "listing", "entries", "contact", "companies")):
        collection_type = "directory"
    elif any(term in text for term in ("search results", "serp", "top results")):
        collection_type = "search_results"
    requested_count = _requested_count(text)
    minimum_pages = _minimum_pages(text)
    max_pages = min(max(2, minimum_pages, (requested_count + 9) // 10), 10)
    return CollectionPolicy(
        policy_id="collection_policy_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12],
        collection_type=collection_type,
        requested_count=requested_count,
        minimum_pages=minimum_pages,
        max_pages=max_pages,
        stop_conditions=["requested_count_reached", "max_pages_reached", "no_new_items", "no_next_page"],
        dedupe_keys=["normalized_url", "normalized_name", "source_text_hash"],
        pagination_modes=["next_link", "numbered_pages", "infinite_scroll"],
        item_selectors=["a[href]", "[role='listitem']", "article", ".card", ".listing", ".result"],
    )


def evaluate_collection_page(
    page: PageReadArtifact,
    policy: CollectionPolicy,
    *,
    seen_item_keys: set[str] | None = None,
    visited_pages: set[str] | None = None,
) -> CollectionPageState:
    seen = set(seen_item_keys or set())
    visited = {_normalize_url(url) for url in set(visited_pages or set()) if _normalize_url(url)}
    current_url = _normalize_url(page.canonical_url)
    visited_with_current = {url for url in [*visited, current_url] if url}
    items = _item_candidates(page, policy)
    new_items = [item for item in items if item.item_key not in seen]
    pagination = _pagination_candidates(page)
    next_url = _next_url(pagination, visited_with_current)
    total_seen = len(seen | {item.item_key for item in items})
    pages_visited = len(visited_with_current)
    stop_reason = ""
    if total_seen >= policy.requested_count and pages_visited >= policy.minimum_pages:
        stop_reason = "requested_count_reached"
    elif pages_visited >= policy.max_pages:
        stop_reason = "max_pages_reached"
    elif not new_items and seen:
        stop_reason = "no_new_items"
    elif not next_url:
        stop_reason = "no_next_page"
    should_continue = not stop_reason and bool(next_url)
    return CollectionPageState(
        policy=policy,
        page_url=page.canonical_url,
        item_candidates=items,
        pagination_candidates=pagination,
        stop_reason=stop_reason,
        should_continue=should_continue,
        next_url=next_url,
        total_seen_count=total_seen,
        new_item_count=len(new_items),
        pages_visited_count=pages_visited,
        visited_pages=sorted(visited_with_current),
    )


def evaluate_collection_pages(task: str, pages: list[PageReadArtifact]) -> CollectionPageState | None:
    policy = build_collection_policy(task)
    if policy is None or not pages:
        return None
    seen: set[str] = set()
    visited: set[str] = set()
    state: CollectionPageState | None = None
    for page in pages:
        state = evaluate_collection_page(page, policy, seen_item_keys=seen, visited_pages=visited)
        visited.add(_normalize_url(page.canonical_url))
        seen.update(item.item_key for item in state.item_candidates)
    if state is None:
        return None
    if len(visited) >= policy.max_pages and state.total_seen_count < policy.requested_count:
        return CollectionPageState(
            policy=state.policy,
            page_url=state.page_url,
            item_candidates=state.item_candidates,
            pagination_candidates=state.pagination_candidates,
            stop_reason="max_pages_reached",
            should_continue=False,
            next_url=state.next_url,
            total_seen_count=state.total_seen_count,
            new_item_count=state.new_item_count,
            pages_visited_count=len(visited),
            visited_pages=sorted(visited),
        )
    return state


def _looks_like_collection_task(text: str) -> bool:
    explicit_collection = any(term in text for term in ("collect entries", "collect records", "collect ", "listings", "pagination", "next page", "infinite scroll"))
    paginated_source = any(term in text for term in ("multi-page", "multiple pages", "page directory", "directory entries"))
    return explicit_collection or paginated_source


def _requested_count(text: str) -> int:
    patterns = [
        r"\b(?:top|first|collect|extract)\s+(\d{1,3})\b",
        r"\b(\d{1,3})\s+(?:entries|records|listings|results)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return max(1, min(int(match.group(1)), 200))
    return 50


def _minimum_pages(text: str) -> int:
    patterns = [
        r"\bacross\s+at\s+least\s+(\d{1,2})\s+pages?\b",
        r"\bat\s+least\s+(\d{1,2})\s+pages?\b",
        r"\bacross\s+(\d{1,2})\s+pages?\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return max(1, min(int(match.group(1)), 10))
    return 1


def _item_candidates(page: PageReadArtifact, policy: CollectionPolicy) -> list[CollectionItemCandidate]:
    candidates: list[CollectionItemCandidate] = []
    for link in page.navigation_context:
        label = _compact(link.get("label", ""))
        url = _normalize_url(str(link.get("url") or ""))
        if not label or _is_pagination_label(label) or _is_utility_link(label, url):
            continue
        confidence = 0.78 if url else 0.62
        candidates.append(_candidate(label, url or page.canonical_url, page.canonical_url, label, confidence, {"source": "link"}))
    for paragraph in page.paragraphs:
        if policy.collection_type == "directory" and _looks_like_directory_item(paragraph):
            name = _directory_name(paragraph)
            candidates.append(_candidate(name, page.canonical_url, page.canonical_url, paragraph, 0.68, {"source": "paragraph"}))
        elif _looks_like_card_item(paragraph):
            name = _card_name(paragraph)
            candidates.append(_candidate(name, page.canonical_url, page.canonical_url, paragraph, 0.66, {"source": "paragraph_card"}))
    return sorted(_dedupe_candidates(candidates), key=_candidate_rank, reverse=True)[: policy.requested_count]


def _pagination_candidates(page: PageReadArtifact) -> list[PaginationCandidate]:
    candidates: list[PaginationCandidate] = []
    for link in page.navigation_context:
        label = _compact(link.get("label", ""))
        url = _normalize_url(str(link.get("url") or ""))
        if not url:
            continue
        lower = label.lower()
        if _is_next_label(lower):
            candidates.append(PaginationCandidate(label=label or "Next", url=url, mode="next_link", confidence=0.9, reason="next_label"))
        elif re.fullmatch(r"\d{1,3}", lower) or re.search(r"\bpage\s+\d{1,3}\b", lower):
            candidates.append(PaginationCandidate(label=label, url=url, mode="numbered_pages", confidence=0.72, reason="numbered_page_label"))
    if any("infinite scroll" in paragraph.lower() or "load more" in paragraph.lower() for paragraph in page.paragraphs):
        candidates.append(PaginationCandidate(label="Load more", url=page.canonical_url, mode="infinite_scroll", confidence=0.64, reason="load_more_text"))
    return _dedupe_pagination(candidates)


def _candidate(name: str, url: str, source_url: str, source_text: str, confidence: float, metadata: dict[str, Any]) -> CollectionItemCandidate:
    item_key = _item_key(name, url, source_text, source_url=source_url)
    return CollectionItemCandidate(
        item_id="collection_item_" + hashlib.sha1(item_key.encode("utf-8")).hexdigest()[:12],
        name=_compact(name)[:180],
        url=url,
        source_url=source_url,
        source_text=_compact(source_text)[:320],
        item_key=item_key,
        confidence=round(confidence, 3),
        metadata=metadata,
    )


def _next_url(candidates: list[PaginationCandidate], visited: set[str]) -> str | None:
    for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
        normalized = _normalize_url(candidate.url)
        if normalized and normalized not in visited:
            return candidate.url
    return None


def _item_key(name: str, url: str, source_text: str, *, source_url: str = "") -> str:
    normalized_url = _normalize_url(url)
    normalized_source_url = _normalize_url(source_url)
    normalized_name = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    if normalized_url and normalized_url != "/" and normalized_url != normalized_source_url:
        return f"url:{normalized_url}"
    if normalized_name:
        return f"name:{normalized_name}"
    return "text:" + hashlib.sha1(_compact(source_text).lower().encode("utf-8")).hexdigest()[:16]


def _normalize_url(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def _is_next_label(label: str) -> bool:
    compact = label.strip().lower()
    return compact in {"next", "next page", ">", ">>", "load more", "show more"} or "next" in compact


def _is_pagination_label(label: str) -> bool:
    lower = label.lower().strip()
    return _is_next_label(lower) or lower in {"previous", "prev", "<", "<<"} or bool(re.fullmatch(r"\d{1,3}", lower))


def _is_utility_link(label: str, url: str) -> bool:
    lower = f"{label} {url}".lower()
    return label.strip().lower() in {"(about)", "about"} or any(term in lower for term in ("privacy", "terms", "login", "sign in", "cookie", "help", "subscribe"))


def _looks_like_directory_item(text: str) -> bool:
    lower = text.lower()
    return bool(re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text)) or any(term in lower for term in ("phone", "contact", "address", "website"))


def _looks_like_card_item(text: str) -> bool:
    compact = _compact(text)
    lower = compact.lower()
    return (
        len(compact) >= 40
        and (
            " by " in lower
            or "tags:" in lower
            or bool(re.search(r"[.!?]\s+[A-Z][A-Za-z .'-]{2,80}$", compact))
        )
    )


def _directory_name(text: str) -> str:
    compact = _compact(text)
    parts = re.split(r"\b(?:contact|phone|email|address|website)\b|[|:]", compact, maxsplit=1, flags=re.IGNORECASE)
    return parts[0].strip(" -")[:180] or compact[:180]


def _card_name(text: str) -> str:
    compact = _compact(text)
    if " by " in compact.lower():
        return re.split(r"\s+by\s+", compact, maxsplit=1, flags=re.IGNORECASE)[0].strip(" \"'")[:180]
    if "tags:" in compact.lower():
        return re.split(r"\btags:\b", compact, maxsplit=1, flags=re.IGNORECASE)[0].strip(" \"'")[:180]
    return compact[:180]


def _dedupe_candidates(candidates: list[CollectionItemCandidate]) -> list[CollectionItemCandidate]:
    by_key: dict[str, CollectionItemCandidate] = {}
    for candidate in candidates:
        existing = by_key.get(candidate.item_key)
        if existing is None or candidate.confidence >= existing.confidence:
            by_key[candidate.item_key] = candidate
    return list(by_key.values())


def _candidate_rank(candidate: CollectionItemCandidate) -> float:
    source = str(candidate.metadata.get("source") or "")
    source_bonus = 0.08 if source == "paragraph_card" else 0.0
    return candidate.confidence + source_bonus


def _dedupe_pagination(candidates: list[PaginationCandidate]) -> list[PaginationCandidate]:
    by_url: dict[str, PaginationCandidate] = {}
    for candidate in candidates:
        key = _normalize_url(candidate.url)
        existing = by_url.get(key)
        if existing is None or candidate.confidence >= existing.confidence:
            by_url[key] = candidate
    return list(by_url.values())


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()
