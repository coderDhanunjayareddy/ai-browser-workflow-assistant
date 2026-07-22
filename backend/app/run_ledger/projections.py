from __future__ import annotations

from typing import Any

from app.contracts.ledger_events import LedgerEvent


def prior_steps_projection(events: list[LedgerEvent]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for event in events:
        if event.event_type in {"planner.responded", "execution.completed", "report.verified"}:
            steps.append(
                {
                    "event_type": event.event_type,
                    "step_index": event.step_index,
                    "summary": event.payload.get("summary") or event.payload.get("outcome_kind") or "",
                    "payload": event.payload,
                }
            )
    return steps


def planner_trace_projection(events: list[LedgerEvent]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": event.event_id,
            "step_index": event.step_index,
            "event_type": event.event_type,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
        if event.event_type.startswith("planner.")
    ]


def validation_timeline_projection(events: list[LedgerEvent]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": event.event_id,
            "step_index": event.step_index,
            "status": event.payload.get("status"),
            "payload": event.payload,
        }
        for event in events
        if event.event_type in {"verification.completed", "report.verified"}
    ]
