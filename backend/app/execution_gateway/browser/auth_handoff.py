from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuthHandoffSignal:
    required: bool
    reason: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "reason": self.reason,
            "confidence": self.confidence,
            "evidence": dict(self.evidence),
        }


AUTH_TERMS = (
    "sign in",
    "log in",
    "login",
    "password",
    "passkey",
    "verification code",
    "two-step",
    "2-step",
    "multi-factor",
    "mfa",
    "otp",
    "sso",
)


def detect_auth_handoff(page: Any) -> AuthHandoffSignal:
    try:
        state = page.evaluate(
            """() => {
              const text = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 2000);
              const passwordFields = document.querySelectorAll('input[type="password"]').length;
              const otpFields = Array.from(document.querySelectorAll('input')).filter((el) => {
                const label = [el.name, el.id, el.autocomplete, el.placeholder, el.getAttribute('aria-label')]
                  .filter(Boolean).join(' ').toLowerCase();
                return /otp|one-time|verification|code/.test(label);
              }).length;
              return { text, passwordFields, otpFields, url: location.href, title: document.title };
            }"""
        )
    except Exception as exc:  # noqa: BLE001
        return AuthHandoffSignal(False, "unavailable", 0.0, {"error": str(exc)[:200]})

    haystack = f"{state.get('title', '')} {state.get('url', '')} {state.get('text', '')}".lower()
    matched = [term for term in AUTH_TERMS if term in haystack]
    password_fields = int(state.get("passwordFields", 0) or 0)
    otp_fields = int(state.get("otpFields", 0) or 0)

    if password_fields:
        return AuthHandoffSignal(True, "password_required", 0.95, {"password_fields": password_fields, "matched_terms": matched})
    if otp_fields:
        return AuthHandoffSignal(True, "mfa_or_otp_required", 0.9, {"otp_fields": otp_fields, "matched_terms": matched})
    if matched:
        return AuthHandoffSignal(True, "authentication_page", 0.75, {"matched_terms": matched[:5]})
    return AuthHandoffSignal(False, "not_auth", 0.2, {"matched_terms": []})
