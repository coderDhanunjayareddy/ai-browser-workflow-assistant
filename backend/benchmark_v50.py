"""
V5.0 Mission Layer — Performance Benchmark.

Measures p50/p95/p99 latency for each core operation with 200 repetitions.

Performance targets:
  create_mission:            < 1ms
  attach_task:               < 1ms
  lifecycle_transitions:     < 1ms
  mission_store_get:         < 0.1ms
  affinity_score_pair:       < 1ms
  find_matching_mission:     < 5ms (with 20 active missions)
  analytics_get:             < 0.5ms
  memory_build_3_tasks:      < 5ms
  context_registry_3_tasks:  < 10ms
  timeline_build_3_tasks:    < 5ms
  bootstrap_enrich:          < 10ms

Usage:
  cd backend
  python benchmark_v50.py
"""
import statistics
import sys
import time

REPS = 200
COL  = 38

def bench(label: str, fn, reps: int = REPS, target_p95_ms: float = None):
    samples = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)

    p50 = statistics.median(samples)
    p95 = statistics.quantiles(samples, n=100)[94]
    p99 = statistics.quantiles(samples, n=100)[98]
    status = ""
    if target_p95_ms is not None:
        status = "  OK" if p95 <= target_p95_ms else "  SLOW"
    print(f"  {label:<{COL}} p50={p50:.3f}ms  p95={p95:.3f}ms  p99={p99:.3f}ms{status}")
    return p95


def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
from app.mission import store as mission_store, lifecycle as mission_lifecycle
from app.mission import analytics as mission_analytics, affinity as mission_affinity
from app.mission import memory as mission_memory, context_registry
from app.mission import timeline as mission_timeline, bootstrap as mission_bootstrap
from app.mission.models import create_mission, MissionState
from app.unified import store as task_store
from app.unified.models import UnifiedTask, ApprovalRecord, ApprovalStatus

import uuid

def _task(query: str = "find flights to NYC") -> UnifiedTask:
    t = UnifiedTask(
        task_id=str(uuid.uuid4())[:8],
        conversation_id="bench-conv",
        original_query=query,
    )
    t.entities = {"city": "NYC", "airline": "Delta"}
    t.current_goal = "Book cheapest flight"
    t.research_report = {
        "executive_summary": "Found 12 flights",
        "key_findings": ["Avg price $420", "Best time Tuesday"],
        "confidence_score": 0.88,
    }
    return t

def _put_task(query: str = "find flights") -> UnifiedTask:
    t = _task(query)
    task_store.put(t)
    return t


section("1. Mission Lifecycle")

def _create():
    m = create_mission("Bench Mission", "Bench objective")
    mission_store.put(m)
    mission_store.remove(m.mission_id)

bench("create_mission (factory)", _create, target_p95_ms=1.0)

_m_attach = mission_lifecycle.create_mission_obj("Attach Test")
_t_attach = _put_task("flights to NYC")
def _attach():
    global _m_attach
    _m_attach = create_mission("Tmp")
    mission_store.put(_m_attach)
    mission_lifecycle.attach_task(_m_attach.mission_id, _t_attach.task_id)

bench("attach_task (with store)", _attach, reps=100, target_p95_ms=1.0)

_m_lc = mission_lifecycle.create_mission_obj("LC")
mission_lifecycle.attach_task(_m_lc.mission_id, "some-task")

def _pause_resume():
    m = create_mission("PR")
    m.state = MissionState.active
    mission_store.put(m)
    mission_lifecycle.pause(m.mission_id)
    mission_lifecycle.resume(m.mission_id)
    mission_store.remove(m.mission_id)

bench("pause + resume cycle", _pause_resume, target_p95_ms=1.0)


section("2. Store")

_bench_m = create_mission("BenchGet")
mission_store.put(_bench_m)

def _store_get():
    mission_store.get(_bench_m.mission_id)

bench("mission_store.get (hit)", _store_get, target_p95_ms=0.1)
bench("mission_store.get (miss)", lambda: mission_store.get("ghost-id"), target_p95_ms=0.1)

def _find_by_task():
    mission_store.find_by_task("some-task")

bench("find_by_task (small store)", _find_by_task, target_p95_ms=0.5)


section("3. Affinity")

from app.mission.affinity import _extract_keywords, _jaccard, score_pair

bench("_extract_keywords (12-word query)", lambda: _extract_keywords("find the cheapest flight from London to NYC in December"), target_p95_ms=1.0)
bench("_jaccard (medium sets)", lambda: _jaccard({"flight","hotel","travel","cheap","London","NYC"}, {"booking","airline","flights","travel","hotel","London"}), target_p95_ms=0.1)
bench("score_pair (two queries)", lambda: score_pair("book cheap flight to Paris", "cheapest flights Paris"), target_p95_ms=1.0)

# Populate 20 active missions for find_matching_mission benchmark
mission_store._reset_for_testing()
mission_analytics._reset_for_testing()
for i in range(20):
    mc = mission_lifecycle.create_mission_obj(f"Travel Mission {i}", "book flights and hotels")
    t_mc = _put_task(f"find flights trip {i}")
    mission_lifecycle.attach_task(mc.mission_id, t_mc.task_id)

_probe_task = _put_task("find flights to Paris cheap")
bench("find_matching_mission (20 active missions)", lambda: mission_affinity.find_matching_mission(_probe_task), target_p95_ms=5.0)

mission_store._reset_for_testing()
mission_analytics._reset_for_testing()


section("4. Analytics")

bench("analytics.get_analytics()", lambda: mission_analytics.get_analytics(), target_p95_ms=0.5)
bench("analytics.record_mission_created()", lambda: mission_analytics.record_mission_created(), target_p95_ms=0.5)


section("5. Memory, Context, Timeline")

_m_perf = mission_lifecycle.create_mission_obj("Perf Mission", "build context for bench")
_tasks_perf = []
for i in range(3):
    t = _put_task(f"task query {i}")
    t.entities = {f"entity_{i}": f"val_{i}"}
    t.current_goal = f"Goal {i}"
    t.research_report = {"executive_summary": f"Summary {i}", "key_findings": [f"finding_{i}"], "confidence_score": 0.8}
    t.execution_plan = {"workflow_type": "automation", "confidence": 0.9}
    t.approvals.append(ApprovalRecord(f"appr-{i}", t.task_id, f"action_{i}", "SAFE", ApprovalStatus.approved))
    mission_lifecycle.attach_task(_m_perf.mission_id, t.task_id)
    _tasks_perf.append(t)

bench("memory_build (3 tasks)", lambda: mission_memory.build(_m_perf, _tasks_perf), target_p95_ms=5.0)
bench("context_registry (3 tasks)", lambda: context_registry.get_context(_m_perf.mission_id), target_p95_ms=10.0)
bench("timeline_build (3 tasks)", lambda: mission_timeline.build(_m_perf, _tasks_perf), target_p95_ms=5.0)


section("6. Bootstrap")

_t_boot = _tasks_perf[0]
bench("enrich_task_bootstrap", lambda: mission_bootstrap.enrich_task_bootstrap(_t_boot.task_id, _m_perf.mission_id), target_p95_ms=10.0)
bench("enrich_handoff_payload", lambda: mission_bootstrap.enrich_handoff_payload({"pre_filled_facts": {}}, _m_perf.mission_id), target_p95_ms=5.0)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"\n{'='*70}")
print("  All benchmarks complete. Review SLOW markers above.")
print(f"{'='*70}")

mission_store._reset_for_testing()
mission_analytics._reset_for_testing()
