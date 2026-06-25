"""
V4.0 Intelligence Layer — Performance Benchmark.

Measures latency for each component individually and for the
full engine pipeline. Target: < 50ms total overhead.

Run from backend/ directory:
  PYTHONIOENCODING=utf-8 python benchmark_v40.py

Exit code: 0 = all components within budget, 1 = violations.
"""
import time
import statistics
import sys

ITERATIONS = 500
BUDGET_MS  = 50.0       # per-run total budget
WARN_MS    = 10.0       # warn if single component exceeds this

SEP = "-" * 64


def _now_ms() -> float:
    return time.perf_counter() * 1000


def bench(label: str, fn, iterations: int = ITERATIONS) -> dict:
    times = []
    for _ in range(iterations):
        t0 = _now_ms()
        fn()
        times.append(_now_ms() - t0)
    return {
        "label": label,
        "min": min(times),
        "max": max(times),
        "mean": statistics.mean(times),
        "p50": statistics.median(times),
        "p95": sorted(times)[int(0.95 * len(times))],
        "p99": sorted(times)[int(0.99 * len(times))],
    }


def print_row(r: dict) -> None:
    warn = " !" if r["p95"] > WARN_MS else "  "
    print(
        f"  {r['label']:<40} "
        f"min={r['min']:5.2f}ms  "
        f"p50={r['p50']:5.2f}ms  "
        f"p95={r['p95']:5.2f}ms  "
        f"p99={r['p99']:5.2f}ms{warn}"
    )


# ─── Setup ────────────────────────────────────────────────────────────────────

from app.intelligence.models import (
    ActionType, ApprovalLevel, ExecutionOpportunity,
    ReadinessState, WorkflowReadiness,
)
from app.intelligence.opportunity_detector  import ExecutionOpportunityDetector
from app.intelligence.goal_decomposer       import GoalDecomposer
from app.intelligence.readiness_analyzer    import WorkflowReadinessAnalyzer
from app.intelligence.approval_advisor      import ApprovalPolicyAdvisor
from app.intelligence.plan_builder          import ExecutionPlanBuilder
from app.intelligence.recommendation_engine import WorkflowRecommendationEngine
from app.intelligence.bootstrap_generator   import WorkflowBootstrapGenerator
from app.intelligence.engine                import run_intelligence

det   = ExecutionOpportunityDetector()
decomp = GoalDecomposer()
ana   = WorkflowReadinessAnalyzer()
adv   = ApprovalPolicyAdvisor()
bld   = ExecutionPlanBuilder()
reng  = WorkflowRecommendationEngine()
gen   = WorkflowBootstrapGenerator()

BOOK_QUERY  = "research and book cheapest flight to Mumbai"
BOOK_TOPIC  = "flight to Mumbai"
BOOK_SUMMARY = "Several direct flights available from ₹3,000."

_opp = det.detect(BOOK_QUERY)
_tree = decomp.decompose(BOOK_TOPIC, _opp) if _opp.detected else None
_readiness = ana.analyze(_opp, _tree, None)
_approval  = adv.classify(_opp, BOOK_QUERY)
_plan = bld.build(BOOK_QUERY, BOOK_TOPIC, _opp, _readiness, _approval, _tree)
_recs = reng.generate(_plan, _readiness)

# ─── Run benchmarks ───────────────────────────────────────────────────────────

results = []

print(f"\n{SEP}")
print("  V4.0 Intelligence Layer — Performance Benchmark")
print(f"  Iterations per benchmark: {ITERATIONS}")
print(SEP)

# Component benchmarks
results.append(bench(
    "OpportunityDetector.detect(book)",
    lambda: det.detect(BOOK_QUERY)
))

results.append(bench(
    "OpportunityDetector.detect(research-only)",
    lambda: det.detect("research best flights from Hyderabad")
))

results.append(bench(
    "GoalDecomposer.decompose(book)",
    lambda: decomp.decompose(BOOK_TOPIC, _opp)
))

results.append(bench(
    "ReadinessAnalyzer.analyze(book, no-session)",
    lambda: ana.analyze(_opp, _tree, None)
))

results.append(bench(
    "ApprovalAdvisor.classify(book)",
    lambda: adv.classify(_opp, BOOK_QUERY)
))

results.append(bench(
    "PlanBuilder.build(book, blocked)",
    lambda: bld.build(BOOK_QUERY, BOOK_TOPIC, _opp, _readiness, _approval, _tree)
))

results.append(bench(
    "RecommendationEngine.generate(book, blocked)",
    lambda: reng.generate(_plan, _readiness)
))

results.append(bench(
    "BootstrapGenerator.generate(book)",
    lambda: gen.generate(BOOK_QUERY, _plan, BOOK_TOPIC, BOOK_SUMMARY)
))

# Full engine benchmarks
results.append(bench(
    "run_intelligence — research-only",
    lambda: run_intelligence(
        "research best flights", "flights", "Summary"
    )
))

results.append(bench(
    "run_intelligence — book (no session)",
    lambda: run_intelligence(BOOK_QUERY, BOOK_TOPIC, BOOK_SUMMARY)
))

results.append(bench(
    "run_intelligence — purchase HIGH_RISK",
    lambda: run_intelligence("buy iPhone 15 now", "iPhone 15", "")
))

results.append(bench(
    "run_intelligence — navigate SAFE",
    lambda: run_intelligence("open amazon.com", "amazon", "")
))

# Print results
print("\n  Component benchmarks:")
for r in results[:-4]:
    print_row(r)

print("\n  Full engine benchmarks (entire pipeline):")
for r in results[-4:]:
    print_row(r)

# ─── Budget enforcement ────────────────────────────────────────────────────────

full_engine = [r for r in results if r["label"].startswith("run_intelligence")]
violations = [r for r in full_engine if r["p95"] > BUDGET_MS]
warnings   = [r for r in results if r["p95"] > WARN_MS and r not in violations]

print(f"\n{SEP}")
print(f"  Budget: p95 < {BUDGET_MS:.0f}ms per run_intelligence call")
print(SEP)

if warnings:
    print(f"\n  WARNINGS (p95 > {WARN_MS}ms for individual component):")
    for r in warnings:
        print(f"    {r['label']}: p95={r['p95']:.2f}ms")

if violations:
    print(f"\n  BUDGET VIOLATIONS:")
    for r in violations:
        print(f"    {r['label']}: p95={r['p95']:.2f}ms > {BUDGET_MS}ms")
    print(f"\n  RESULT: BUDGET EXCEEDED ({len(violations)} violations)")
    sys.exit(1)
else:
    best = max(full_engine, key=lambda r: r["p95"])
    print(f"\n  Worst case: {best['label']}")
    print(f"  p95 = {best['p95']:.2f}ms  (budget: {BUDGET_MS:.0f}ms)")
    print(f"\n  RESULT: ALL WITHIN BUDGET")
    sys.exit(0)
