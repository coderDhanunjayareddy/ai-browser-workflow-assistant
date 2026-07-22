from __future__ import annotations

from app.context_packet.models import PlannerPacket
from app.observability.metrics import default_metric_sink


def record_packet_metrics(run_id: str, packet: PlannerPacket, *, build_ms: int) -> None:
    default_metric_sink.record("v3.context_packet.build_ms", build_ms, run_id=run_id, tags={})
    default_metric_sink.record(
        "v3.context_packet.packet_chars",
        packet.budget_metadata.packet_chars,
        run_id=run_id,
        tags={},
    )
    default_metric_sink.record(
        "v3.context_packet.projection_items",
        sum(packet.budget_metadata.original_counts.values()),
        run_id=run_id,
        tags={},
    )
    default_metric_sink.record(
        "v3.context_packet.trimmed_items",
        sum(packet.budget_metadata.trimmed_counts.values()),
        run_id=run_id,
        tags={},
    )
