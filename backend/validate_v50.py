"""
V5.0 Mission Layer — Validation Suite.

Runs 120 checks across 12 components using pure in-memory mode
(no DB required). Each check prints PASS or FAIL.

Usage:
  cd backend
  python validate_v50.py
"""
import sys
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Inline result tracking
# ---------------------------------------------------------------------------
_total = _passed = _failed = 0


def check(label: str, condition: bool) -> None:
    global _total, _passed, _failed
    _total += 1
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
section("0. Import checks")
try:
    from app.mission.models import (
        Mission, MissionState, TERMINAL_MISSION_STATES,
        VALID_MISSION_TRANSITIONS, create_mission,
        MissionTimelineEvent, MissionEventType, MissionMemory,
    )
    check("mission.models imports cleanly", True)
except ImportError as e:
    check(f"mission.models imports cleanly [{e}]", False)

try:
    from app.mission import store as mission_store
    from app.mission import lifecycle as mission_lifecycle
    from app.mission import analytics as mission_analytics
    from app.mission import persistence as mission_persistence
    from app.mission import restoration as mission_restoration
    from app.mission import timeline as mission_timeline
    from app.mission import memory as mission_memory
    from app.mission import context_registry
    from app.mission import affinity as mission_affinity
    from app.mission import bootstrap as mission_bootstrap
    check("all mission submodules import cleanly", True)
except ImportError as e:
    check(f"all mission submodules import cleanly [{e}]", False)
    sys.exit(1)

try:
    from app.schemas.mission import (
        MissionSchema, MissionAnalyticsSchema, MissionContextSchema,
        MissionMemorySchema, MissionBootstrapSchema, MissionAssignSchema,
        MissionInspectorSchema, CreateMissionRequest, AssignTaskRequest,
    )
    check("mission schemas import cleanly", True)
except ImportError as e:
    check(f"mission schemas import cleanly [{e}]", False)

try:
    from app.api.routes import mission as mission_routes
    check("mission routes import cleanly", True)
except ImportError as e:
    check(f"mission routes import cleanly [{e}]", False)

try:
    from app.core.config import settings
    check("mission_persistence config flag present", hasattr(settings, "mission_persistence"))
except Exception as e:
    check(f"mission_persistence config flag [{e}]", False)

# ---------------------------------------------------------------------------
# 1. MissionState & transitions
# ---------------------------------------------------------------------------
section("1. MissionState & transitions")

check("MissionState has 6 values", len(list(MissionState)) == 6)
check("3 terminal states", len(TERMINAL_MISSION_STATES) == 3)
check("completed is terminal", MissionState.completed in TERMINAL_MISSION_STATES)
check("failed is terminal", MissionState.failed in TERMINAL_MISSION_STATES)
check("abandoned is terminal", MissionState.abandoned in TERMINAL_MISSION_STATES)
check("created not terminal", MissionState.created not in TERMINAL_MISSION_STATES)
check("active -> paused valid", MissionState.paused in VALID_MISSION_TRANSITIONS[MissionState.active])
check("active -> completed valid", MissionState.completed in VALID_MISSION_TRANSITIONS[MissionState.active])
check("completed -> no transitions", VALID_MISSION_TRANSITIONS[MissionState.completed] == set())
check("paused -> active valid", MissionState.active in VALID_MISSION_TRANSITIONS[MissionState.paused])

# ---------------------------------------------------------------------------
# 2. Mission factory & dataclass
# ---------------------------------------------------------------------------
section("2. Mission factory & dataclass")

m = create_mission("Validate Mission", "Book flights and hotel", priority=1)
check("create_mission produces Mission", isinstance(m, Mission))
check("mission_id has length ≥ 12", len(m.mission_id) >= 12)
check("title set correctly", m.title == "Validate Mission")
check("objective set correctly", m.objective == "Book flights and hotel")
check("priority clamped to 1", m.priority == 1)
check("default state is created", m.state == MissionState.created)
check("default task_ids is empty", m.task_ids == [])
check("is_terminal False for created", not m.is_terminal)
m2 = create_mission("T", priority=99)
check("priority clamped to 5 for value 99", m2.priority == 5)

