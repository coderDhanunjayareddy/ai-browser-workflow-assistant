"""
M0.6 — Trace layer validation suite (standalone, offline).

Exercises schema + recorder + viewer + tracing client + backend gating end-to-end with test
doubles and prints a PASS/FAIL checklist. No browser, no network, no backend. Exit 0 iff all
checks pass. Mirrors benchmark/validate_m0.py.

Usage:  python -m benchmark.trace.validate_trace
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

from benchmark.trace import schema
from benchmark.trace.recorder import TraceRecorder
from benchmark.trace.viewer import generate_viewer
from benchmark.trace.tracing_client import TracingAnalyzeClient, Exchange
from benchmark.analyze_client import AnalyzeResult, SuggestedActionDTO
from benchmark.m0_models import M0TaskResult, M0StepRecord, TaskStatus

_checks: list[tuple[str, bool]] = []


def ck(name: str, cond: bool) -> None:
    _checks.append((name, bool(cond)))


def _result():
    r = M0TaskResult(task_id="fixture__login_form", website="Fixture", difficulty="simple",
                     category="FORM_SUBMIT", executor_mode="playwright", status=TaskStatus.stuck)
    r.failure_detail = "no progress"
    r.steps = [M0StepRecord(i, action_type="fill", action_selector="#u", action_value="tester",
                            executed=True, execution_success=True, locator_strategy="css_selector",
                            locator_attempts=1, validation_passed=False,
                            validation_detail="exec=True dom_changed=False", execute_ms=40.0,
                            url_after="http://127.0.0.1/login") for i in range(3)]
    return r


def _exchanges(session, n=3):
    out = []
    for i in range(n):
        act = SuggestedActionDTO(f"a{i}", "fill", "#u", "tester", "fill username",
                                 "the field looks empty so I fill it", 0.9, "safe")
        out.append(Exchange(f"tid{i}", session, "log in",
                            {"url": "http://127.0.0.1/login", "title": "Login",
                             "visible_text": "Login form", "interactive_elements": [{"selector": "#u"}]},
                            [], 1.0 + i, result=AnalyzeResult(analysis="filling", suggested_actions=[act])))
    return out


def run() -> int:
    tmp = tempfile.mkdtemp(prefix="m0trace-")
    artifacts, out, tdir = os.path.join(tmp, "a"), os.path.join(tmp, "o"), os.path.join(tmp, "t")
    os.makedirs(os.path.join(tdir, "backend"))
    with open(os.path.join(tdir, "backend", "tid0.json"), "w", encoding="utf-8") as f:
        json.dump({"schema_version": "provider_exchange_v1", "trace_id": "tid0", "captured_at": 1.0,
                   "request": {"provider": "openrouter", "model": "openai/gpt-4o-mini",
                               "messages": [{"role": "system", "content": "SYS"},
                                            {"role": "user", "content": "COMPRESSED PLANNER CONTEXT: {...}"}],
                               "temperature": 0, "max_tokens": 512},
                   "response": {"raw_text": '{"suggested_actions":[]}', "finish_reason": "stop",
                                "usage": {"total_tokens": 1300}}, "latency_ms": 700.0}, f)

    session = "benchmark_fixture__login_form_r1"
    rec = TraceRecorder(enabled=True, artifacts_dir=artifacts, out_dir=out, trace_dir=tdir, run_id="r1")
    traces = rec.build_task(_result(), _exchanges(session))

    ck("one trace per step", len(traces) == 3)
    ck("schema version tagged", all(t["schema_version"] == schema.SCHEMA_VERSION for t in traces))
    ck("trace_id present on every step", all(t["trace_id"] for t in traces))
    ck("backend exact prompt captured (step 0)", traces[0]["provider_request"]["available"] is True)
    ck("assembled prompt is system+user", len(traces[0]["provider_request"]["assembled_prompt"]) == 2)
    ck("raw response captured (step 0)", traces[0]["provider_response"]["raw_text"] is not None)
    ck("latency captured", traces[0]["provider_response"]["latency_ms"] == 700.0)
    ck("missing backend marked unavailable, not fabricated",
       traces[1]["provider_request"]["available"] is False
       and traces[1]["provider_response"]["raw_text"] is None)
    ck("parsed action + reasoning from benchmark side",
       traces[0]["parsed_action"]["action_type"] == "fill"
       and "empty" in (traces[0]["parsed_action"]["reasoning"] or ""))
    ck("executor selector recorded", traces[0]["executor"]["selector_used"] == "#u")
    ck("validation dom_changed parsed", traces[0]["validation"]["dom_changed"] is False)
    ck("terminal decision mirrors STUCK", traces[-1]["loop_decision"]["decision"] == "stuck")
    ck("non-terminal decision is continue/recovered",
       traces[0]["loop_decision"]["decision"] in ("continue", "recovered"))
    ck("step files written", os.path.exists(os.path.join(out, "r1", "fixture__login_form", "step_000.trace.json")))
    ck("index written", os.path.exists(os.path.join(out, "r1", "fixture__login_form", "index.json")))

    # viewer
    vp = generate_viewer(out_dir=out, run_id="r1", task_id="fixture__login_form", artifacts_dir=artifacts)
    html = open(vp, encoding="utf-8").read() if vp else ""
    ck("viewer generated", bool(vp))
    ck("viewer embeds traces", "window.__TRACES__" in html)
    ck("viewer self-contained (no external assets)", 'src="http' not in html and 'href="http' not in html)

    # tracing client delegates + forwards trace_id
    class _Inner:
        def __init__(self): self.tid = None
        def analyze(self, *, session_id, task, page_context, prior_steps, trace_id=None):
            self.tid = trace_id
            return AnalyzeResult(analysis="ok", suggested_actions=[])
    inner = _Inner()
    tc = TracingAnalyzeClient(inner)
    tc.analyze(session_id="s", task="t", page_context={}, prior_steps=[])
    ck("tracing client forwards a trace_id", inner.tid is not None)
    ck("tracing client logs exchange", len(tc.exchanges_for("s")) == 1)

    # disabled recorder is a pure no-op
    rec_off = TraceRecorder(enabled=False, artifacts_dir=artifacts, out_dir=os.path.join(tmp, "off"),
                            trace_dir=tdir, run_id="r2")
    ck("disabled recorder returns []", rec_off.build_task(_result(), []) == [])
    ck("disabled recorder writes nothing", not os.path.exists(os.path.join(tmp, "off")))

    passed = sum(1 for _, ok in _checks if ok)
    total = len(_checks)
    print("\n=== M0.6 TRACE VALIDATION ===")
    for name, ok in _checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run())
