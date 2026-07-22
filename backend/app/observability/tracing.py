from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from pydantic import Field

from app.contracts.base import VersionedContract
from app.contracts.versions import TRACE_EVENT_V1
from app.diagnostics.trace_sink import resolve_trace_dir
from app.feature_flags import is_active


class TraceEvent(VersionedContract):
    schema_version: str = TRACE_EVENT_V1
    producer: str = "backend.observability"
    trace_event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ledger_event_id: str | None = None


def record_trace_event(event: TraceEvent) -> None:
    if not is_active("V3_TRACE_PARITY"):
        return
    try:
        out_dir = os.path.join(resolve_trace_dir(), "v3")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{event.run_id}.jsonl")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
    except Exception:
        pass


def record_structured_trace(
    *,
    run_id: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    ledger_event_id: str | None = None,
    producer: str = "backend.workflow_orchestrator",
) -> TraceEvent | None:
    if not is_active("V3_TRACE_PARITY"):
        return None
    event = TraceEvent(
        run_id=run_id,
        event_type=event_type,
        payload=payload or {},
        ledger_event_id=ledger_event_id,
        producer=producer,
    )
    record_trace_event(event)
    return event
