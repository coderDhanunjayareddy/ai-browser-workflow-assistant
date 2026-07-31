from __future__ import annotations

from app.benchmark.benchmark_models import FailureClassification, ExecutionTrace


FAILURE_SUBSYSTEMS = {
    "planner": "Planner",
    "blueprint": "Blueprint",
    "expansion": "Expansion",
    "ledger": "Ledger",
    "intent_runtime": "Intent Runtime",
    "provider": "Provider",
    "browser": "Browser",
    "knowledge_extraction": "Knowledge Extraction",
    "validation": "Validation",
    "mission_completion": "Mission Completion",
    "extension": "Extension",
    "unknown": "Unknown",
}


class FailureClassifier:
    def classify(self, trace: ExecutionTrace, metrics: dict) -> list[FailureClassification]:
        explicit = trace.stages.get("failures") or []
        if explicit:
            return [self._from_explicit(item, trace.timeline) for item in explicit if isinstance(item, dict)]
        if metrics.get("ledger_consistency") == 0.0:
            return [self._failure("Ledger", "ledger_inconsistency", trace.timeline, "Inspect mission intent lifecycle transitions.", 0.85)]
        if metrics.get("blueprint_accuracy", 1.0) < 0.75:
            return [self._failure("Blueprint", "blueprint_gap", trace.timeline, "Compare expected and observed Blueprint node graph.", 0.75)]
        if metrics.get("mission_success_rate") == 0.0:
            return [self._failure("Unknown", "mission_incomplete", trace.timeline, "Review trace stages to locate missing evidence.", 0.55)]
        return []

    def _from_explicit(self, item: dict, timeline: list[dict]) -> FailureClassification:
        subsystem = FAILURE_SUBSYSTEMS.get(str(item.get("subsystem") or "unknown").lower(), str(item.get("subsystem") or "Unknown"))
        return self._failure(
            subsystem,
            str(item.get("category") or "unknown"),
            list(item.get("timeline") or timeline),
            str(item.get("recommended_fix") or "Review failing subsystem trace."),
            float(item.get("confidence") or 0.5),
        )

    def _failure(self, subsystem: str, category: str, timeline: list[dict], fix: str, confidence: float) -> FailureClassification:
        return FailureClassification(
            category=category,
            root_cause=category,
            affected_subsystem=subsystem,
            timeline=timeline,
            recommended_fix=fix,
            confidence=confidence,
        )
