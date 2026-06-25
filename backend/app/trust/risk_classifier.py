"""
V6.5 Trust Engine — Risk Classifier.

Maps action types to deterministic risk levels.
No LLM. No embeddings. Pure lookup + substring fallback.

Risk levels:
  LOW      — read, research, compare, navigate
  MEDIUM   — click, fill, form input, tab management
  HIGH     — send, share, post, upload, email
  CRITICAL — purchase, delete, payment, checkout, confirm
"""
from __future__ import annotations

from app.trust.models import RiskLevel


# ── Primary classification map ────────────────────────────────────────────────

_ACTION_RISK: dict[str, RiskLevel] = {
    # LOW — pure observation / research, no external effects
    "read_page":         RiskLevel.low,
    "read":              RiskLevel.low,
    "scroll":            RiskLevel.low,
    "screenshot":        RiskLevel.low,
    "navigate":          RiskLevel.low,
    "research":          RiskLevel.low,
    "search":            RiskLevel.low,
    "compare":           RiskLevel.low,
    "analyze":           RiskLevel.low,
    "inspect":           RiskLevel.low,
    "view":              RiskLevel.low,
    "open_tab":          RiskLevel.low,
    # MEDIUM — reversible local side-effects
    "click":             RiskLevel.medium,
    "select":            RiskLevel.medium,
    "form_fill":         RiskLevel.medium,
    "fill":              RiskLevel.medium,
    "input_text":        RiskLevel.medium,
    "type":              RiskLevel.medium,
    "workflow_prepare":  RiskLevel.medium,
    "tab_open":          RiskLevel.medium,
    "tab_switch":        RiskLevel.medium,
    "login":             RiskLevel.medium,
    "add_to_cart":       RiskLevel.medium,
    # HIGH — hard-to-reverse external side-effects
    "message_send":      RiskLevel.high,
    "send":              RiskLevel.high,
    "email_send":        RiskLevel.high,
    "email":             RiskLevel.high,
    "share":             RiskLevel.high,
    "post":              RiskLevel.high,
    "upload":            RiskLevel.high,
    "submit_form":       RiskLevel.high,
    "whatsapp_send":     RiskLevel.high,
    "sms_send":          RiskLevel.high,
    "comment":           RiskLevel.high,
    # CRITICAL — irreversible or financially significant
    "purchase":          RiskLevel.critical,
    "delete":            RiskLevel.critical,
    "payment":           RiskLevel.critical,
    "pay":               RiskLevel.critical,
    "submit_order":      RiskLevel.critical,
    "checkout":          RiskLevel.critical,
    "confirm_purchase":  RiskLevel.critical,
    "confirm_payment":   RiskLevel.critical,
    "send_money":        RiskLevel.critical,
    "transfer":          RiskLevel.critical,
    "unsubscribe":       RiskLevel.critical,
    "cancel_order":      RiskLevel.critical,
    "refund":            RiskLevel.critical,
    "delete_account":    RiskLevel.critical,
}

# Substring fallback rules (checked in order, first match wins)
_SUBSTRING_RULES: list[tuple[str, RiskLevel]] = [
    ("purchase", RiskLevel.critical),
    ("payment",  RiskLevel.critical),
    ("checkout", RiskLevel.critical),
    ("delete",   RiskLevel.critical),
    ("confirm",  RiskLevel.critical),
    ("transfer",  RiskLevel.critical),
    ("send",     RiskLevel.high),
    ("email",    RiskLevel.high),
    ("share",    RiskLevel.high),
    ("post",     RiskLevel.high),
    ("upload",   RiskLevel.high),
    ("click",    RiskLevel.medium),
    ("fill",     RiskLevel.medium),
    ("type",     RiskLevel.medium),
    ("input",    RiskLevel.medium),
    ("login",    RiskLevel.medium),
    ("read",     RiskLevel.low),
    ("search",   RiskLevel.low),
    ("scroll",   RiskLevel.low),
    ("view",     RiskLevel.low),
    ("navigate", RiskLevel.low),
    ("research", RiskLevel.low),
]


class RiskClassifier:
    """
    Deterministic mapping from action type string to RiskLevel.

    Priority:
      1. Exact match in _ACTION_RISK
      2. Substring scan through _SUBSTRING_RULES
      3. Default: MEDIUM (unknown actions are treated cautiously)
    """

    def classify(self, action_type: str) -> RiskLevel:
        """
        Return the risk level for an action type string.

        Case-insensitive. Strips surrounding whitespace.
        """
        key = action_type.strip().lower()

        # Exact match
        if key in _ACTION_RISK:
            return _ACTION_RISK[key]

        # Substring fallback
        for substring, level in _SUBSTRING_RULES:
            if substring in key:
                return level

        # Unknown → MEDIUM (cautious default — not LOW, not CRITICAL)
        return RiskLevel.medium

    def classify_many(self, action_types: list[str]) -> RiskLevel:
        """Return the highest risk level across a list of action types."""
        if not action_types:
            return RiskLevel.low
        levels = [self.classify(a) for a in action_types]
        return max(levels, key=lambda r: _RISK_ORDER[r])


_RISK_ORDER = {
    RiskLevel.low: 0, RiskLevel.medium: 1,
    RiskLevel.high: 2, RiskLevel.critical: 3,
}


# Module-level singleton
_classifier = RiskClassifier()


def classify(action_type: str) -> RiskLevel:
    return _classifier.classify(action_type)


def classify_many(action_types: list[str]) -> RiskLevel:
    return _classifier.classify_many(action_types)
