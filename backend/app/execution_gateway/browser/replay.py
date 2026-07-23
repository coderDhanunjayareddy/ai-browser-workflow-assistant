from __future__ import annotations

import time
from typing import Any

from app.execution_gateway.browser import exec_timeline, metrics


VALID_TERMINAL_EVENTS = {"completed", "failed", "rollback"}


def export_replay(execution_id: str) -> dict[str, Any]:
    start = time.perf_counter()
    timeline = exec_timeline.summary(execution_id)
    metric_snapshot = metrics.get_metrics()
    validation = validate_replay(timeline)
    return {
        "schema_version": "browser_replay.v1",
        "execution_id": execution_id,
        "export_duration_ms": round((time.perf_counter() - start) * 1000, 3),
        "timeline": timeline,
        "metrics": metric_snapshot,
        "validation": validation,
    }


def validate_replay(timeline: dict[str, Any]) -> dict[str, Any]:
    events = list(timeline.get("events", []))
    errors: list[str] = []
    by_step: dict[str, list[str]] = {}
    for event in events:
        step_id = str(event.get("step_id", ""))
        event_type = str(event.get("event_type", ""))
        if not step_id:
            errors.append("missing_step_id")
        if not event_type:
            errors.append("missing_event_type")
        by_step.setdefault(step_id, []).append(event_type)

    for step_id, event_types in by_step.items():
        if "started" in event_types and not any(event in VALID_TERMINAL_EVENTS for event in event_types):
            errors.append(f"step_without_terminal_event:{step_id}")
        terminal_count = sum(1 for event in event_types if event in VALID_TERMINAL_EVENTS)
        if terminal_count > 1:
            errors.append(f"step_with_multiple_terminal_events:{step_id}")

    return {
        "valid": not errors,
        "errors": errors,
        "step_count": len(by_step),
        "event_count": len(events),
    }
