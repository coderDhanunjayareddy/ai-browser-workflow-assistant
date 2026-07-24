from __future__ import annotations

from typing import Any

from app.browser_intelligence.models import (
    BrowserHealthSnapshot,
    BrowserMemorySnapshot,
    DomMutationSignal,
    RecoveryDecision,
    SemanticPageModel,
    SemanticWaitPlan,
    VerificationOutcome,
    VisualGroundingTarget,
)


def build_replay_artifact(
    *,
    page_model: SemanticPageModel,
    verification_outcomes: list[VerificationOutcome] | None = None,
    mutation_signals: list[DomMutationSignal] | None = None,
    wait_plan: SemanticWaitPlan | None = None,
    memory: BrowserMemorySnapshot | None = None,
    recovery: RecoveryDecision | None = None,
    visual_targets: list[VisualGroundingTarget] | None = None,
    health: BrowserHealthSnapshot | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "browser_intelligence.replay.v1",
        "page_model": {
            "schema_version": page_model.schema_version,
            "url": page_model.url,
            "title": page_model.title,
            "classification": page_model.classification.to_dict(),
            "adapter": page_model.adapter,
            "element_count": len(page_model.elements),
            "selector_decisions": [
                candidate.to_dict()
                for candidate in page_model.selector_candidates[:50]
            ],
            "search_results": [
                result.to_dict()
                for result in page_model.search_results[:10]
            ],
        },
        "verification_outcomes": [
            outcome.to_dict()
            for outcome in verification_outcomes or []
        ],
        "dynamic_dom": [signal.to_dict() for signal in mutation_signals or []],
        "wait_plan": wait_plan.to_dict() if wait_plan else None,
        "browser_memory": memory.to_dict() if memory else None,
        "recovery": recovery.to_dict() if recovery else None,
        "visual_targets": [target.to_dict() for target in visual_targets or []],
        "health": health.to_dict() if health else None,
    }
