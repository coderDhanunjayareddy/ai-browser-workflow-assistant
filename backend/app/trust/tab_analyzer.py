"""
V6.5 Trust Engine — TabTrustAnalyzer.

Evaluates the tab set for a mission using V6.0 tab intelligence findings.
Produces a mission-level tab trust score.

Factors:
  + HTTPS usage (per tab)
  + Mission-linked tabs (not orphans)
  - Orphan tabs (no mission_id)
  - Stale background tabs (> 30 min)
  - Duplicate URLs
  - Intelligence findings (MISSING_COMPARISON, DUPLICATE_TABS, etc.)

No execution. Advisory only.
"""
from __future__ import annotations

from typing import Optional

from app.trust.models import (
    TrustEvaluation, RiskLevel, TargetType, make_evaluation,
)
from app.trust.approval_advisor import requires_approval as advise_approval
from app.trust import analytics as trust_analytics


_BASE_TAB_SCORE = 0.80

# Per-finding deductions
_FINDING_DEDUCTIONS: dict[str, float] = {
    "ORPHAN_TABS":            0.20,
    "DUPLICATE_TABS":         0.10,
    "STALE_TABS":             0.08,
    "MISSING_COMPARISON_TAB": 0.05,
    "MISSING_WORKFLOW_TAB":   0.05,
}


class TabTrustAnalyzer:
    """
    Compute a trust score for the tab set of a mission.

    Consumes V6.0 TabContext and TabIntelligenceResult (if available).
    Advisory only — never modifies tab state.
    """

    def analyze(
        self,
        mission_id:   str,
        tab_context:  Optional[dict]   = None,
        tab_findings: Optional[list]   = None,
    ) -> TrustEvaluation:
        """
        Evaluate tab trustworthiness for a mission.

        Args:
            mission_id:   mission being evaluated
            tab_context:  dict from TabContext.to_dict() (or None)
            tab_findings: list of TabFinding.to_dict() dicts (or None)

        Returns:
            TrustEvaluation (advisory)
        """
        if tab_context is None or tab_context.get("tab_count", 0) == 0:
            # No tabs registered → neutral, low risk
            result = make_evaluation(
                target_type       = TargetType.tab,
                target_id         = mission_id,
                trust_score       = 0.70,
                risk_level        = RiskLevel.low,
                approval_required = False,
                confidence        = 0.50,
                reasoning         = "No tabs registered for this mission yet.",
            )
            trust_analytics.record_evaluation(result.risk_level, result.approval_required)
            return result

        score = _BASE_TAB_SCORE
        reasons: list[str] = []
        finding_codes: set[str] = set()

        if tab_findings:
            for f in tab_findings:
                code = f.get("code", "") if isinstance(f, dict) else getattr(f, "code", "")
                finding_codes.add(code)

        # HTTPS bonus: +0.02 per tab using HTTPS (max +0.10)
        summaries = tab_context.get("tab_summaries", [])
        https_count = sum(
            1 for t in summaries
            if str(t.get("url", "")).startswith("https://")
        )
        score += min(https_count * 0.02, 0.10)
        if https_count:
            reasons.append(f"{https_count} HTTPS tab(s) increase trust.")

        # Apply finding deductions
        for code, deduction in _FINDING_DEDUCTIONS.items():
            if code in finding_codes:
                score -= deduction
                reasons.append(f"Finding {code} detected.")

        # Clamp
        score = max(0.0, min(1.0, score))

        # Risk level from score
        if score >= 0.80:
            risk = RiskLevel.low
        elif score >= 0.60:
            risk = RiskLevel.medium
        elif score >= 0.35:
            risk = RiskLevel.high
        else:
            risk = RiskLevel.critical

        approval = advise_approval(risk)

        if not reasons:
            reasons.append(f"Tab trust score: {score:.2f}")

        result = make_evaluation(
            target_type       = TargetType.tab,
            target_id         = mission_id,
            trust_score       = score,
            risk_level        = risk,
            approval_required = approval,
            confidence        = 0.75,
            reasoning         = " ".join(reasons),
        )
        trust_analytics.record_evaluation(result.risk_level, result.approval_required)
        return result


# Module-level singleton
_analyzer = TabTrustAnalyzer()


def analyze(
    mission_id:   str,
    tab_context:  Optional[dict] = None,
    tab_findings: Optional[list] = None,
) -> TrustEvaluation:
    return _analyzer.analyze(
        mission_id   = mission_id,
        tab_context  = tab_context,
        tab_findings = tab_findings,
    )
