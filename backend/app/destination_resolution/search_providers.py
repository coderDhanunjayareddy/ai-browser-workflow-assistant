from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse


@dataclass(frozen=True)
class SearchProvider:
    provider_id: str
    display_name: str
    hosts: tuple[str, ...]
    search_url_template: str | None
    fallback_provider_ids: tuple[str, ...]
    result_path_prefixes: tuple[str, ...]
    result_requires_query: bool
    redirect_paths: tuple[str, ...]
    redirect_query_keys: tuple[str, ...]
    challenge_path_prefixes: tuple[str, ...]


def _load() -> tuple[SearchProvider, ...]:
    raw = json.loads(Path(__file__).with_name("search_providers.json").read_text(encoding="utf-8"))
    return tuple(SearchProvider(
        provider_id=str(item["provider_id"]),
        display_name=str(item["display_name"]),
        hosts=tuple(str(host).casefold() for host in item.get("hosts", [])),
        search_url_template=str(item["search_url_template"]) if item.get("search_url_template") else None,
        fallback_provider_ids=tuple(str(value) for value in item.get("fallback_provider_ids", [])),
        result_path_prefixes=tuple(str(path).casefold() for path in item.get("result_path_prefixes", [])),
        result_requires_query=bool(item.get("result_requires_query", False)),
        redirect_paths=tuple(str(path).casefold() for path in item.get("redirect_paths", [])),
        redirect_query_keys=tuple(str(key) for key in item.get("redirect_query_keys", [])),
        challenge_path_prefixes=tuple(str(path).casefold() for path in item.get("challenge_path_prefixes", [])),
    ) for item in raw)


SEARCH_PROVIDERS = _load()


def _provider(url: str) -> SearchProvider | None:
    parsed = urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").casefold()
    return next((
        provider for provider in SEARCH_PROVIDERS
        if any(host == known or host.endswith(f".{known}") for known in provider.hosts)
    ), None)


def provider_id_for_url(url: str) -> str:
    provider = _provider(url)
    return provider.provider_id if provider else ""


def provider_display_name(provider_id: str) -> str:
    provider = next((item for item in SEARCH_PROVIDERS if item.provider_id == provider_id), None)
    return provider.display_name if provider else "search provider"


def configured_provider_ids() -> tuple[str, ...]:
    return tuple(provider.provider_id for provider in SEARCH_PROVIDERS)


def is_search_provider_url(url: str) -> bool:
    return _provider(url) is not None


def is_search_results_url(url: str) -> bool:
    provider = _provider(url)
    if provider is None:
        return False
    parsed = urlparse(str(url or ""))
    path = (parsed.path or "/").casefold()
    if not any(path.startswith(prefix) for prefix in provider.result_path_prefixes):
        return False
    return bool(parsed.query) if provider.result_requires_query else True


def is_search_surface_url(url: str) -> bool:
    provider = _provider(url)
    if provider is None:
        return False
    parsed = urlparse(str(url or ""))
    path = (parsed.path or "/").casefold()
    return path in {"", "/"} or is_search_results_url(url) or any(
        path.startswith(prefix) for prefix in provider.challenge_path_prefixes
    )


def is_search_challenge(url: str, visible_text: str) -> bool:
    provider = _provider(url)
    if provider is None:
        return False
    path = (urlparse(str(url or "")).path or "/").casefold()
    if any(path.startswith(prefix) for prefix in provider.challenge_path_prefixes):
        return True
    normalized = " ".join(str(visible_text or "").casefold().split())
    return any(marker in normalized for marker in (
        "one last step", "please solve the challenge", "captcha", "recaptcha",
        "hcaptcha", "verify you are human", "not a robot", "unusual traffic",
        "automated queries",
    ))


def unwrap_search_result_url(url: str) -> str:
    provider = _provider(url)
    if provider is None:
        return url
    parsed = urlparse(str(url or ""))
    if parsed.path.casefold() not in provider.redirect_paths:
        return url
    values = parse_qs(parsed.query)
    for key in provider.redirect_query_keys:
        candidate = str((values.get(key) or [""])[0]).strip()
        parsed_candidate = urlparse(candidate)
        if parsed_candidate.scheme in {"http", "https"} and parsed_candidate.hostname:
            return candidate
    return ""


def alternate_search_urls(
    query: str,
    *,
    after_provider_id: str = "",
    exclude_provider_ids: set[str] | None = None,
) -> list[tuple[str, str]]:
    excluded = exclude_provider_ids or set()
    encoded = quote_plus(str(query or "").strip())
    current = next((item for item in SEARCH_PROVIDERS if item.provider_id == after_provider_id), None)
    order = list(current.fallback_provider_ids) if current else []
    order.extend(item.provider_id for item in SEARCH_PROVIDERS if item.provider_id not in order)
    ranked = sorted(SEARCH_PROVIDERS, key=lambda item: order.index(item.provider_id))
    return [
        (provider.provider_id, provider.search_url_template.format(query=encoded))
        for provider in ranked
        if provider.search_url_template and provider.provider_id not in excluded
    ]
