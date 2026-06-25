"""
V4.0 Component 7 — ApprovalPolicyAdvisor.

Classifies the safety risk of a detected execution opportunity.

SAFE            — read-only, search, navigation, no commitments
REQUIRES_APPROVAL — creates bookings, registrations, downloads
HIGH_RISK       — payments, deletions, communications to third parties

All classification is rule-based. No LLM. < 1 ms.
"""
from __future__ import annotations

from app.intelligence.models import ActionType, ApprovalLevel, ExecutionOpportunity

# Keyword overrides — message text → HIGH_RISK regardless of action_type
_HIGH_RISK_PHRASES: frozenset[str] = frozenset({
    "pay", "payment", "pay now", "place order", "confirm payment",
    "buy now", "purchase now", "complete payment",
    "delete", "remove", "cancel account", "unsubscribe permanently",
    "send message", "send email", "send whatsapp",
})

_SAFE_TYPES: frozenset[ActionType] = frozenset({
    ActionType.search,
    ActionType.navigate,
    ActionType.unknown,
})

_REQUIRES_APPROVAL_TYPES: frozenset[ActionType] = frozenset({
    ActionType.book,
    ActionType.register,
    ActionType.schedule,
    ActionType.download,
    ActionType.rent,
    ActionType.apply,
})

_HIGH_RISK_TYPES: frozenset[ActionType] = frozenset({
    ActionType.purchase,
    ActionType.communicate,
})


class ApprovalPolicyAdvisor:
    """
    Classifies an execution opportunity into SAFE, REQUIRES_APPROVAL, or HIGH_RISK.

    Safety priority: phrase-level overrides > action_type defaults.
    """

    def classify(
        self,
        opportunity: ExecutionOpportunity,
        query: str = "",
    ) -> ApprovalLevel:
        """
        Return the ApprovalLevel for the given opportunity.

        Args:
            opportunity: detected execution opportunity
            query: original user message (used for phrase-level overrides)
        """
        if not opportunity.detected:
            return ApprovalLevel.safe

        lowered = query.lower()

        # Phrase-level override always wins
        if any(phrase in lowered for phrase in _HIGH_RISK_PHRASES):
            return ApprovalLevel.high_risk

        action_type = opportunity.action_type
        if action_type in _HIGH_RISK_TYPES:
            return ApprovalLevel.high_risk
        if action_type in _REQUIRES_APPROVAL_TYPES:
            return ApprovalLevel.requires_approval
        if action_type in _SAFE_TYPES:
            return ApprovalLevel.safe

        return ApprovalLevel.requires_approval  # default conservative


# Module-level singleton
advisor = ApprovalPolicyAdvisor()
