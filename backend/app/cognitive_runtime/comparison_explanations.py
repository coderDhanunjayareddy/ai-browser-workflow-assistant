from __future__ import annotations

from typing import Any

from app.cognitive_runtime.comparison_models import AgreementResult


class ComparisonExplanationBuilder:
    def build(
        self,
        *,
        agreement: AgreementResult,
        runtime_reason: str,
        cognitive_reason: str,
        cognitive_explanation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "agreement": agreement.to_dict(),
            "summary": agreement.explanation,
            "runtime": {
                "decision": agreement.runtime_decision,
                "reason": runtime_reason,
            },
            "cognitive": {
                "decision": agreement.cognitive_decision,
                "reason": cognitive_reason,
                "explanation": cognitive_explanation or {},
            },
            "execution_impact": "none",
            "runtime_v1_wins": True,
        }
