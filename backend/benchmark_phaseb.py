"""
Phase B — Execution Gateway V1 — Benchmark Suite.

Targets (per spec Component 15):
  B1. Gateway startup   < 2ms    (preflight + record creation)
  B2. Dispatcher        < 0.5ms  (to_command + dispatch one command)
  B3. Mock execution    < 5ms    (full plan run through the mock adapter)
  B4. Inspector         < 25ms

Plus supporting micro-benchmarks + HTTP.

Run: python benchmark_phaseb.py
"""
import sys
import time
import statistics

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0


def bench(label: str, target_ms: float, fn, reps: int = 200) -> float:
    global PASS, FAIL
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    p50 = statistics.median(times)
    p95 = statistics.quantiles(times, n=20)[18]
    ok  = p95 <= target_ms
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}")
    print(f"         p50={p50:.4f}ms  p95={p95:.4f}ms  target<{target_ms}ms")
    return p95


# ── Setup ─────────────────────────────────────────────────────────────────────
from app.execution_gateway import (
    engine as gateway, registry as ereg, analytics as eanal, timeline as etl,
    audit as eaudit, inspector as einsp, dispatcher as edisp, runner as erunner,
)
from app.execution_gateway.mock_adapter import MockBrowserAdapter
from app.execution_gateway.models import make_execution
from app.execution_planning import registry as plan_reg, planner
from app.execution_planning.registry import set_status
from app.execution_planning.models import PlanStatus
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState

for m in [ereg, eanal, etl, eaudit, plan_reg, auth_reg, mission_store]:
    m._reset_for_testing()

auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600,
                          mission_id="m-bench", task_id="t-bench")
auth_reg.add(auth)
mission_store.put(Mission("m-bench", "t", "obj", MissionState.active, task_ids=["t-bench"]))
plan = planner.create_plan(auth)
plan_reg.add(plan)
set_status(plan.plan_id, PlanStatus.ready)
plan = plan_reg.get(plan.plan_id)

adapter = MockBrowserAdapter()
seed = gateway.start(plan.plan_id)
EID = seed.execution_id
sample_step = plan.steps[0]

print("\n=== Phase B Execution Gateway — Benchmarks ===\n")

# ── B1. Gateway startup < 2ms ─────────────────────────────────────────────────
print("[B1] Gateway startup (preflight + verification)")
bench("gateway.preflight(plan)", 2.0, lambda: gateway.preflight(plan))
bench("gateway.start(auto_run=False)", 2.0, lambda: gateway.start(plan.plan_id, auto_run=False), reps=100)

# ── B2. Dispatcher < 0.5ms ────────────────────────────────────────────────────
print("\n[B2] Dispatcher")
cmd = edisp.to_command(sample_step)
bench("dispatcher.to_command(step)", 0.5, lambda: edisp.to_command(sample_step))
bench("dispatcher.dispatch(cmd, adapter)", 0.5, lambda: edisp.dispatch(cmd, adapter))

# ── B3. Mock execution < 5ms ──────────────────────────────────────────────────
print("\n[B3] Mock execution (full plan run)")
def _run_full():
    rec = make_execution(plan.plan_id, plan.authorization_id, mission_id="m-bench",
                         task_id="t-bench", total_steps=len(plan.steps),
                         adapter_name="mock", created_at=time.time())
    erunner.run(rec, plan, MockBrowserAdapter())
bench("runner.run() 3-step plan", 5.0, _run_full, reps=100)

# ── B4. Inspector < 25ms ──────────────────────────────────────────────────────
print("\n[B4] Inspector")
bench("inspector.inspect()", 25.0, lambda: einsp.inspect(EID), reps=100)

# ── Supporting ────────────────────────────────────────────────────────────────
print("\n[B5] Supporting")
bench("registry.get()", 1.0, lambda: ereg.get(EID))
bench("registry.summary_for_mission()", 1.0, lambda: ereg.summary_for_mission("m-bench"))
bench("analytics.get_analytics()", 1.0, lambda: eanal.get_analytics())
bench("audit.entries_for_execution()", 1.0, lambda: eaudit.entries_for_execution(EID))

# ── HTTP layer ────────────────────────────────────────────────────────────────
print("\n[B6] HTTP Layer")
from fastapi.testclient import TestClient
from app.main import app
http = TestClient(app)
bench("POST /gateway/start (HTTP)", 20.0,
      lambda: http.post(f"/gateway/start/{plan.plan_id}"), reps=50)
bench("GET /gateway/inspect (HTTP)", 25.0,
      lambda: http.get(f"/gateway/inspect/{EID}"), reps=50)
bench("GET /gateway/analytics (HTTP)", 15.0,
      lambda: http.get("/gateway/analytics"), reps=100)

# ── Summary ───────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"PHASE B BENCHMARKS: {PASS}/{total} pass")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL BENCHMARKS PASS")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