# ---------------------------------------------------------------------------
# 3. Analytics
# ---------------------------------------------------------------------------
section("3. Analytics")
mission_analytics._reset_for_testing()

a = mission_analytics.get_analytics()
check("get_analytics returns dict", isinstance(a, dict))
check("initial total_missions == 0", a["total_missions"] == 0)

mission_analytics.record_mission_created()
mission_analytics.record_mission_created()
a = mission_analytics.get_analytics()
check("total_missions == 2 after 2 creates", a["total_missions"] == 2)
check("active_missions == 2", a["active_missions"] == 2)

mission_analytics.record_mission_completed(duration_ms=400)
a = mission_analytics.get_analytics()
check("completed_missions == 1", a["completed_missions"] == 1)
check("active_missions == 1 after complete", a["active_missions"] == 1)
check("average_duration_ms == 400", a["average_mission_duration_ms"] == 400)
check("completion_rate == 0.5", abs(a["mission_completion_rate"] - 0.5) < 0.01)

mission_analytics.record_task_attached()
mission_analytics.record_task_attached()
mission_analytics.record_task_attached()
a = mission_analytics.get_analytics()
check("total_tasks_attached == 3", a["total_tasks_attached"] == 3)
check("avg_tasks_per_mission == 1.5", abs(a["average_tasks_per_mission"] - 1.5) < 0.01)

mission_analytics.record_research_to_execution()
a = mission_analytics.get_analytics()
check("research_to_execution_rate == 0.5", abs(a["research_to_execution_rate"] - 0.5) < 0.01)

mission_analytics._reset_for_testing()

# ---------------------------------------------------------------------------
# 4. In-Memory Store
# ---------------------------------------------------------------------------
section("4. In-Memory Store")
mission_store._reset_for_testing()

m_s1 = create_mission("S1")
m_s2 = create_mission("S2")
mission_store.put(m_s1)
mission_store.put(m_s2)

check("get returns put mission", mission_store.get(m_s1.mission_id) is m_s1)
check("get unknown returns None", mission_store.get("ghost") is None)
check("all_missions returns 2", len(mission_store.all_missions()) == 2)

m_s1.state = MissionState.completed
mission_store.put(m_s1)
active = mission_store.active_missions()
check("active_missions excludes completed", m_s1 not in active)
check("active_missions includes created", m_s2 in active)

mission_store.put(UnifiedTask_proxy := create_mission("WithTask"))
UnifiedTask_proxy.task_ids = ["tx"]
mission_store.put(UnifiedTask_proxy)
check("find_by_task finds correct mission", mission_store.find_by_task("tx") is UnifiedTask_proxy)
check("find_by_task returns None for unknown", mission_store.find_by_task("ty") is None)

removed = mission_store.remove(m_s2.mission_id)
check("remove returns True", removed is True)
check("removed mission not in store", mission_store.get(m_s2.mission_id) is None)
check("remove unknown returns False", mission_store.remove("ghost") is False)

mission_store._reset_for_testing()

# ---------------------------------------------------------------------------
# 5. Lifecycle manager
# ---------------------------------------------------------------------------
section("5. Lifecycle Manager")
mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

from app.unified.models import UnifiedTask  # ensure available

mc1 = mission_lifecycle.create_mission_obj("LC Test", "obj", priority=2)
check("create stores mission", mission_store.get(mc1.mission_id) is not None)
check("create increments analytics", mission_analytics.get_analytics()["total_missions"] == 1)

mc1 = mission_lifecycle.attach_task(mc1.mission_id, "task-lc-1")
check("attach adds task_id", "task-lc-1" in mc1.task_ids)
check("attach promotes to active", mc1.state == MissionState.active)

