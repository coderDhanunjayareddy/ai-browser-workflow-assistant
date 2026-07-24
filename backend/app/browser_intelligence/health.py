from __future__ import annotations

from app.browser_intelligence.models import BrowserHealthSnapshot, DomMutationSignal, RecoveryDecision, SemanticPageModel, SemanticWaitPlan


class BrowserHealthMonitor:
    def assess(
        self,
        *,
        page_model: SemanticPageModel,
        mutations: list[DomMutationSignal],
        wait_plan: SemanticWaitPlan,
        recovery: RecoveryDecision | None,
    ) -> BrowserHealthSnapshot:
        stale_model = any(signal.requires_refresh for signal in mutations)
        unstable = [
            candidate for candidate in page_model.selector_candidates
            if candidate.valid and candidate.confidence < 0.5
        ]
        selector_instability = len(unstable) / max(1, len(page_model.selector_candidates))
        repeated_failures = 0 if recovery is None or recovery.recovered else (1 if recovery else 0)
        excessive_retries = bool(recovery and len(recovery.attempts) > 5)
        infinite_loop_risk = stale_model and not wait_plan.ready
        navigation_failures = 0
        score = 1.0
        if stale_model:
            score -= 0.2
        if not wait_plan.ready:
            score -= 0.15
        score -= min(0.25, selector_instability * 0.25)
        if excessive_retries:
            score -= 0.15
        if infinite_loop_risk:
            score -= 0.15
        score = max(0.0, round(score, 3))
        return BrowserHealthSnapshot(
            health_score=score,
            stale_model=stale_model,
            repeated_failures=repeated_failures,
            selector_instability=round(selector_instability, 3),
            excessive_retries=excessive_retries,
            infinite_loop_risk=infinite_loop_risk,
            navigation_failures=navigation_failures,
            responsive=score >= 0.5,
            metrics={
                "mutation_frequency": len(mutations),
                "wait_latency_budget_ms": wait_plan.timeout_ms,
                "selector_stability": round(1.0 - selector_instability, 3),
                "adapter_accuracy": page_model.telemetry.get("adapter_metadata", {}).get("adapter_confidence", 0.5),
            },
        )
