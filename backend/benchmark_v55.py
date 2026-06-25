"""
V5.5 Mission Intelligence Layer — Benchmarks.

Measures p95 latency for all intelligence components.
Run with: python benchmark_v55.py

Performance targets:
  readiness_scorer.compute()           < 0.1ms
  blocker_detector.detect()            < 1ms
  information_gap.analyze()            < 2ms
  workflow_recommender.recommend()     < 1ms
  next_action_planner.plan()           < 0.5ms
  state_advisor.advise()               < 0.5ms
  registry.get() (hit)                 < 0.1ms
  registry.get() (miss)                < 0.1ms
  registry.set()                       < 0.1ms
  engine.run() (cold, 0 tasks)         < 10ms
  engine.run() (warm, cached)          < 0.5ms
  engine.run() (cold, 4 tasks)         < 15ms
  analytics.get_analytics()            < 0.1ms
  full API GET /intelligence (0 tasks) < 25ms
  full API GET /intelligence (4 tasks) < 30ms
  full API GET /blockers               < 10ms
  full API GET /next-action            < 10ms
"""
import time
import statistics
import uuid
from datetime import datetime

REPS = 200


def bench(label: str, fn, reps: int = REPS, target_ms: float = None):
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    status = ""
    if target_ms is not None:
        status = "OK" if p95 <= target_ms else "SLOW"
    print(f"  {label:<50}  p50={p50:6.2f}ms  p95={p95:6.2f}ms  {status}")
    return p95


# ── Setup helpers ──────────────────────────────────────────────────────────────

def _ctx(task_summaries=None, title="order laptop", entities=None, approvals=None):
    from app.mission.context_registry import MissionContext
    from app.mission.models import MissionMemory
    summaries = task_summaries or []
    mem = MissionMemory(
        mission_id="m1", entities=entities or {}, goals=[],
        research_findings=[], execution_plans=[], decisions=[],
        last_updated=datetime.utcnow(),
    )
    return MissionContext(
        mission_id="m1", mission_title=title, mission_state="ACTIVE",
        priority=3, task_count=len(summaries), task_summaries=summaries,
        entities=entities or {}, goals=[], research_findings=[],
        execution_plans=[], approvals=approvals or [], memory=mem, latency_ms=0,
    )


def _ts(task_id="t1", state="COMPLETED", has_research=True, has_plan=False):
    return {"task_id": task_id, "state": state, "query": "q", "goal": None,
            "has_research": has_research, "has_plan": has_plan, "approval_count": 0}


def _dummy_report():
    from app.mission.intelligence.models import (
        MissionIntelligenceReport, MissionAdvisoryState, MissionNextAction,
    )
    return MissionIntelligenceReport(
        mission_id="m1", readiness_score=0.80, confidence=0.75,
        recommended_action="Act", suggested_workflow="purchase_workflow",
        blockers=[], missing_information=[], reasoning="Test",
        next_action=MissionNextAction(action="Act", reasoning="R", priority=1),
        advisory_state=MissionAdvisoryState.ready, workflow_recommendation=None,
        generated_at=datetime.utcnow(), latency_ms=5,
    )


# ── Reset state before benchmarks ─────────────────────────────────────────────
from app.mission import store as mission_store
from app.unified import store as task_store
from app.mission.intelligence import registry as intel_registry, analytics as intel_analytics

mission_store._reset_for_testing()
task_store._reset_for_testing()
intel_registry._reset_for_testing()
intel_analytics._reset_for_testing()

print("\n=== V5.5 Mission Intelligence Layer — Benchmarks ===\n")

# ── 1. Readiness Scorer ───────────────────────────────────────────────────────
print("Readiness Scorer:")
from app.mission.intelligence.readiness_scorer import compute, score_from_context

bench("compute() [4 tasks, all params]",
    lambda: compute(4, 3, 0, True, True, True, 1, 2),
    target_ms=0.1)

ctx_4 = _ctx([_ts("t1"), _ts("t2"), _ts("t3"), _ts("t4", has_plan=True)])
bench("score_from_context() [4 tasks]",
    lambda: score_from_context(ctx_4, blocker_count=1, missing_info_count=2),
    target_ms=0.5)

# ── 2. Blocker Detector ───────────────────────────────────────────────────────
print("\nBlocker Detector:")
from app.mission.intelligence import blocker_detector

ctx_0 = _ctx([])
bench("detect() [0 tasks]",
    lambda: blocker_detector.detect(ctx_0),
    target_ms=1)

ctx_2 = _ctx([_ts("t1"), _ts("t2", has_plan=True)])
bench("detect() [2 tasks, no blockers]",
    lambda: blocker_detector.detect(ctx_2),
    target_ms=1)

ctx_blocky = _ctx([_ts("t1", state="FAILED", has_research=False)])
bench("detect() [1 failed task, no research]",
    lambda: blocker_detector.detect(ctx_blocky),
    target_ms=1)

# ── 3. Information Gap Analyzer ───────────────────────────────────────────────
print("\nInformation Gap Analyzer:")
from app.mission.intelligence import information_gap

ctx_book = _ctx(task_summaries=[], title="book flight to Paris")
bench("analyze() [book flight, no entities]",
    lambda: information_gap.analyze(ctx_book),
    target_ms=2)

ctx_known = _ctx(task_summaries=[_ts()], title="order laptop", entities={"product_name": "Dell XPS"})
bench("analyze() [purchase, known entity]",
    lambda: information_gap.analyze(ctx_known),
    target_ms=2)

