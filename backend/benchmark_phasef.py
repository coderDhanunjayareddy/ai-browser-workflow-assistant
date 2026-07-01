"""
Phase F — Certification & Reliability — Benchmark Suite.

Benchmarks complete workflows with percentile statistics (p50/p95/p99): semantic analysis,
planning, mock execution (planner+gateway pipeline), reliability rollup, report generation,
and failure classification. A guarded real-browser section reports real workflow-duration
percentiles when chromium is available.

Run: python benchmark_phasef.py
"""
import sys
import time
import statistics

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0


def _pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (p / 100.0) * (len(s) - 1)
    lo = int(k); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def bench(label, target_p95, fn, reps=100):
    global PASS, FAIL
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    p50, p95, p99 = _pct(times, 50), _pct(times, 95), _pct(times, 99)
    if target_p95 is None:
        print(f"  [INFO] {label}: p50={p50:.3f} p95={p95:.3f} p99={p99:.3f} ms")
        return
    ok = p95 <= target_p95
    if ok: PASS += 1
    else:  FAIL += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: p50={p50:.3f} p95={p95:.3f} p99={p99:.3f} ms  (p95<{target_p95})")


from app.certification import scenarios, runner, reliability, failure_catalog, report, fixtures
from app.certification.models import WorkflowOutcome
from app.website_intelligence import analyzer as wi
from app.execution_gateway.browser import failure_classes as fc
from app.execution_gateway import registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_planning import registry as plan_reg
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl


def reset_all():
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl,
              reliability, failure_catalog]:
        m._reset_for_testing()


SCS = scenarios.build_scenarios()
print("\n=== Phase F Certification & Reliability — Benchmarks ===\n")
print(f"  {len(SCS)} scenarios / {len(fixtures.FIXTURES)} fixtures\n")

print("[B1] Semantic analysis per fixture (Website Intelligence reuse)")
htmls = list(fixtures.FIXTURES.values())
bench("WI.analyze_html (medium fixture)", 10.0, lambda: wi.analyze_html(htmls[3]))

print("\n[B2] Planning — build + register + ready a workflow plan")
login = next(s for s in SCS if s.scenario_id == "cert-login")
def _plan_build():
    steps = login.build_steps("http://x")
    runner._build_ready_plan(login, steps)
reset_all()
bench("plan build+register+ready (5 steps)", 5.0, _plan_build, reps=200)

print("\n[B3] Mock execution — full planner+gateway pipeline per workflow")
def _one_mock():
    reset_all()
    runner.run_scenario(login, base_url="", real_browser=False, seen_at=1.0)
bench("mock workflow (login, 5 steps)", 50.0, _one_mock, reps=100)

print("\n[B4] Reliability rollup + report")
reset_all()
for i in range(200):
    reliability.record_workflow(WorkflowOutcome(f"s{i}", "C", "app", i % 5 != 0, float(i % 50)))
bench("reliability.metrics (200 outcomes)", 5.0, reliability.metrics, reps=200)
reset_all()
_results = runner.certify_all(SCS, base_url="", real_browser=False, seen_at=1.0)
bench("report.build_report (all scenarios)", 10.0,
      lambda: report.build_report(_results, scenarios=SCS, mode="mock"), reps=100)

print("\n[B5] Failure classification throughput")
bench("classify_failure (ambiguous)", 1.0,
      lambda: fc.classify_failure(Exception("strict mode violation: resolved to 2 elements"), phase="click"),
      reps=500)

print("\n[B6] Full mock certification suite (all workflows) — INFO")
def _full_suite():
    reset_all()
    runner.certify_all(SCS, base_url="", real_browser=False, seen_at=1.0)
bench(f"certify_all ({len(SCS)} workflows, mock)", None, _full_suite, reps=10)

# ── Guarded real-browser workflow percentiles (INFO) ──────────────────────────
print("\n[B7] Real-browser workflow duration percentiles (INFO; needs chromium)")
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True); b.close()
    from app.execution_gateway.browser import session as bsession
    srv = fixtures.FixtureServer().start()
    # a representative subset (fast workflows) measured a few times each
    subset = [s for s in SCS if s.scenario_id in
              ("cert-login", "cert-search", "cert-edit-row", "cert-pagination", "cert-tabs",
               "cert-confirm", "cert-multistep")]
    durations = []
    try:
        for _ in range(2):
            for s in subset:
                reset_all(); bsession._reset_for_testing()
                r = runner.run_scenario(s, base_url=srv.base_url, real_browser=True, seen_at=1.0)
                durations.append(r.duration_ms)
    finally:
        srv.stop()
    print(f"  [INFO] real workflow durations (n={len(durations)}): "
          f"p50={_pct(durations,50):.0f} p95={_pct(durations,95):.0f} p99={_pct(durations,99):.0f} ms")
    print(f"  [INFO] min={min(durations):.0f} max={max(durations):.0f} ms")
except Exception as e:
    print(f"  [SKIP] chromium unavailable: {type(e).__name__}: {str(e)[:80]}")

total = PASS + FAIL
print(f"\n{'='*56}")
print(f"PHASE F BENCHMARKS: {PASS}/{total} pass")
print("  ALL BENCHMARKS PASS" if FAIL == 0 else f"  FAILURES: {FAIL}")
print(f"{'='*56}")
sys.exit(0 if FAIL == 0 else 1)
