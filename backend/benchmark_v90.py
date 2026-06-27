"""
V9.0 Execution Planning Layer — Benchmark Suite.

Targets (per spec Component 15):
  B1. Planner    < 2ms
  B2. Validator  < 1ms
  B3. Registry   < 1ms
  B4. Inspector  < 25ms

Plus supporting micro-benchmarks (rollback, analytics, HTTP).

Run: python benchmark_v90.py
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
from app.execution_planning import (
    registry as preg, analytics as panal, timeline as ptl,
    planner as pplanner, validator as pvalidator, rollback as prollback,
    inspector as pinsp,
)
from app.authorization.models import make_authorization
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState

preg._reset_for_testing(); panal._reset_for_testing(); ptl._reset_for_testing()
auth_reg._reset_for_testing(); mission_store._reset_for_testing()

auth = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600,
                          mission_id="m-bench", task_id="t-bench")
auth_reg.add(auth)
mission_store.put(Mission("m-bench", "t", "objective", MissionState.active, task_ids=["t-bench"]))


class _RC:
    last_url = "http://bench.com"


seed_plan = pplanner.create_plan(auth, runtime_context=_RC())
preg.add(seed_plan)
PID = seed_plan.plan_id

print("\n=== V9.0 Execution Planning Layer — Benchmarks ===\n")

# ── B1. Planner < 2ms ─────────────────────────────────────────────────────────
print("[B1] Planner")
bench("planner.create_plan() canonical", 2.0, lambda: pplanner.create_plan(auth, runtime_context=_RC()))

# Workflow-graph planner
class _Node:
    def __init__(self, nid, desc): self.node_id = nid; self.description = desc; self.prerequisites = []
class _Graph:
    def __init__(self, n): self.nodes = n
graph = _Graph([_Node(f"n{i}", "Click button" if i % 2 else "Extract data") for i in range(8)])
bench("planner.create_plan() 8-node graph", 2.0, lambda: pplanner.create_plan(auth, workflow_graph=graph))

# ── B2. Validator < 1ms ───────────────────────────────────────────────────────
print("\n[B2] Validator")
bench("validator.validate()", 1.0, lambda: pvalidator.validate(seed_plan))

# ── B3. Registry < 1ms ────────────────────────────────────────────────────────
print("\n[B3] Registry")
bench("registry.get()", 1.0, lambda: preg.get(PID))
bench("registry.get_for_authorization()", 1.0, lambda: preg.get_for_authorization(auth.authorization_id))
bench("registry.list_for_mission()", 1.0, lambda: preg.list_for_mission("m-bench"))
bench("registry.summary_for_mission()", 1.0, lambda: preg.summary_for_mission("m-bench"))

# ── B4. Inspector < 25ms ──────────────────────────────────────────────────────
print("\n[B4] Inspector")
bench("inspector.inspect()", 25.0, lambda: pinsp.inspect(PID), reps=100)

# ── Supporting ────────────────────────────────────────────────────────────────
print("\n[B5] Supporting")
bench("rollback.plan_rollback()", 1.0, lambda: prollback.plan_rollback(seed_plan.steps))
bench("analytics.get_analytics()", 1.0, lambda: panal.get_analytics())
bench("registry.add()", 1.0, lambda: preg.add(seed_plan))

# ── HTTP layer ────────────────────────────────────────────────────────────────
print("\n[B6] HTTP Layer")
from fastapi.testclient import TestClient
from app.main import app
http = TestClient(app)
bench("POST /plans/create (HTTP)", 20.0,
      lambda: http.post(f"/plans/create/{auth.authorization_id}"), reps=50)
bench("GET /plans/inspect (HTTP)", 25.0,
      lambda: http.get(f"/plans/inspect/{PID}"), reps=50)
bench("GET /plans/analytics (HTTP)", 15.0,
      lambda: http.get("/plans/analytics"), reps=100)

# ── Summary ───────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"V9.0 BENCHMARKS: {PASS}/{total} pass")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL BENCHMARKS PASS")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
