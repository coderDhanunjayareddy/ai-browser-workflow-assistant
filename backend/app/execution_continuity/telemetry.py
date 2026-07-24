from __future__ import annotations

import time

from app.execution_continuity.models import ActionRecord, ContinuityTelemetry, MissionProgress, ProgressValidation


def build_telemetry(
    *,
    started_at: float,
    records: list[ActionRecord],
    mission: MissionProgress,
    validation: ProgressValidation,
) -> ContinuityTelemetry:
    return ContinuityTelemetry(
        build_latency_ms=int((time.perf_counter() - started_at) * 1000),
        action_count=len(records),
        unique_action_count=len({record.signature for record in records}),
        visited_url_count=len({record.url for record in records if record.url}),
        loop_detected=validation.loop_signal.detected,
        progress_percent=mission.progress_percent,
    )
