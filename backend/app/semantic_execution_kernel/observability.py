from __future__ import annotations

import time

from app.semantic_execution_kernel.models import EligibilityResult, GroundingResult, KernelSnapshot, SemanticEntity


def telemetry_summary(
    *,
    started_at: float,
    entities: list[SemanticEntity],
    eligibility: EligibilityResult | None,
    grounding: GroundingResult | None,
    loop_status: dict,
    sync: dict,
) -> dict[str, object]:
    return {
        "kernel_latency_ms": int((time.perf_counter() - started_at) * 1000),
        "entity_count": len(entities),
        "eligibility_failure_count": len(eligibility.failures) if eligibility else 0,
        "grounded": bool(grounding and grounding.grounded),
        "grounding_failure": None if grounding is None or grounding.grounded else grounding.reason,
        "loop_detected": bool(loop_status.get("detected")),
        "planner_rejection_reason": eligibility.reason if eligibility and not eligibility.eligible else None,
        "browser_sync": sync,
    }


def capability_report(snapshot: KernelSnapshot) -> dict[str, object]:
    return {
        "schema_version": "semantic_execution_kernel.capability_report.v1",
        "capability": "browser.semantic_execution_kernel",
        "maturity": "level_4_shadow_certified",
        "rollout": "shadow",
        "telemetry": snapshot.telemetry,
    }
