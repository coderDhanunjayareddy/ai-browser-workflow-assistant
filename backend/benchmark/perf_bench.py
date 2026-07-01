"""
M0 — Performance benchmarks for the benchmark framework ITSELF.

Measures the overhead the harness adds around the (unavoidable) browser + AI latency:
report generation, metric aggregation, criterion evaluation, failure classification, and
timeline/JSON export. All offline — no browser, no network. Builds synthetic task results.

Usage:  python -m benchmark.perf_bench
"""
from __future__ import annotations

import json
import time

from benchmark.m0_models import (
    M0TaskResult, M0StepRecord, TaskStatus, M0Criterion, M0CriterionKind, FailureCategory,
)
from benchmark import m0_metrics, m0_report, criteria, failure_classifier


def _synthetic_results(n: int) -> list[M0TaskResult]:
    out = []
    tiers = ["simple", "medium", "complex"]
    for i in range(n):
        tier = tiers[i % 3]
        r = M0TaskResult(task_id=f"t{i}", website=f"site{i%6}", difficulty=tier,
                         category="SEARCH", executor_mode="playwright")
        for j in range(5):
            s = M0StepRecord(index=j, action_type="click", executed=True,
                             execution_success=(j % 4 != 0), ai_called=True,
                             prompt_tokens=1200, completion_tokens=180,
                             locator_strategy="css_selector",
                             validation_passed=(j % 3 != 0),
                             observe_ms=40, analyze_ms=900, execute_ms=120, validate_ms=15)
            r.steps.append(s)
        r.status = TaskStatus.completed if i % 2 == 0 else TaskStatus.failed
        if r.status == TaskStatus.failed:
            r.failure_category = FailureCategory.execution.value
        r.duration_ms = 8000 + i
        out.append(r)
    return out


def _bench(label: str, fn, iterations: int) -> None:
    fn()  # warm
    t0 = time.perf_counter()
    for _ in range(iterations):
        fn()
    elapsed = (time.perf_counter() - t0) / iterations * 1000
    print(f"  {label:32s} {elapsed:8.3f} ms/op  ({iterations} iters)")


def main() -> int:
    print("[perf] M0 framework overhead (offline, synthetic data)\n")

    results = _synthetic_results(27)

    _bench("aggregate(27 tasks)", lambda: m0_metrics.aggregate(results, executor_mode="playwright"),
           iterations=500)

    meta = {"run_id": "perf", "suite": "nightly", "executor_mode": "playwright", "duration_s": 0}
    _bench("build_report(27 tasks)",
           lambda: m0_report.build_report(meta=meta, results=results, executor_mode="playwright"),
           iterations=500)

    report = m0_report.build_report(meta=meta, results=results, executor_mode="playwright")
    _bench("render_markdown", lambda: m0_report.render_markdown(report), iterations=1000)
    _bench("render_html", lambda: m0_report.render_html(report), iterations=300)
    _bench("json.dumps(report)", lambda: json.dumps(report), iterations=1000)

    ctx = criteria.EvalContext(final_url="https://x/results?q=python",
                               page_text="found python tutorial results here", steps_taken=3)
    crits = [M0Criterion(M0CriterionKind.dom_text_present, target="python"),
             M0Criterion(M0CriterionKind.url_matches, target=r"q=python"),
             M0Criterion(M0CriterionKind.min_completed_steps, value=2)]
    _bench("evaluate_success(3 crit)", lambda: criteria.evaluate_success(crits, ctx),
           iterations=20000)

    sig = failure_classifier.FailureSignal(phase="execute", executed=True, dom_changed=False)
    _bench("classify(failure)", lambda: failure_classifier.classify(sig), iterations=50000)

    _bench("M0TaskResult.to_dict", lambda: results[0].to_dict(), iterations=5000)

    print("\n[perf] done. These are pure-harness costs; real run time is browser + Gemini latency.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
