from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit, urlunsplit

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentExecutionEvidence
from app.intent_dispatcher.registry import IntentOwnerRegistration, register_intent_executor, register_intent_owner
from app.intent_providers.common import execution_result


def register() -> None:
    register_intent_owner(
        IntentOwnerRegistration(
            provider_id="browser_intelligence",
            capability="serp_collection",
            dispatch_target="browser_intelligence",
            reason="Browser Intelligence owns passive collection of observed search results.",
            matcher=lambda intent, _payload: intent in {"collect_search_results", "collect_serp_results"},
        )
    )
    register_intent_executor("browser_intelligence", execute)


def execute(context: ExecutionContext, directive: IntentDispatchDirective):
    search_results = _extract_search_results(context)
    registered_entities = _register_search_result_entities(context, search_results)
    source_policy = _source_collection_policy(context, search_results)

    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}:{len(search_results)}",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Collected {len(search_results)} observed search results.",
        payload={
            "search_result_count": len(search_results),
            "search_results": [_result_payload(result) for result in search_results[:10]],
            "registered_entity_count": len(registered_entities),
            "registered_entities": [
                {
                    "entity_id": entity.entity_id,
                    "canonical_url": entity.canonical_url,
                    "rank": entity.metadata.get("rank"),
                    "title": entity.title,
                }
                for entity in registered_entities[:10]
            ],
            "source_collection_policy": source_policy,
        },
    )
    context.metadata.setdefault("browser_intelligence", {})["search_results"] = evidence.payload["search_results"]
    context.metadata.setdefault("browser_intelligence", {})["source_collection_policy"] = source_policy
    return execution_result(
        directive,
        status="succeeded",
        reason=evidence.summary,
        evidence=[evidence],
    )


def _result_payload(result) -> dict:
    url = _read(result, "url") or _read(result, "href") or ""
    normalized_url = _read(result, "normalized_url") or _canonical_result_url(url)
    return {
        "rank": _read(result, "rank"),
        "title": _read(result, "title") or _read(result, "text") or "",
        "url": url,
        "snippet": _read(result, "snippet") or _read(result, "description") or "",
        "displayed_url": _read(result, "displayed_url") or "",
        "open_selector": _read(result, "open_selector") or _read(result, "selector"),
        "selector_id": _read(result, "selector_id"),
        "normalized_url": normalized_url,
        "source_domain": _read(result, "source_domain") or "",
        "source_type": _read(result, "source_type") or "unknown",
        "is_ad": bool(_read(result, "is_ad", False)),
        "relevance_score": float(_read(result, "relevance_score", 0.5) or 0.0),
    }


def _extract_search_results(context: ExecutionContext) -> list[dict]:
    results = []
    for container in _search_result_containers(context):
        for index, item in enumerate(_as_list(container), start=len(results) + 1):
            normalized = _normalize_search_result(item, index)
            if normalized.get("url"):
                results.append(normalized)
    if results:
        return _dedupe_results(results)

    for index, block in enumerate(_content_blocks(context.page_context)[:10], start=1):
        normalized = _normalize_content_block(block, index)
        if normalized.get("url"):
            results.append(normalized)
    return _dedupe_results(results)


def _search_result_containers(context: ExecutionContext) -> list:
    containers = []
    artifact = context.browser_intelligence
    page_context = context.page_context
    for source in (
        _read(artifact, "page_model"),
        artifact,
        page_context,
        _read(page_context, "page_model"),
        _read(page_context, "semantic_page_model"),
        _read(_read(page_context, "metadata"), "browser_intelligence"),
        _read(_read(page_context, "metadata"), "page_model"),
    ):
        search_results = _read(source, "search_results")
        if search_results:
            containers.append(search_results)
    return containers


def _content_blocks(page_context) -> list:
    return _as_list(_read(page_context, "content_blocks"))


def _normalize_search_result(item, index: int) -> dict:
    payload = _result_payload(item)
    payload["rank"] = payload.get("rank") or index
    return payload


def _normalize_content_block(block, index: int) -> dict:
    return {
        "rank": index,
        "title": str(_read(block, "title") or _read(block, "text") or "").strip(),
        "url": str(_read(block, "url") or _read(block, "href") or "").strip(),
        "snippet": str(_read(block, "snippet") or _read(block, "description") or "").strip(),
        "displayed_url": str(_read(block, "displayed_url") or "").strip(),
        "open_selector": _read(block, "open_selector") or _read(block, "selector"),
        "selector_id": _read(block, "selector_id"),
        "normalized_url": str(_read(block, "normalized_url") or "").strip(),
        "source_domain": str(_read(block, "source_domain") or "").strip(),
        "source_type": str(_read(block, "source_type") or "unknown").strip(),
        "is_ad": bool(_read(block, "is_ad", False)),
        "relevance_score": float(_read(block, "relevance_score", 0.5) or 0.0),
    }


