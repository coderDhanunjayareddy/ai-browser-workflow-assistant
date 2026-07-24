from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings


TOKEN_TTL_HOURS = 24


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return f"pbkdf2_sha256$210000${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        salt = _unb64(salt_b64)
        expected = _unb64(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_token(user_id: str, session_id: str, expires_at: datetime | None = None) -> str:
    expires_at = expires_at or datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "sid": session_id,
        "exp": int(expires_at.timestamp()),
        "iat": int(datetime.utcnow().timestamp()),
        "nonce": secrets.token_urlsafe(12),
    }
    unsigned = f"{_json_b64(header)}.{_json_b64(payload)}"
    sig = hmac.new(_secret(), unsigned.encode("utf-8"), hashlib.sha256).digest()
    return f"{unsigned}.{_b64(sig)}"


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".", 2)
        unsigned = f"{header_b64}.{payload_b64}"
        expected = hmac.new(_secret(), unsigned.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        payload = json.loads(_unb64(payload_b64).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(datetime.utcnow().timestamp()):
            return None
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_api_key() -> tuple[str, str, str]:
    secret = f"v5_{secrets.token_urlsafe(32)}"
    return secret, token_hash(secret), f"{secret[:7]}...{secret[-4:]}"


def session_expiry() -> datetime:
    return datetime.utcnow() + timedelta(hours=TOKEN_TTL_HOURS)


def _secret() -> bytes:
    value = getattr(settings, "v5_jwt_secret", "") or "dev-v5-product-layer-secret"
    return value.encode("utf-8")


def _json_b64(value: dict[str, Any]) -> str:
    return _b64(json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