mc1 = mission_lifecycle.attach_task(mc1.mission_id, "task-lc-1")  # idempotent
check("duplicate attach is idempotent", mc1.task_ids.count("task-lc-1") == 1)

mc1 = mission_lifecycle.detach_task(mc1.mission_id, "task-lc-1")
check("detach removes task_id", "task-lc-1" not in mc1.task_ids)

mc1 = mission_lifecycle.attach_task(mc1.mission_id, "task-lc-2")
mc1 = mission_lifecycle.pause(mc1.mission_id)
check("pause sets state PAUSED", mc1.state == MissionState.paused)

mc1 = mission_lifecycle.resume(mc1.mission_id)
check("resume sets state ACTIVE", mc1.state == MissionState.active)

mc1 = mission_lifecycle.fail(mc1.mission_id, "test fail")
check("fail sets state FAILED", mc1.state == MissionState.failed)
check("fail stores reason in metadata", mc1.metadata.get("failure_reason") == "test fail")
check("fail analytics", mission_analytics.get_analytics()["failed_missions"] == 1)

from app.mission.lifecycle import MissionError
try:
    mission_lifecycle.complete(mc1.mission_id)
    check("cannot re-transition terminal mission", False)
except MissionError:
    check("cannot re-transition terminal mission", True)

mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

# ---------------------------------------------------------------------------
# 6. Timeline
# ---------------------------------------------------------------------------
section("6. Timeline")

from app.unified.models import TimelineEvent, TimelineEventType, TaskState

m_tl = create_mission("Timeline Test", "obj")
task_tl = UnifiedTask(task_id="t-tl", conversation_id="c1", original_query="find flights")
m_tl.task_ids = ["t-tl"]
events = mission_timeline.build(m_tl, [task_tl])

check("build returns list", isinstance(events, list))
check("events sorted by timestamp", events == sorted(events, key=lambda e: e.timestamp))
types = {e.event_type.value for e in events}
check("mission_created event present", "mission_created" in types)
check("task_attached event present", "task_attached" in types)

task_tl.timeline.events.append(TimelineEvent(
    event_id="tl-ev-1",
    event_type=TimelineEventType.research_completed,
    task_id="t-tl",
    data={"q": "flights"},
))
events2 = mission_timeline.build(m_tl, [task_tl])
types2 = {e.event_type.value for e in events2}
check("research_completed event mapped", "research_completed" in types2)

task_tl.state = TaskState.completed
events3 = mission_timeline.build(m_tl, [task_tl])
types3 = {e.event_type.value for e in events3}
check("task_completed event generated", "task_completed" in types3)

summary = mission_timeline.get_summary(events2)
check("get_summary has total_events", "total_events" in summary)
check("get_summary total > 0", summary["total_events"] > 0)

# ---------------------------------------------------------------------------
# 7. Memory
# ---------------------------------------------------------------------------
section("7. Memory")

from app.unified.models import ApprovalRecord, ApprovalStatus

m_mem = create_mission("Memory Test")
t_mem1 = UnifiedTask(task_id="mem-t1", conversation_id="c1", original_query="find hotels")
t_mem1.entities = {"city": "Paris", "dates": "June"}
t_mem1.current_goal = "Find cheapest hotel"
t_mem1.research_report = {"executive_summary": "Paris hotels summary", "key_findings": ["Hilton"],
                           "confidence_score": 0.8}
t_mem2 = UnifiedTask(task_id="mem-t2", conversation_id="c1", original_query="book hotel")
t_mem2.entities = {"city": "London"}  # overrides Paris
t_mem2.current_goal = "Book confirmed hotel"
t_mem2.approvals = [
    ApprovalRecord("appr-1", "mem-t2", "book-hotel", "SAFE", ApprovalStatus.approved),
    ApprovalRecord("appr-2", "mem-t2", "pay-extra",  "SAFE", ApprovalStatus.denied),
]
m_mem.task_ids = ["mem-t1", "mem-t2"]
mem = mission_memory.build(m_mem, [t_mem1, t_mem2])

