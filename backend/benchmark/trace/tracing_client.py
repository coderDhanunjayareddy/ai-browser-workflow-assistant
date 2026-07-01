"""
M0.6 — Tracing analyze client.

Transparent wrapper around AnalyzeClient. For each /analyze call it mints a trace_id,
forwards it (so the backend tags its provider-exchange file with the same id), and logs the
exact request inputs + parsed response. The TaskRunner is untouched: it calls `.analyze(...)`
with the normal signature; this wrapper adds the trace_id internally.

The log is consumed after the run by TraceRecorder to assemble one StepTrace per step.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Optional

from benchmark.analyze_client import AnalyzeResult


@dataclass
class Exchange:
    trace_id:      str
    session_id:    str
    task:          str
    page_context:  dict
    prior_steps:   list
    timestamp:     float
    result:        Optional[AnalyzeResult] = None
    error:         Optional[str] = None


class TracingAnalyzeClient:
    def __init__(self, inner) -> None:
        self._inner = inner
        self.exchanges: list[Exchange] = []

    @staticmethod
    def new_trace_id() -> str:
        return uuid.uuid4().hex

    def analyze(self, *, session_id: str, task: str, page_context: dict,
                prior_steps: list, trace_id: Optional[str] = None) -> AnalyzeResult:
        tid = trace_id or self.new_trace_id()
        ex = Exchange(trace_id=tid, session_id=session_id, task=task,
                      page_context=page_context, prior_steps=list(prior_steps), timestamp=time.time())
        try:
            ex.result = self._inner.analyze(session_id=session_id, task=task,
                                            page_context=page_context, prior_steps=prior_steps,
                                            trace_id=tid)
            return ex.result
        except Exception as e:
            ex.error = f"{type(e).__name__}: {e}"
            raise
        finally:
            self.exchanges.append(ex)

    def exchanges_for(self, session_id: str) -> list[Exchange]:
        return [e for e in self.exchanges if e.session_id == session_id]
