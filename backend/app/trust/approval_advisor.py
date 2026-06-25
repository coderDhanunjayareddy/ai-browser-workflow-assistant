"""
V6.5 Trust Engine — ApprovalAdvisorV2.

Determines whether user approval is recommended, given a risk level.
ADVISORY ONLY — this never enforces or bypasses the existing Approval Center.

Rules:
  LOW      → approval_required = False
  MEDIUM   → approval_required = MEDIUM_REQUIRES_APPROVAL (default False, configurable)
  HIGH     → approval_required = True
  CRITICAL → approval_required = True (mandatory)
"""
from __future__ import annotations

from app.trust.models import RiskLevel

# Configurable via environment or settings — default False for MEDIUM
MEDIUM_REQUIRES_APPROVAL: bool = False


class ApprovalAdvisorV2:
    """
    Maps a RiskLevel to an approval recommendation.

    Advisory only. The existing Approval Center retains all enforcement power.
    """

    def __init__(self, medium_requires: bool = MEDIUM_REQUIRES_APPROVAL) -> None:
        self._medium_requires = medium_requires

    def requires_approval(self, risk_level: RiskLevel) -> bool:
        """Return True if user approval is recommended for this risk level."""
        if risk_level == RiskLevel.low:
            return False
        if risk_level == RiskLevel.medium:
            return self._medium_requires
        # HIGH and CRITICAL always recommend approval
        return True

    def reasoning(self, risk_level: RiskLevel) -> str:
        """Human-readable explanation for the recommendation."""
        if risk_level == RiskLevel.low:
            return "Low-risk action — no user approval needed."
        if risk_level == RiskLevel.medium:
            if self._medium_requires:
                return "Medium-risk action — user confirmation recommended (configured)."
            return "Medium-risk action — approval optional (configurable)."
        if risk_level == RiskLevel.high:
            return "High-risk action — user approval strongly recommended before proceeding."
        return "Critical-risk action — mandatory user approval required before any execution."


# Module-level singleton (uses default medium_requires=False)
_advisor = ApprovalAdvisorV2()


def requires_approval(risk_level: RiskLevel) -> bool:
    return _advisor.requires_approval(risk_level)


def reasoning(risk_level: RiskLevel) -> str:
    return _advisor.reasoning(risk_level)
