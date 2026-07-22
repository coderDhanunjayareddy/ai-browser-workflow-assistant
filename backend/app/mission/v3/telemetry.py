from __future__ import annotations

from app.mission.v3.models import MissionSnapshot
from app.observability.metrics import default_metric_sink


def record_mission_metrics(run_id: str, snapshot: MissionSnapshot, *, transition_ms: int) -> None:
    tags = {"state": snapshot.state, "mode": snapshot.mode}
    default_metric_sink.record(
        "v3.mission.transition_ms",
        transition_ms,
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.mission.planner_iterations",
        snapshot.planner_iterations,
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.mission.replanning_count",
        len(snapshot.replan_reasons),
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.mission.retries",
        snapshot.retry_count,
        run_id=run_id,
        tags=tags,
    )
    default_metric_sink.record(
        "v3.mission.recoveries",
        snapshot.recovery_count,
        run_id=run_id,
        tags=tags,
    )
    if snapshot.state == "completed":
        default_metric_sink.record("v3.mission.completed", 1, run_id=run_id, tags=tags)
    if snapshot.state == "failed":
        default_metric_sink.record("v3.mission.failed", 1, run_id=run_id, tags=tags)