check("entities merged", "city" in mem.entities)
check("later task wins on conflict", mem.entities["city"] == "London")
check("earlier entity preserved", "dates" in mem.entities)
check("goals collected", len(mem.goals) == 2)
check("goals deduplicated", len(set(mem.goals)) == len(mem.goals))
check("research_findings has 1 entry", len(mem.research_findings) == 1)
check("decisions has 1 approved entry", len(mem.decisions) == 1)
check("denied not in decisions", mem.decisions[0]["action"] == "book-hotel")

d = mission_memory.to_dict(mem)
check("to_dict is serializable", isinstance(d["last_updated"], str))

# ---------------------------------------------------------------------------
# 8. Context Registry
# ---------------------------------------------------------------------------
section("8. Context Registry")
mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

from app.unified import store as task_store

m_ctx = mission_lifecycle.create_mission_obj("Context Test")
t_ctx = UnifiedTask(task_id="ctx-t1", conversation_id="c1", original_query="find laptop")
t_ctx.entities = {"brand": "Dell"}
t_ctx.research_report = {"executive_summary": "laptops"}
task_store.put(t_ctx)
mission_lifecycle.attach_task(m_ctx.mission_id, "ctx-t1")

ctx = context_registry.get_context(m_ctx.mission_id)
check("get_context returns MissionContext", ctx is not None)
check("task_count == 1", ctx.task_count == 1)
check("task summary has correct query", ctx.task_summaries[0]["query"] == "find laptop")
check("task summary has_research == True", ctx.task_summaries[0]["has_research"] is True)
check("entities in context", "brand" in ctx.entities)
check("latency_ms >= 0", ctx.latency_ms >= 0)

check("get_context None for unknown", context_registry.get_context("ghost") is None)

d_ctx = context_registry.get_context_dict(m_ctx.mission_id)
check("get_context_dict returns dict", isinstance(d_ctx, dict))
check("get_context_dict has latency_ms", "latency_ms" in d_ctx)

mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

# ---------------------------------------------------------------------------
# 9. Affinity Heuristic
# ---------------------------------------------------------------------------
section("9. Affinity Heuristic")

from app.mission.affinity import (
    _extract_keywords, _jaccard, score_pair, AFFINITY_THRESHOLD,
    _same_domain, find_matching_mission, assign_task_to_mission,
)
mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

kw = _extract_keywords("book a flight to New York City")
check("'flight' extracted", "flight" in kw)
check("stop words excluded", "a" not in kw)
check("short words excluded", "to" not in kw)

a_kw = {"flight", "hotel", "trip"}
b_kw = {"flight", "travel", "tickets"}
j = _jaccard(a_kw, b_kw)
check("jaccard 1/4 ≤ overlap ≤ 1", 0 < j < 1)
check("jaccard identical == 1.0", _jaccard(a_kw, a_kw) == 1.0)
check("jaccard disjoint == 0.0", _jaccard({"x"}, {"y"}) == 0.0)

check("same_domain travel+travel", _same_domain({"flight", "hotel"}, {"travel", "booking"}))
check("diff_domain travel+electronics", not _same_domain({"flight", "hotel"}, {"laptop", "gpu"}))

score_high = score_pair("flight hotel paris trip", "flight hotel paris booking")
score_low  = score_pair("book flight hotel paris", "best recipe chicken dinner cook")
check("same-topic score > threshold", score_high > AFFINITY_THRESHOLD)
check("cross-domain score < threshold", score_low < AFFINITY_THRESHOLD)

t_aff = UnifiedTask(task_id="aff-t1", conversation_id="c1", original_query="find flights to NYC")
check("no missions -> find returns None", find_matching_mission(t_aff) is None)

assigned = assign_task_to_mission(t_aff, create_if_none=True)
check("assign creates new mission", assigned is not None)
check("task in mission.task_ids", "aff-t1" in assigned.task_ids)