# ── 4. Workflow Recommender ───────────────────────────────────────────────────
print("\nWorkflow Recommender:")
from app.mission.intelligence import workflow_recommender

bench("recommend() [book flight]",
    lambda: workflow_recommender.recommend("Book flight to London", "", 0.80),
    target_ms=1)

bench("recommend() [unknown intent]",
    lambda: workflow_recommender.recommend("research laptops", "", 0.50),
    target_ms=1)

# ── 5. Next Action Planner ────────────────────────────────────────────────────
print("\nNext Action Planner:")
from app.mission.intelligence import next_action_planner
from app.mission.intelligence.models import MissionBlocker, BlockerSeverity

ctx_ready = _ctx([_ts(has_research=True, has_plan=True)])
bench("plan() [ready mission, no blockers]",
    lambda: next_action_planner.plan(ctx_ready, [], 0.85),
    target_ms=0.5)

crit_b = MissionBlocker(code="NO_RESEARCH", description="d", severity=BlockerSeverity.critical)
bench("plan() [critical blocker]",
    lambda: next_action_planner.plan(ctx_ready, [crit_b], 0.20),
    target_ms=0.5)

# ── 6. State Advisor ──────────────────────────────────────────────────────────
print("\nState Advisor:")
from app.mission.intelligence import state_advisor

bench("advise() [active, no blockers]",
    lambda: state_advisor.advise(ctx_4, [], 0.50),
    target_ms=0.5)

bench("advise() [ready]",
    lambda: state_advisor.advise(ctx_ready, [], 0.85),
    target_ms=0.5)

# ── 7. Registry ───────────────────────────────────────────────────────────────
print("\nRegistry:")
from app.mission.intelligence.registry import MissionIntelligenceRegistry

reg = MissionIntelligenceRegistry(ttl=60)
report = _dummy_report()
reg.set("bench_m", report)

bench("registry.get() [hit]",
    lambda: reg.get("bench_m"),
    target_ms=0.1)

bench("registry.get() [miss]",
    lambda: reg.get("no_such_mission"),
    target_ms=0.1)

bench("registry.set()",
    lambda: reg.set("bench_m", report),
    target_ms=0.1)

# ── 8. Engine ─────────────────────────────────────────────────────────────────
print("\nIntelligence Engine:")
from app.mission.intelligence import engine as intel_engine
from app.mission.lifecycle import create_mission_obj

mission_store._reset_for_testing()
task_store._reset_for_testing()
intel_registry._reset_for_testing()

m_empty = create_mission_obj("Benchmark empty")
bench("engine.run() [0 tasks, cold]",
    lambda: intel_engine.run(m_empty.mission_id, force_refresh=True),
    reps=100, target_ms=10)

# Warm (cached)
intel_engine.run(m_empty.mission_id)
bench("engine.run() [0 tasks, cached]",
    lambda: intel_engine.run(m_empty.mission_id),
    target_ms=0.5)

# 4-task mission
from app.unified.models import UnifiedTask, TaskState

m_4t = create_mission_obj("Order laptop - benchmark")
for i in range(4):
    t = UnifiedTask(
        task_id=str(uuid.uuid4())[:8], conversation_id="c1",
        original_query=f"research step {i}", state=TaskState.completed,
    )
    t.research_report = {"summary": f"Step {i} done.", "sources": [], "key_findings": []}
    if i == 3:
        t.execution_plan = {"workflow_type": "purchase_workflow"}
    task_store.put(t)
    from app.mission.lifecycle import attach_task
    attach_task(m_4t.mission_id, t.task_id)

bench("engine.run() [4 tasks, cold]",
    lambda: intel_engine.run(m_4t.mission_id, force_refresh=True),
    reps=100, target_ms=15)

# ── 9. Analytics ─────────────────────────────────────────────────────────────
print("\nAnalytics:")
from app.mission.intelligence import analytics as intel_analytics

bench("get_analytics()",
    lambda: intel_analytics.get_analytics(),
    target_ms=0.1)

bench("record_intelligence_run()",
    lambda: intel_analytics.record_intelligence_run(5),
    target_ms=0.1)

# ── 10. API Endpoints ─────────────────────────────────────────────────────────
print("\nAPI Endpoints (TestClient, includes routing + serialization):")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

# Create test missions via API
resp = client.post("/mission/", json={"title": "Bench mission empty"})
mid_empty = resp.json()["mission_id"]

bench("GET /mission/{id}/intelligence [0 tasks]",
    lambda: client.get(f"/mission/{mid_empty}/intelligence"),
    reps=100, target_ms=25)

bench("GET /mission/{id}/blockers [0 tasks]",
    lambda: client.get(f"/mission/{mid_empty}/blockers"),
    reps=100, target_ms=10)

bench("GET /mission/{id}/next-action [0 tasks]",
    lambda: client.get(f"/mission/{mid_empty}/next-action"),
    reps=100, target_ms=10)

resp_4t = client.post("/mission/", json={"title": "Bench mission 4 tasks"})
mid_4t = resp_4t.json()["mission_id"]
for ts in [t for tid in m_4t.task_ids if (t := task_store.get(tid))]:
    client.post(f"/mission/{mid_4t}/tasks/{ts.task_id}")

bench("GET /mission/{id}/intelligence [4 tasks, force_refresh]",
    lambda: client.get(f"/mission/{mid_4t}/intelligence?force_refresh=true"),
    reps=50, target_ms=30)

bench("GET /mission/intelligence/analytics",
    lambda: client.get("/mission/intelligence/analytics"),
    reps=100, target_ms=10)

print("\n=== Benchmarks complete ===\n")
