from __future__ import annotations

from app.grounding.cache import GroundingCacheResult
from app.observability.metrics import default_metric_sink


def record_grounding_metrics(
    run_id: str,
    cache_result: GroundingCacheResult,
    *,
    hit_ratio: float,
    cache_size: int,
) -> None:
    result = cache_result.result
    tags = {
        "status": result.status,
        "action_type": result.action_type,
        "fallback_used": str(result.fallback_used).lower(),
        "cache_hit": str(cache_result.cache_hit).lower(),
    }
    default_metric_sink.record(
        "v3.grounding.latency_ms",
        cache_result.resolve_ms,
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.grounding.confidence",
        result.confidence,
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.grounding.cache_hit_ratio",
        hit_ratio,
        run_id=run_id,
        tags={"cache_size": str(cache_size)},
    )
    if result.status == "ambiguous":
        default_metric_sink.record("v3.grounding.ambiguity", 1, run_id=run_id, tags=tags)
    if result.fallback_used:
        default_metric_sink.record("v3.grounding.fallback", 1, run_id=run_id, tags=tags)
    if result.status == "resolved":
        default_metric_sink.record("v3.grounding.resolved", 1, run_id=run_id, tags=tags)
    if result.status == "not_found":
        default_metric_sink.record("v3.grounding.not_found", 1, run_id=run_id, tags=tags)
