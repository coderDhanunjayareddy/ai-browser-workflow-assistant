"""Phase 0 critical-action and sensitive-data policy definitions.

This module defines the contract used to design and test the future live execution gate.
It does not grant authority and is intentionally not wired into execution during Phase 0.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class PolicyDisposition(str, Enum):
    allow = "allow"
    confirm = "confirm"
    watch = "watch"
    handoff = "handoff"
    deny = "deny"


class SensitiveDataClass(str, Enum):
    credentials = "credentials"
    authentication_secret = "authentication_secret"
    financial = "financial"
    government_identifier = "government_identifier"
    health = "health"
    legal_or_hr = "legal_or_hr"
    precise_location = "precise_location"
    biometric = "biometric"
    private_communication = "private_communication"
    browsing_telemetry = "browsing_telemetry"
    personal_contact = "personal_contact"
    user_file = "user_file"


@dataclass(frozen=True)
class CriticalActionRule:
    rule_id: str
    description: str
    disposition: PolicyDisposition
    triggers: tuple[str, ...]
    confirmation_scope: str
    rationale: str


@dataclass(frozen=True)
class SensitiveDataRule:
    data_class: SensitiveDataClass
    examples: tuple[str, ...]
    model_context: str
    transmission: PolicyDisposition
    handling: str


CRITICAL_ACTION_RULES = (
    CriticalActionRule(
        "external_communication",
        "Send, post, publish, submit, or otherwise represent the user to another party.",
        PolicyDisposition.confirm,
        ("send", "post", "publish", "submit", "reply", "comment", "message"),
        "Exact recipient/audience and final content.",
        "The action changes what a third party believes the user said or approved.",
    ),
    CriticalActionRule(
        "financial_transaction",
        "Complete a purchase, payment, transfer, booking charge, or other financial commitment.",
        PolicyDisposition.confirm,
        ("purchase", "pay", "checkout", "place order", "transfer", "confirm booking"),
        "Exact merchant/recipient, item or service, currency, and total amount.",
        "Financial commitments can be difficult to reverse and may create legal obligations.",
    ),
    CriticalActionRule(
        "destructive_or_irreversible",
        "Delete data, cancel a service, close an account, or discard unsaved work.",
        PolicyDisposition.confirm,
        ("delete", "remove", "cancel subscription", "close account", "discard", "permanently delete"),
        "Exact object, scope, and known recovery path.",
        "Deletion or cancellation may be irreversible or costly to recover.",
    ),
    CriticalActionRule(
        "permissions_and_access",
        "Change sharing, roles, permissions, credentials, API keys, or persistent access.",
        PolicyDisposition.confirm,
        ("share", "invite", "grant access", "change permission", "rotate key", "create api key"),
        "Exact resource, principal, permission level, and duration.",
        "The action changes who can access user data or act with the user's authority.",
    ),
    CriticalActionRule(
        "account_or_security_change",
        "Change account identity, security, recovery, MFA, password, or device settings.",
        PolicyDisposition.handoff,
        ("change password", "disable mfa", "recovery email", "security setting", "sign out all"),
        "User completes the security-sensitive step directly.",
        "Account-security changes can enable takeover or lockout.",
    ),
    CriticalActionRule(
        "credential_or_challenge_entry",
        "Enter a password, OTP, MFA code, CAPTCHA response, payment-card secret, or security answer.",
        PolicyDisposition.handoff,
        ("password", "otp", "one-time code", "mfa", "2fa", "captcha", "cvv", "security answer"),
        "User enters the secret directly; it is not placed in model context or logs.",
        "Authentication secrets and human-verification challenges must remain under direct user control.",
    ),
    CriticalActionRule(
        "software_or_extension_install",
        "Install or run downloaded software, scripts, browser-console code, or extensions.",
        PolicyDisposition.handoff,
        ("install extension", "run installer", "execute script", "browser console", "download and run"),
        "Exact artifact, publisher, integrity evidence, requested privileges, and user takeover.",
        "Downloaded code crosses the browser boundary and can compromise the host.",
    ),
    CriticalActionRule(
        "regulated_high_impact",
        "Take medical, legal, employment, housing, education, insurance, or government-benefit action.",
        PolicyDisposition.handoff,
        ("medical", "prescription", "legal filing", "job offer", "insurance claim", "benefit application"),
        "User reviews and completes the consequential decision or submission.",
        "Errors can materially affect rights, health, livelihood, or access to essential services.",
    ),
    CriticalActionRule(
        "sensitive_data_transmission",
        "Transmit sensitive data through a form, message, upload, URL, or access change.",
        PolicyDisposition.confirm,
        ("upload", "attach", "share personal", "send document", "fill sensitive"),
        "Exact data, recipient, purpose, and resulting access.",
        "Typing or uploading data is disclosure even before a final submit button is pressed.",
    ),
    CriticalActionRule(
        "external_tool_or_connector_access",
        "Allow a third-party tool, connector, MCP server, or plugin to read or modify non-public user data.",
        PolicyDisposition.confirm,
        ("connect account", "use connector", "use mcp", "authorize plugin", "third-party tool", "grant connector access"),
        "Exact provider, account, requested operation, data classes, read/write scope, and duration.",
        "External tools create a separate trust boundary and may receive more user data than the immediate output reveals.",
    ),
)


SENSITIVE_DATA_RULES = (
    SensitiveDataRule(SensitiveDataClass.credentials, ("password", "security answer"), "never", PolicyDisposition.handoff, "Never infer, store, log, or send to a model."),
    SensitiveDataRule(SensitiveDataClass.authentication_secret, ("OTP", "MFA code", "session cookie", "API key"), "never", PolicyDisposition.handoff, "User enters short-lived secrets directly; redact from traces."),
    SensitiveDataRule(SensitiveDataClass.financial, ("card number", "bank account", "transaction history"), "redacted-by-default", PolicyDisposition.confirm, "Use only user-provided values for a named recipient and purpose."),
    SensitiveDataRule(SensitiveDataClass.government_identifier, ("passport", "tax ID", "national ID"), "redacted-by-default", PolicyDisposition.confirm, "Require narrow consent and never infer missing values."),
    SensitiveDataRule(SensitiveDataClass.health, ("diagnosis", "prescription", "medical record"), "minimum-necessary", PolicyDisposition.handoff, "Prefer user takeover for medical-care actions."),
    SensitiveDataRule(SensitiveDataClass.legal_or_hr, ("legal matter", "performance review", "payroll record"), "minimum-necessary", PolicyDisposition.confirm, "Identify recipient and access change before transmission."),
    SensitiveDataRule(SensitiveDataClass.precise_location, ("home address", "live GPS coordinates"), "redacted-by-default", PolicyDisposition.confirm, "Do not expose in URLs or unrelated forms."),
    SensitiveDataRule(SensitiveDataClass.biometric, ("face template", "fingerprint", "voiceprint"), "never", PolicyDisposition.handoff, "Do not process unless an explicitly approved product requirement exists."),
    SensitiveDataRule(SensitiveDataClass.private_communication, ("email body", "chat history", "calendar details"), "task-scoped", PolicyDisposition.confirm, "Do not move content across origins without explicit purpose."),
    SensitiveDataRule(SensitiveDataClass.browsing_telemetry, ("history", "internal URL", "search log"), "request-scoped", PolicyDisposition.confirm, "No persistent always-allow access; redact sensitive query values."),
    SensitiveDataRule(SensitiveDataClass.personal_contact, ("email", "phone", "postal address"), "minimum-necessary", PolicyDisposition.confirm, "Confirm when disclosure changes the audience."),
    SensitiveDataRule(SensitiveDataClass.user_file, ("resume", "identity document", "private attachment"), "metadata-first", PolicyDisposition.confirm, "Confirm exact file and destination before upload."),
)


def match_critical_actions(text: str) -> tuple[CriticalActionRule, ...]:
    normalized = " ".join(text.lower().split())
    return tuple(
        rule for rule in CRITICAL_ACTION_RULES
        if any(trigger in normalized for trigger in rule.triggers)
    )


def export_policy_contract() -> dict:
    return {
        "schema_version": "phase0.policy-taxonomy.v1",
        "critical_actions": [
            {**asdict(rule), "disposition": rule.disposition.value}
            for rule in CRITICAL_ACTION_RULES
        ],
        "sensitive_data": [
            {
                **asdict(rule),
                "data_class": rule.data_class.value,
                "transmission": rule.transmission.value,
            }
            for rule in SENSITIVE_DATA_RULES
        ],
    }
