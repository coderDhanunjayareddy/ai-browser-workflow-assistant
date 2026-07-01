"""
M0.6 — Backend trace sink (TRACE_MODE only).

Captures the exact provider-facing prompt + raw response for one `/analyze` call and writes
it to <trace_dir>/backend/<trace_id>.json, so the benchmark trace viewer can show precisely
what the LLM received and returned. Correlation is by trace_id, carried in the X-Trace-Id
request header and stored in a ContextVar for the duration of the request.

Hard guarantees:
  • Every function is a no-op unless settings.trace_mode is true.
  • No function raises into the caller (all failures are swallowed).
  • Nothing here is read by planning/execution — write-only observability.
"""
from __future__ import annotations

import contextvars
import json
import os
import time
from typing import Any, Optional

from app.core.config import settings

SCHEMA_VERSION = "provider_exchange_v1"

# trace_id for the current request; None outside a traced request.
_current_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "m0_trace_id", default=None)


def enabled() -> bool:
    return bool(settings.trace_mode)


def resolve_trace_dir() -> str:
    """Shared trace directory (same convention the benchmark reads). Env TRACE_DIR wins."""
    if settings.trace_dir:
        return settings.trace_dir
    env = os.environ.get("TRACE_DIR")
    if env:
        return env
    # default: <repo>/backend/.trace_sink  (this file is app/diagnostics/trace_sink.py)
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(backend_dir, ".trace_sink")


def set_current(trace_id: Optional[str]) -> None:
    """Set the trace_id for this request (no-op when tracing is off or id is empty)."""
    if not enabled() or not trace_id:
        return
    try:
        _current_trace_id.set(trace_id)
    except Exception:
        pass


def get_current() -> Optional[str]:
    try:
        return _current_trace_id.get()
    except Exception:
        return None


def record_provider_exchange(*, request: dict[str, Any], response: dict[str, Any],
                             latency_ms: float, trace_id: Optional[str] = None) -> None:
    """Persist one provider exchange. Safe + no-op unless tracing is on with a trace_id."""
    if not enabled():
        return
    tid = trace_id or get_current()
    if not tid:
        return
    try:
        out_dir = os.path.join(resolve_trace_dir(), "backend")
        os.makedirs(out_dir, exist_ok=True)
        record = {
            "schema_version": SCHEMA_VERSION,
            "trace_id": tid,
            "captured_at": time.time(),
            "request": request,          # provider, model, messages (exact prompt), temp, max_tokens
            "response": response,        # raw_text, finish_reason, usage
            "latency_ms": round(latency_ms, 2),
        }
        path = os.path.join(out_dir, f"{tid}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)
    except Exception:
        # diagnostics must never break a request
        pass
