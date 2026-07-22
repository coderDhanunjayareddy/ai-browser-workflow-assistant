from __future__ import annotations

from app.observability.metrics import default_metric_sink
from app.semantic_page.cache import SemanticGraphCacheResult


def record_graph_metrics(run_id: str, result: SemanticGraphCacheResult, *, hit_ratio: float, cache_size: int) -> None:
    default_metric_sink.record(
        "v3.semantic_graph.build_ms",
        result.build_ms,
        run_id=run_id,
        tags={"cache_hit": str(result.cache_hit).lower()},
    )
    default_metric_sink.record(
        "v3.semantic_graph.cache_hit_ratio",
        hit_ratio,
        run_id=run_id,
        tags={},
    )
    default_metric_sink.record(
        "v3.semantic_graph.cache_size",
        cache_size,
        run_id=run_id,
        tags={},
    )
