"""
benchmark_v80.py -- V8.0 Human Approval Center performance benchmarks.

Targets:
  Registry GET hit      < 1ms  p95
  Queue query           < 5ms  p95
  Inspector             <25ms  p95
  Analytics GET         < 1ms  p95
  Generate (mission)    <15ms  p95

Run: python benchmark_v80.py
"""
import time
import sys
import statistics
import uuid

_results: list[dict] = []
_failed_count = 0


def _bench(label: str, fn, n: int, target_ms: float) -> None:
    global _failed_count
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    p50 = statistics.median(samples)
    p95 = samples[int(n * 0.95)]
    p99 = samples[int(n * 0.99)]
    passed = p95 <= target_ms
    status = "PASS" if passed else "FAIL"
    if not passed:
        _failed_count += 1
    print(f"  {status}  {label}")
    print(f"         p50={p50:.3f}ms  p95={p95:.3f}ms  p99={p99:.3f}ms"
          f"  target=<{target_ms}ms")
    _results.append({"label": label, "p95": p95, "target_ms": target_ms, "passed": passed})


# ── Setup ─────────────────────────────────────────────────────────────────────
print("\nV8.0 Benchmark -- setting up...")

from app.approvals.models import (
    ApprovalSourceType, ApprovalRiskLevel, make_approval_request,
)
import app.approvals.registry as areg
import app.approvals.analytics as aanal
import app.approvals.timeline as atl
import app.approvals.queue as aq
import app.approvals.inspector as ainsp
import app.approvals.generator as agen
from app.mission.models import Mission
import app.mission.store as ms
import app.trust.registry as trust_reg
from app.trust import analytics as trust_analytics
import app.decisions.registry as dec_reg
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

areg._reset_for_testing()
aanal._reset_for_testing()
atl._reset_for_testing()
trust_reg._reset_for_testing()
trust_analytics._reset_for_testing()
dec_reg._reset_for_testing()


def _mission() -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title="Bench", objective="bench")
    ms.put(m)
    return m.mission_id


mid1 = _mission()
mid2 = _mission()

# Pre-populate: 150 approvals across 2 missions
_stored_ids = []
for i in range(75):
    r = make_approval_request(ApprovalSourceType.trust_engine, f"src-{i}",
                               f"T{i}", "D", ApprovalRiskLevel.medium, mission_id=mid1)
    areg.add(r)
    _stored_ids.append(r.approval_id)

for i in range(75):
    r = make_approval_request(ApprovalSourceType.decision_center, f"src-{i}",
                               f"D{i}", "D", ApprovalRiskLevel.high, mission_id=mid2)
    areg.add(r)
    _stored_ids.append(r.approval_id)

# A few critical ones
for _ in range(5):
    r = make_approval_request(ApprovalSourceType.manual, "s", "Crit", "D",
                               ApprovalRiskLevel.critical, mission_id=mid1)
    areg.add(r)

print(f"  Registry pre-loaded: {areg.count()} items")


# ── 1. Registry GET hit ───────────────────────────────────────────────────────
print("\n[1] Registry GET (cache hit)")
_sample_id = _stored_ids[0]

def _reg_get():
    areg.get(_sample_id)

_bench("Registry GET (cache hit)", _reg_get, n=5000, target_ms=1)


# ── 2. Queue — all_pending ────────────────────────────────────────────────────
print("\n[2] Queue -- all_pending(20)")

def _queue_pending():
    aq.all_pending(limit=20)

_bench("ApprovalQueue.all_pending(20)", _queue_pending, n=500, target_ms=5)


# ── 3. Queue — for_mission ────────────────────────────────────────────────────
print("\n[3] Queue -- for_mission")

def _queue_mission():
    aq.for_mission(mid1, limit=50)

_bench("ApprovalQueue.for_mission(50)", _queue_mission, n=500, target_ms=5)


# ── 4. Queue — critical ───────────────────────────────────────────────────────
print("\n[4] Queue -- critical")

def _queue_critical():
    aq.critical(limit=10)

_bench("ApprovalQueue.critical(10)", _queue_critical, n=1000, target_ms=5)


# ── 5. Queue — summary_for_mission ───────────────────────────────────────────
print("\n[5] Queue -- summary_for_mission")

def _queue_summary():
    aq.summary_for_mission(mid1)

_bench("ApprovalQueue.summary_for_mission", _queue_summary, n=500, target_ms=5)


# ── 6. ApprovalInspector ─────────────────────────────────────────────────────
print("\n[6] ApprovalInspector.inspect(mission)")

def _inspect():
    ainsp.inspect(mid1)

_bench("ApprovalInspector.inspect", _inspect, n=100, target_ms=25)


# ── 7. Analytics GET ──────────────────────────────────────────────────────────
print("\n[7] Analytics counter")

def _analytics():
    aanal.get_analytics()

_bench("ApprovalAnalytics.get_analytics", _analytics, n=5000, target_ms=1)


# ── 8. Generator ─────────────────────────────────────────────────────────────
print("\n[8] ApprovalGenerator.generate_for_mission")
areg._reset_for_testing()
mid3 = _mission()

def _generate():
    agen.generate_for_mission(mid3)

_bench("ApprovalGenerator.generate", _generate, n=50, target_ms=15)


# ── 9. HTTP — GET /approvals/analytics ───────────────────────────────────────
print("\n[9] HTTP -- GET /approvals/analytics")

def _http_analytics():
    client.get("/approvals/analytics")

_bench("GET /approvals/analytics (HTTP)", _http_analytics, n=200, target_ms=10)


# ── 10. HTTP — GET /approvals/pending ────────────────────────────────────────
print("\n[10] HTTP -- GET /approvals/pending")

def _http_pending():
    client.get("/approvals/pending")

_bench("GET /approvals/pending (HTTP)", _http_pending, n=200, target_ms=10)


# ── 11. HTTP — POST /approve (approve flow) ───────────────────────────────────
print("\n[11] HTTP -- POST /approve flow latency")
_appr_ids = []
for _ in range(60):
    r = make_approval_request(ApprovalSourceType.manual, "s", "Bench Approve", "D",
                               ApprovalRiskLevel.medium)
    areg.add(r)
    _appr_ids.append(r.approval_id)

_idx = [0]

def _http_approve():
    if _idx[0] < len(_appr_ids):
        client.post(f"/approvals/{_appr_ids[_idx[0]]}/approve")
        _idx[0] += 1

_bench("POST /approvals/{id}/approve (HTTP)", _http_approve, n=50, target_ms=10)


# ── Summary ───────────────────────────────────────────────────────────────────
total  = len(_results)
passed = sum(1 for r in _results if r["passed"])
print(f"\n{'='*62}")
print(f"V8.0 Benchmarks: {passed}/{total} passed", end="")
if _failed_count:
    print(f"  ({_failed_count} FAILED)")
    sys.exit(1)
else:
    print("  -- ALL PASS")