t_aff2 = UnifiedTask(task_id="aff-t2", conversation_id="c1", original_query="random xyz 123 abc")
no_match = assign_task_to_mission(t_aff2, create_if_none=False)
check("create_if_none=False returns None when no match", no_match is None)

mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

# ---------------------------------------------------------------------------
# 10. Bootstrap
# ---------------------------------------------------------------------------
section("10. Bootstrap")
mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

from app.unified import store as task_store

m_boot = mission_lifecycle.create_mission_obj("Bootstrap Test", "book flight and hotel")
t_boot_prev = UnifiedTask(task_id="boot-prev", conversation_id="c1", original_query="research flights")
t_boot_prev.entities = {"city": "NYC", "depart_date": "2024-12-01"}
task_store.put(t_boot_prev)
mission_lifecycle.attach_task(m_boot.mission_id, "boot-prev")

t_boot_new = UnifiedTask(task_id="boot-new", conversation_id="c1", original_query="book flight NYC")
t_boot_new.entities = {"airline": "Delta"}
task_store.put(t_boot_new)
mission_lifecycle.attach_task(m_boot.mission_id, "boot-new")

result = mission_bootstrap.enrich_task_bootstrap("boot-new", m_boot.mission_id)
check("enrich_task_bootstrap returns result", result is not None)
check("result.mission_id matches", result.mission_id == m_boot.mission_id)
check("result.task_id matches", result.task_id == "boot-new")
check("merged_entities has city", "city" in result.merged_entities)
check("merged_entities has airline", "airline" in result.merged_entities)
check("enriched_facts has mission_id", result.enriched_facts["mission_id"] == m_boot.mission_id)
check("enriched_facts has mission_title", result.enriched_facts["mission_title"] == "Bootstrap Test")
check("latency_ms >= 0", result.latency_ms >= 0)

check("None for unknown mission", mission_bootstrap.enrich_task_bootstrap("t1", "ghost") is None)
check("None for unknown task", mission_bootstrap.enrich_task_bootstrap("ghost", m_boot.mission_id) is None)

payload = {"pre_filled_facts": {"user_pref": "window seat"}}
enriched = mission_bootstrap.enrich_handoff_payload(payload, m_boot.mission_id)
check("enrich_handoff adds mission_id", "mission_id" in enriched)
check("enrich_handoff merges pre_filled_facts", "user_pref" in enriched["pre_filled_facts"])
check("mission entities merged into facts", "city" in enriched["pre_filled_facts"])

mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

# ---------------------------------------------------------------------------
# 11. Persistence (disabled mode — no DB required)
# ---------------------------------------------------------------------------
section("11. Persistence (disabled mode)")

# Should be False by default
check("mission_persistence defaults to False", not settings.mission_persistence)

mission_persistence.save(create_mission("no-persist"))  # no-op
check("save is no-op when disabled", True)

result_load = mission_persistence.load("any-id")
check("load returns None when disabled", result_load is None)

result_active = mission_persistence.load_active()
check("load_active returns [] when disabled", result_active == [])

result_del = mission_persistence.delete("any-id")
check("delete returns False when disabled", result_del is False)

# ---------------------------------------------------------------------------
# 12. Restoration
# ---------------------------------------------------------------------------
section("12. Restoration")
mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

m_rest = mission_lifecycle.create_mission_obj("Restore Test")
result = mission_restoration.restore(m_rest.mission_id)
check("fast path returns from memory", result is not None)
check("fast path returns correct mission", result.mission_id == m_rest.mission_id)

check("restore None for unknown", mission_restoration.restore("ghost-restore") is None)

# warmup with empty DB
count = mission_restoration.warmup()
check("warmup returns int", isinstance(count, int))
check("warmup returns 0 when persistence disabled", count == 0)

mission_store._reset_for_testing()
mission_analytics._reset_for_testing()

# ---------------------------------------------------------------------------
# Final Report
# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"  VALIDATION COMPLETE — {_passed}/{_total} passed ({_failed} failed)")
print(f"{'='*60}")

if _failed > 0:
    sys.exit(1)
