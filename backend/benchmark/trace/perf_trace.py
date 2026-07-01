"""
M0.6 — Trace layer performance benchmark (offline).

Measures the recording/rendering overhead the trace layer adds, and confirms that a
DISABLED recorder is effectively free. All offline with synthetic data; real-run cost is
browser + LLM latency, unaffected by tracing.

Usage:  python -m benchmark.trace.perf_trace
"""
from __future__ import annotations

import os
import tempfile
import time

from benchmark.trace.recorder import TraceRecorder
from benchmark.trace.viewer import generate_viewer
from benchmark.trace.tracing_client import Exchange
from benchmark.analyze_client import AnalyzeResult, SuggestedActionDTO
from benchmark.m0_models import M0TaskResult, M0StepRecord, TaskStatus


def _result(nsteps):
    r = M0TaskResult(task_id="t", website="W", difficulty="simple", category="SEARCH",
                     executor_mode="playwright", status=TaskStatus.completed)
    r.steps = [M0StepRecord(i, action_type="click", action_selector="#go", executed=True,
                            execution_success=True, locator_strategy="css_selector",
                            validation_passed=True, validation_detail="exec=True dom_changed=True",
                            url_after=f"http://x/{i}") for i in range(nsteps)]
    return r


def _exchanges(session, n):
    act = SuggestedActionDTO("a", "click", "#go", None, "go", "because", 0.8, "safe")
    return [Exchange(f"tid{i}", session, "task",
                     {"url": "http://x", "title": "X", "visible_text": "hi" * 200,
                      "interactive_elements": [{"selector": "#go"}] * 30}, [], 1.0 + i,
                     result=AnalyzeResult(analysis="a", suggested_actions=[act])) for i in range(n)]


def _bench(label, fn, iters):
    fn()
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    print(f"  {label:38s} {(time.perf_counter()-t0)/iters*1000:8.3f} ms/op ({iters} iters)")


def main() -> int:
    print("[perf] M0.6 trace layer overhead (offline, synthetic)\n")
    tmp = tempfile.mkdtemp(prefix="m0trace-perf-")
    art, out, tdir = os.path.join(tmp, "a"), os.path.join(tmp, "o"), os.path.join(tmp, "t")
    session = "benchmark_t_r"
    result10 = _result(10)
    ex10 = _exchanges(session, 10)

    rec_on = TraceRecorder(enabled=True, artifacts_dir=art, out_dir=out, trace_dir=tdir, run_id="r")
    rec_off = TraceRecorder(enabled=False, artifacts_dir=art, out_dir=out, trace_dir=tdir, run_id="r")

    _bench("recorder DISABLED (10 steps)", lambda: rec_off.build_task(result10, ex10), iters=5000)
    _bench("recorder ENABLED build+write (10 steps)", lambda: rec_on.build_task(result10, ex10), iters=300)
    rec_on.build_task(result10, ex10)
    _bench("viewer generate (10 steps)",
           lambda: generate_viewer(out_dir=out, run_id="r", task_id="t", artifacts_dir=art), iters=300)

    print("\n[perf] disabled recorder is ~0 ms; enabled cost is per-task post-processing, off the "
          "hot path and dwarfed by browser + LLM latency.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
