from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

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

    evidence = IntentExecutionEvidence(
        evidence_id=f"{directive.intent}:{context.mission_id}:{len(search_results)}",
        source=directive.owner,
        kind=directive.capability,
        summary=f"Collected {len(search_results)} observed search results.",
        payload={
            "search_result_count": len(search_results),
            "search_results": [_result_payload(result) for result in search_results[:10]],
        },
    )
    context.metadata.setdefault("browser_intelligence", {})["search_results"] = evidence.payload["search_results"]
    return execution_result(
        directive,
        status="succeeded",
        reason=evidence.summary,
        evidence=[evidence],
    )


def _result_payload(result) -> dict:
    return {
        "rank": _read(result, "rank"),
        "title": _read(result, "title") or _read(result, "text") or "",
        "url": _read(result, "url") or _read(result, "href") or "",
        "snippet": _read(result, "snippet") or _read(result, "description") or "",
        "displayed_url": _read(result, "displayed_url") or "",
        "open_selector": _read(result, "open_selector") or _read(result, "selector"),
        "selector_id": _read(result, "selector_id"),
        "normalized_url": _read(result, "normalized_url") or "",
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
        if not key or key in seen:
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
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", parsed.query, ""))


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
