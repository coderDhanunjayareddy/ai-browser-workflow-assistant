"""
V8.9 Browser Runtime Layer — Benchmark Suite.

Targets (per spec Component 14):
  B1. Cache lookup       < 1ms
  B2. Context diff       < 2ms
  B3. Runtime sync       < 5ms
  B4. Inspector          < 25ms

Plus supporting micro-benchmarks (event queue, prefetch, HTTP).

Run: python benchmark_v89.py
"""
import sys
import time
import uuid
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
from app.runtime import (
    registry, cache, events, analytics, sync_service, inspector, diff, prefetch,
)
from app.runtime.models import (
    ContextSnapshot, RuntimeEventType, make_runtime_event, make_session,
)

registry._reset_for_testing()
cache._reset_for_testing()
events._reset_for_testing()
analytics._reset_for_testing()

now = time.time()
# Seed a runtime via the sync service
seed = sync_service.sync(active_mission_id="m-bench", active_tab_id="tab-1",
                         last_url="http://a", last_title="A", last_read_view="x" * 1500)
RID = seed.runtime_id

old_snap = ContextSnapshot(last_url="http://a", last_title="A", last_read_view="x" * 1500)
new_snap = ContextSnapshot(last_url="http://b", last_title="B", last_read_view="y" * 1500,
                           last_selection="sel", dom_mutation_count=4)

pf_events = [make_runtime_event(RuntimeEventType.selection_changed, RID, now=now) for _ in range(3)]

print("\n=== V8.9 Browser Runtime Layer — Benchmarks ===\n")

# ── B1. Cache lookup < 1ms ────────────────────────────────────────────────────
print("[B1] Cache lookup")
bench("cache.get(runtime_id)",        1.0, lambda: cache.get(RID))
bench("cache.peek(runtime_id)",       1.0, lambda: cache.peek(RID))
bench("cache.is_fresh(runtime_id)",   1.0, lambda: cache.is_fresh(RID))

# ── B2. Context diff < 2ms ────────────────────────────────────────────────────
print("\n[B2] Context diff")
bench("diff.compute(old, new)",       2.0, lambda: diff.compute(old_snap, new_snap))

# ── B3. Runtime sync < 5ms ────────────────────────────────────────────────────
print("\n[B3] Runtime sync")
_counter = {"i": 0}
def _do_sync():
    _counter["i"] += 1
    sync_service.sync(runtime_id=RID, active_mission_id="m-bench",
                      active_tab_id="tab-1",
                      last_url=f"http://a/{_counter['i'] % 3}", last_title="A",
                      last_read_view="x" * 1500)
bench("sync_service.sync()",          5.0, _do_sync, reps=100)

# ── B4. Inspector < 25ms ──────────────────────────────────────────────────────
print("\n[B4] Inspector")
bench("inspector.inspect()",          25.0, lambda: inspector.inspect(RID), reps=100)

# ── Supporting micro-benchmarks ───────────────────────────────────────────────
print("\n[B5] Supporting")
bench("event_queue.get_for_runtime()", 1.0, lambda: events.get_for_runtime(RID, limit=50))
bench("event_queue.summary()",         1.0, lambda: events.summary(RID))
bench("prefetch.predict()",            1.0, lambda: prefetch.predict(None, pf_events, new_snap))
bench("registry.get()",                1.0, lambda: registry.get(RID))
bench("analytics.get_analytics()",     1.0, lambda: analytics.get_analytics(wall_now=now))

# ── HTTP layer ────────────────────────────────────────────────────────────────
print("\n[B6] HTTP Layer")
from fastapi.testclient import TestClient
from app.main import app
http = TestClient(app)
bench("POST /runtime/sync (HTTP)",   15.0,
      lambda: http.post("/runtime/sync", json={"runtime_id": RID,
                        "active_mission_id": "m-bench", "last_url": "http://h"}),
      reps=50)
bench("GET /runtime/inspect (HTTP)", 25.0,
      lambda: http.get(f"/runtime/inspect?runtime_id={RID}"), reps=50)
bench("GET /runtime/analytics (HTTP)", 15.0,
      lambda: http.get("/runtime/analytics"), reps=100)

# ── Summary ───────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"V8.9 BENCHMARKS: {PASS}/{total} pass")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL BENCHMARKS PASS")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
