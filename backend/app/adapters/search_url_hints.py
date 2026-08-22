from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


# Declarative search URL hints are optional adapter data. The orchestrator owns
# neither these domains nor their workflow; an unseen site falls back to live
# semantic controls instead of inheriting a named procedure.
SEARCH_URL_HINTS: dict[str, dict[str, str]] = {
    "github.com": {"path": "/search", "query_parameter": "q", "type_parameter": "type"},
    "youtube.com": {"path": "/results", "query_parameter": "search_query"},
}


def canonical_search_url(current_url: str, query: str, task_text: str) -> str | None:
    if not query:
        return None
    parsed = urlparse(current_url)
    host = parsed.netloc.lower().split(":", 1)[0].removeprefix("www.")
    matched_host = next(
        (candidate for candidate in SEARCH_URL_HINTS if host == candidate or host.endswith(f".{candidate}")),
        None,
    )
    if not matched_host:
        return None
    hint = SEARCH_URL_HINTS[matched_host]
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params[hint["query_parameter"]] = query
    type_parameter = hint.get("type_parameter")
    if type_parameter and "repositories" in task_text:
        params[type_parameter] = "repositories"
    return urlunparse((
        parsed.scheme or "https", parsed.netloc, hint["path"], "", urlencode(params), "",
    ))
