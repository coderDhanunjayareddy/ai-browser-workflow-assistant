"""
benchmark_v75.py -- V7.5 Decision Center performance benchmarks.

Targets:
  Registry GET hit      < 1ms  p95
  Decision feed         < 5ms  p95
  Inspector             <25ms  p95
  Aggregate (mission)   <15ms  p95
  Analytics GET         < 1ms  p95

Run: python benchmark_v75.py
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
print("\nV7.5 Benchmark -- setting up...")

from app.decisions.models import (
    DecisionType, DecisionPriority, DecisionStatus, make_decision,
)
import app.decisions.registry as dreg
import app.decisions.analytics as danal
import app.decisions.timeline as dtl
import app.decisions.feed as dfeed
import app.decisions.inspector as dinsp
import app.decisions.aggregator as dagg
from app.mission.models import Mission
import app.mission.store as ms
import app.trust.registry as trust_reg
from app.trust import analytics as trust_analytics
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

dreg._reset_for_testing()
danal._reset_for_testing()
dtl._reset_for_testing()
trust_reg._reset_for_testing()
trust_analytics._reset_for_testing()


def _mission() -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title="Bench", objective="bench")
    ms.put(m)
    return m.mission_id


mid1 = _mission()
mid2 = _mission()

# Pre-populate registry with 200 items across 2 missions
_stored_ids = []
for i in range(100):
    d = make_decision(DecisionType.info, DecisionPriority.medium, f"T{i}", "D", "src",
                      mission_id=mid1)
    dreg.add(d)
    _stored_ids.append(d.decision_id)

for i in range(100):
    d = make_decision(DecisionType.blocker, DecisionPriority.high, f"B{i}", "D", "src",
                      mission_id=mid2)
    dreg.add(d)
    _stored_ids.append(d.decision_id)

# A critical one for critical feed
crit_d = make_decision(DecisionType.trust_warning, DecisionPriority.critical,
                        "Crit", "D", "trust_engine", mission_id=mid1)
dreg.add(crit_d)
print(f"  Registry pre-loaded: {dreg.count()} items")


# ── 1. Registry GET hit ───────────────────────────────────────────────────────
print("\n[1] Registry GET (cache hit)")

_sample_id = _stored_ids[0]

def _reg_get():
    dreg.get(_sample_id)

_bench("Registry GET (cache hit)", _reg_get, n=5000, target_ms=1)


# ── 2. Decision feed — latest ─────────────────────────────────────────────────
print("\n[2] Decision feed -- latest(20)")

def _feed_latest():
    dfeed.latest(limit=20)

_bench("DecisionFeed.latest(20)", _feed_latest, n=500, target_ms=5)


# ── 3. Decision feed — for_mission ────────────────────────────────────────────
print("\n[3] Decision feed -- for_mission")

def _feed_mission():
    dfeed.for_mission(mid1, limit=50)

_bench("DecisionFeed.for_mission(50)", _feed_mission, n=500, target_ms=5)


# ── 4. Decision feed — critical_only ─────────────────────────────────────────
print("\n[4] Decision feed -- critical_only")

def _feed_critical():
    dfeed.critical_only(limit=10)

_bench("DecisionFeed.critical_only", _feed_critical, n=1000, target_ms=5)


# ── 5. DecisionInspector ─────────────────────────────────────────────────────
print("\n[5] DecisionInspector.inspect(mission)")

def _inspect():
    dinsp.inspect(mid1)

_bench("DecisionInspector.inspect", _inspect, n=100, target_ms=25)


# ── 6. DecisionAggregator ────────────────────────────────────────────────────
print("\n[6] DecisionAggregator.aggregate")
dreg._reset_for_testing()
mid3 = _mission()

def _aggregate():
    dagg.aggregate(mid3)

_bench("DecisionAggregator.aggregate", _aggregate, n=50, target_ms=15)


# ── 7. Analytics GET ──────────────────────────────────────────────────────────
print("\n[7] Analytics counter")

def _analytics():
    danal.get_analytics()

_bench("DecisionAnalytics.get_analytics", _analytics, n=5000, target_ms=1)


# ── 8. HTTP endpoints ─────────────────────────────────────────────────────────
print("\n[8] HTTP -- GET /decisions/analytics")

def _http_analytics():
    client.get("/decisions/analytics")

_bench("GET /decisions/analytics (HTTP)", _http_analytics, n=200, target_ms=10)

print("\n[9] HTTP -- GET /decisions/critical")

def _http_critical():
    client.get("/decisions/critical")

_bench("GET /decisions/critical (HTTP)", _http_critical, n=200, target_ms=10)


# ── Summary ───────────────────────────────────────────────────────────────────
total  = len(_results)
passed = sum(1 for r in _results if r["passed"])
print(f"\n{'='*60}")
print(f"V7.5 Benchmarks: {passed}/{total} passed", end="")
if _failed_count:
    print(f"  ({_failed_count} FAILED)")
    sys.exit(1)
else:
    print("  -- ALL PASS")