def _dedupe_results(results: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for result in results:
        key = _canonical_result_url(str(result.get("url") or ""))
        if not key or key in seen or not _openable_search_result(key, result):
            continue
        seen.add(key)
        item = dict(result)
        item["rank"] = len(deduped) + 1
        item["normalized_url"] = key
        if not item.get("source_domain"):
            item["source_domain"] = urlsplit(key).netloc.lower()
        deduped.append(item)
    return deduped


def _canonical_result_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.netloc.lower().endswith("google.com") and parsed.path == "/url":
        query_target = parse_qs(parsed.query).get("q", [""])[0]
        if query_target:
            return _canonical_result_url(query_target)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", parsed.query, ""))


def _openable_search_result(canonical_url: str, result: dict) -> bool:
    if bool(result.get("is_ad")):
        return False
    parsed = urlsplit(canonical_url)
    host = parsed.netloc.lower()
    if not host:
        return False
    if any(host == domain or host.endswith(f".{domain}") for domain in {"google.com", "bing.com", "duckduckgo.com"}):
        blocked_paths = ("/search", "/url", "/preferences", "/settings", "/maps", "/images", "/videos", "/news")
        return not any(parsed.path.startswith(path) for path in blocked_paths)
    return True


def _register_search_result_entities(context: ExecutionContext, results: list[dict]):
    from app.runtime_state_manager.entity_binding import register_entity

    registered = []
    source_page = str(_read(context.page_context, "url") or "")
    for result in results[:40]:
        url = str(result.get("normalized_url") or result.get("url") or "")
        if not url:
            continue
        registered.append(
            register_entity(
                context.mission_id,
                entity_type="search_result",
                source_layer="browser_intelligence.search_result_collection",
                title=str(result.get("title") or url),
                canonical_url=url,
                artifact_id=f"bi:search_result_collection:{_hash(source_page)}:{result.get('rank') or len(registered) + 1}",
                selector_ids=[str(item) for item in (result.get("selector_id"), result.get("open_selector")) if item],
                confidence=max(0.0, min(1.0, float(result.get("relevance_score") or 0.82))),
                source_page=source_page,
                metadata={
                    "rank": str(result.get("rank") or len(registered) + 1),
                    "displayed_url": str(result.get("displayed_url") or ""),
                    "description": str(result.get("snippet") or ""),
                    "source_domain": str(result.get("source_domain") or ""),
                    "source_type": str(result.get("source_type") or "organic"),
                },
            )
        )
    return registered


def _source_collection_policy(context: ExecutionContext, results: list[dict]) -> dict:
    from app.knowledge_extraction.research_spec import build_research_mission_spec

    spec = build_research_mission_spec(context.task or "")
    requested = _requested_source_count(context.task or "", spec)
    available = len(results)
    domains = []
    seen_domains: set[str] = set()
    for result in results:
        domain = str(result.get("source_domain") or urlsplit(str(result.get("normalized_url") or result.get("url") or "")).netloc.lower())
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            domains.append(domain)
    return {
        "schema_version": "source_collection_policy.v1",
        "requested_source_count": requested,
        "available_source_count": available,
        "openable_source_count": min(requested, available),
        "source_policy": getattr(spec, "source_policy", "distinct_non_search_source_urls") if spec else "distinct_non_search_source_urls",
        "distinct_domain_count": len(domains),
        "domains": domains[:12],
        "ready_for_open_phase": available >= min(requested, 1),
    }


def _requested_source_count(task: str, spec: Any | None) -> int:
    if spec is not None:
        return int(getattr(spec, "source_count", 1) or 1)
    match = re.search(
        r"\btop\s+(\d{1,2})\b|\bfirst\s+(\d{1,2})\b|\b(\d{1,2})\s+(?:relevant\s+)?(?:results|sources|pages|tabs)\b",
        task,
        flags=re.IGNORECASE,
    )
    if not match:
        return 1
    count = next((int(group) for group in match.groups() if group), 1)
    return max(1, min(count, 10))


def _hash(value: str) -> str:
    import hashlib

    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def _read(value, key: str, default=None):
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []
