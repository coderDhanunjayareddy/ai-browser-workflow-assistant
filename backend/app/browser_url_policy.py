from __future__ import annotations

from urllib.parse import urlsplit


SEARCH_ENGINE_RESULT_HOSTS = {"google.com", "bing.com", "duckduckgo.com"}
SEARCH_ENGINE_INTERNAL_PATHS = (
    "/search",
    "/url",
    "/preferences",
    "/settings",
    "/maps",
    "/images",
    "/videos",
    "/news",
    "/sorry",
    "/consent",
    "/challenge",
)


def is_openable_browser_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    host = parsed.netloc.lower().removeprefix("www.")
    if host in SEARCH_ENGINE_RESULT_HOSTS:
        return not any(parsed.path.startswith(path) for path in SEARCH_ENGINE_INTERNAL_PATHS)
    return True
