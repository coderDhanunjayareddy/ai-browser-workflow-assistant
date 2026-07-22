from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "access_token",
    "auth",
    "authorization",
    "code",
    "cookie",
    "credential",
    "jwt",
    "key",
    "login",
    "otp",
    "pass",
    "password",
    "refresh_token",
    "secret",
    "session",
    "token",
}

REDACTED = "[redacted]"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def sanitize_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except Exception:
        return value
    if not parts.scheme or not parts.netloc:
        return value
    safe_query = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        safe_query.append((key, REDACTED if _is_sensitive_key(key) else item))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), ""))


def sanitize_ledger_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return REDACTED
    if isinstance(value, str):
        if key.lower() in {"url", "tab_url", "href", "current_url"}:
            return sanitize_url(value)
        return value
    if isinstance(value, list):
        return [sanitize_ledger_value(key, item) for item in value]
    if isinstance(value, dict):
        return sanitize_ledger_payload(value)
    return value


def sanitize_ledger_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: sanitize_ledger_value(key, value) for key, value in payload.items()}
