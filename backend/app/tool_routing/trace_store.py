from __future__ import annotations

from collections import deque
from threading import RLock

from app.tool_routing.models import ToolRouteTrace

_MAX_TRACES = 500
_traces: deque[ToolRouteTrace] = deque(maxlen=_MAX_TRACES)
_lock = RLock()


def record(trace: ToolRouteTrace) -> ToolRouteTrace:
    with _lock:
        _traces.append(trace)
    return trace


def get(trace_id: str) -> ToolRouteTrace | None:
    with _lock:
        return next((item for item in reversed(_traces) if item.trace_id == trace_id), None)


def recent(limit: int = 50) -> list[ToolRouteTrace]:
    safe_limit = max(1, min(limit, 100))
    with _lock:
        return list(_traces)[-safe_limit:]


def reset_for_testing() -> None:
    with _lock:
        _traces.clear()
