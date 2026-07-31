from __future__ import annotations

from app.cognitive_runtime.comparison_models import AgreementResult, AgreementType


class DecisionAgreementEngine:
    """Compares Runtime V1 decisions with Cognitive Runtime recommendations."""

    _COGNITIVE_TO_RUNTIME = {
        "continue": "CONTINUE",
        "wait": "WAIT",
        "request_user": "REQUEST_USER",
        "recover": "RECOVER",
        "replan": "REPLAN",
        "complete_ready": "COMPLETE",
        "blocked": "BLOCKED",
        "fail": "FAILED",
        "cancel": "FAILED",
        "unknown": "UNKNOWN",
    }

    _SEMANTIC_GROUPS = (
        {"COMPLETE", "CONTINUE"},
        {"FAILED", "BLOCKED"},
    )

    _PARTIAL_GROUPS = (
        {"WAIT", "REQUEST_USER"},
        {"REPLAN", "RECOVER"},
        {"BLOCKED", "REQUEST_USER", "WAIT"},
    )

    def compare(self, *, runtime_decision: str, cognitive_decision: str) -> AgreementResult:
        runtime = self._normalize_runtime(runtime_decision)
        cognitive = self._normalize_cognitive(cognitive_decision)
        if runtime == cognitive:
            return AgreementResult(AgreementType.EXACT, runtime, cognitive, "none", "Runtime V1 and Cognitive Runtime chose the same decision.")
        if self._same_group(runtime, cognitive, self._SEMANTIC_GROUPS):
            return AgreementResult(AgreementType.SEMANTIC, runtime, cognitive, "semantic_equivalent", "Decisions differ in label but have compatible execution meaning.")
        if self._same_group(runtime, cognitive, self._PARTIAL_GROUPS):
            return AgreementResult(AgreementType.PARTIAL, runtime, cognitive, "adjacent_runtime_state", "Decisions point to adjacent handling paths and need migration review.")
        return AgreementResult(AgreementType.DISAGREEMENT, runtime, cognitive, f"{runtime.lower()}_vs_{cognitive.lower()}", "Runtime V1 and Cognitive Runtime recommend different handling.")

    def _normalize_cognitive(self, decision: str) -> str:
        normalized = str(decision or "").strip().lower()
        return self._COGNITIVE_TO_RUNTIME.get(normalized, self._normalize_runtime(decision))

    def _normalize_runtime(self, decision: str) -> str:
        normalized = str(decision or "").strip().upper().replace("-", "_").replace(" ", "_")
        if normalized in {"FAIL", "FAILURE", "ERROR"}:
            return "FAILED"
        if normalized == "ASK":
            return "REQUEST_USER"
        if normalized == "REPORT":
            return "COMPLETE"
        return normalized or "UNKNOWN"

    @staticmethod
    def _same_group(runtime: str, cognitive: str, groups: tuple[set[str], ...]) -> bool:
        return any(runtime in group and cognitive in group for group in groups)
