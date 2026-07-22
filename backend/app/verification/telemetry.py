from __future__ import annotations

from app.observability.metrics import default_metric_sink
from app.verification.models import ValidationObject


def record_validation_metrics(
    run_id: str,
    validation: ValidationObject,
    *,
    latency_ms: int,
) -> None:
    tags = {
        "status": validation.validation_status,
        "failure_category": validation.failure_category or "none",
        "pipeline": str(validation.replay_metadata.get("pipeline") or "unknown"),
    }
    default_metric_sink.record(
        "v3.validation.latency_ms",
        latency_ms,
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.validation.confidence",
        validation.confidence,
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.validation.result",
        1,
        run_id=run_id,
        tags=tags,
    )
    if validation.failure_category:
        default_metric_sink.record(
            "v3.validation.failure_category",
            1,
            run_id=run_id,
            tags=tags,
        )
