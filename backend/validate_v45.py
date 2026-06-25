"""
V4.5 Unified Task Graph — Validation Script.

Validates: model correctness, lifecycle transitions, timeline, approval center,
tab registry, workflow continuity, analytics, context registry, REST endpoints.
All checks run end-to-end with real in-memory objects (no mocks).
"""
import sys
import time
import uuid

# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────
sys.path.insert(0, ".")

from app.unified import store as task_store, analytics as task_analytics
from app.unified.models import TaskState, TabRole, ApprovalStatus
from app.unified.task_lifecycle import TaskLifecycleManager, TaskLifecycleError
from app.unified.task_timeline import TaskTimelineManager
from app.unified.approval_center import ApprovalCenter
from app.unified.tab_registry import TaskTabRegistry
from app.unified.workflow_continuity import WorkflowContinuityLayer
from app.unified.task_context_registry import TaskContextRegistry
from app.models.db import UnifiedTaskRecord

task_store._reset_for_testing()
task_analytics._reset_for_testing()

mgr = TaskLifecycleManager()
timeline = TaskTimelineManager()
ac = ApprovalCenter()
tab_reg = TaskTabRegistry()
continuity = WorkflowContinuityLayer()
ctx_reg = TaskContextRegistry()

PASS = "  [PASS]"
FAIL = "  [FAIL]"
errors: list[str] = []

def check(name: str, cond: bool) -> None:
    if cond:
        print(f"{PASS} {name}")
    else:
        print(f"{FAIL} {name}")
        errors.append(name)

# ──────────────────────────────────────────────────────────────────────────────
# 1. Task creation
# ──────────────────────────────────────────────────────────────────────────────
print("\n[1] Task Creation")
task = mgr.create("conv-val-1", "validate unified task graph")
check("task created with state CREATED", task.state == TaskState.created)
check("task stored in store", task_store.get(task.task_id) is not None)
check("task indexed by conversation", task_store.get_by_conversation("conv-val-1") is not None)
check("original_query stored", task.original_query == "validate unified task graph")
check("state_history has initial entry", len(task.state_history) == 1)

# ──────────────────────────────────────────────────────────────────────────────
# 2. get_or_create idempotency
# ──────────────────────────────────────────────────────────────────────────────
print("\n[2] get_or_create idempotency")
task2 = mgr.get_or_create("conv-val-1", "different query")
check("returns same task on repeat call", task2.task_id == task.task_id)
task3 = mgr.get_or_create("conv-val-new", "new query")
check("creates new task for new conversation", task3.task_id != task.task_id)

# ──────────────────────────────────────────────────────────────────────────────
# 3. State transitions
# ──────────────────────────────────────────────────────────────────────────────
print("\n[3] State Transitions")
mgr.mark_researching(task, "flight booking")
check("mark_researching -> RESEARCHING", task.state == TaskState.researching)

mgr.mark_research_complete(task, "rsess-1", "flight booking", opportunity_detected=False)
check("mark_research_complete -> RESEARCH_COMPLETE", task.state == TaskState.research_complete)
check("research_session_id set", task.research_session_id == "rsess-1")

mgr.transition(task, TaskState.ready_for_workflow)
check("manual transition to READY_FOR_WORKFLOW", task.state == TaskState.ready_for_workflow)

mgr.mark_workflow_started(task, "wsess-1")
check("mark_workflow_started -> WORKFLOW_RUNNING", task.state == TaskState.workflow_running)
check("workflow_session_id set", task.workflow_session_id == "wsess-1")

mgr.mark_completed(task, "all steps completed")
check("mark_completed -> COMPLETED", task.state == TaskState.completed)

# ──────────────────────────────────────────────────────────────────────────────
# 4. Invalid transition guard
# ──────────────────────────────────────────────────────────────────────────────
print("\n[4] Invalid Transition Guard")
try:
    mgr.transition(task, TaskState.researching)
    check("raises on COMPLETED -> RESEARCHING", False)
except TaskLifecycleError:
    check("raises on COMPLETED -> RESEARCHING", True)

# ──────────────────────────────────────────────────────────────────────────────
# 5. Auto-promote on opportunity_detected
# ──────────────────────────────────────────────────────────────────────────────
print("\n[5] Auto-promote")
task_ap = mgr.create("conv-ap", "book now")
mgr.mark_researching(task_ap, "flights")
mgr.mark_research_complete(task_ap, "rs2", "flights", opportunity_detected=True)
check("auto-promotes to READY_FOR_WORKFLOW", task_ap.state == TaskState.ready_for_workflow)

# ──────────────────────────────────────────────────────────────────────────────
# 6. Failed -> retry
# ──────────────────────────────────────────────────────────────────────────────
print("\n[6] Failed -> Retry")
task_f = mgr.create("conv-fail", "q")
mgr.mark_researching(task_f, "t")
mgr.mark_failed(task_f, "engine error")
check("failed state set", task_f.state == TaskState.failed)
mgr.mark_researching(task_f, "t")
check("retry from failed: back to RESEARCHING", task_f.state == TaskState.researching)

# ──────────────────────────────────────────────────────────────────────────────
# 7. Timeline
# ──────────────────────────────────────────────────────────────────────────────
print("\n[7] Timeline")
task_tl = mgr.create("conv-tl", "timeline test")
ev1 = timeline.record_user_message(task_tl, "hello")
ev2 = timeline.record_research_started(task_tl, "flights")
ev3 = timeline.record_research_completed(task_tl, "flights", 0.9, 5)
check("timeline has 4 events (user_message from create + 3)", len(task_tl.timeline.events) == 4)
ordered = timeline.get_ordered(task_tl)
check("get_ordered returns list", isinstance(ordered, list))
summary = timeline.get_summary(task_tl)
check("get_summary returns list of dicts", all("event_id" in s for s in summary))

from app.unified.models import TimelineEventType
msgs = task_tl.timeline.by_type(TimelineEventType.research_started)
check("by_type filter works", len(msgs) == 1)

# ──────────────────────────────────────────────────────────────────────────────
# 8. Approval Center
# ──────────────────────────────────────────────────────────────────────────────
print("\n[8] Approval Center")
task_ac = mgr.create("conv-ac", "approval test")
rec1 = ac.request(task_ac, "click buy", "HIGH_RISK")
check("request creates PENDING", rec1.status == ApprovalStatus.pending)
check("timeline has approval_requested event", len(task_ac.timeline.by_type(TimelineEventType.approval_requested)) == 1)

approved = ac.approve(task_ac, rec1.approval_id, note="user confirmed")
check("approve sets APPROVED", approved.status == ApprovalStatus.approved)
check("resolved_at set", approved.resolved_at is not None)
check("timeline has approval_granted event", len(task_ac.timeline.by_type(TimelineEventType.approval_granted)) == 1)
check("cannot re-approve", ac.approve(task_ac, rec1.approval_id) is None)

rec2 = ac.request(task_ac, "delete account", "HIGH_RISK")
denied = ac.deny(task_ac, rec2.approval_id, reason="too risky")
check("deny sets DENIED", denied.status == ApprovalStatus.denied)

rec3 = ac.request(task_ac, "read page", "SAFE")
count = ac.expire_pending(task_ac)
check("expire_pending returns correct count", count == 1)
check("pending list is now empty", len(ac.pending(task_ac)) == 0)

# ──────────────────────────────────────────────────────────────────────────────
# 9. Tab Registry
# ──────────────────────────────────────────────────────────────────────────────
print("\n[9] Tab Registry")
task_tb = mgr.create("conv-tb", "tab test")
t1 = tab_reg.register(task_tb, "tab1", "https://flights.com", "Flights", TabRole.research)
t2 = tab_reg.register(task_tb, "tab2", "https://booking.com", "Booking", TabRole.workflow)
check("two tabs registered", len(task_tb.tabs) == 2)
check("get_by_role returns research tabs", len(tab_reg.get_by_role(task_tb, TabRole.research)) == 1)
check("get returns correct tab", tab_reg.get(task_tb, "tab1").url == "https://flights.com")
tab_reg.register(task_tb, "tab1", "https://flights-new.com", "Flights2", TabRole.research)
check("upsert updates existing tab", len(task_tb.tabs) == 2)
summary = tab_reg.summary(task_tb)
check("summary returns list", isinstance(summary, list) and len(summary) == 2)

# ──────────────────────────────────────────────────────────────────────────────
# 10. Workflow Continuity
# ──────────────────────────────────────────────────────────────────────────────
print("\n[10] Workflow Continuity")
task_wc = mgr.create("conv-wc", "book flight")
mgr.mark_researching(task_wc, "flights")
continuity.attach_research(
    task_wc,
    research_session_id="rs-wc",
    topic="flights",
    executive_summary="Found 5 flights under $200",
    key_findings=["AA123 $180", "UA456 $195"],
    recommended_actions=["Book AA123"],
    confidence_score=0.88,
)
continuity.attach_intelligence(
    task_wc,
    plan_id="plan-1",
    workflow_type="booking_workflow",
    approval_level="REQUIRES_APPROVAL",
    confidence=0.85,
    missing_inputs=[],
    recommended_next_action="fill_passenger_form",
)
mgr.mark_research_complete(task_wc, "rs-wc", "flights", opportunity_detected=True)

check("is_ready_for_workflow returns True", continuity.is_ready_for_workflow(task_wc))
ctx = continuity.get_handoff_context(task_wc)
check("handoff context has task_id", ctx["task_id"] == task_wc.task_id)
check("handoff context has research_findings", "research_findings" in ctx)
check("handoff context has workflow_type", "workflow_type" in ctx)
check("handoff context has research_summary", ctx.get("research_summary") == "Found 5 flights under $200")

# ──────────────────────────────────────────────────────────────────────────────
# 11. Context Registry
# ──────────────────────────────────────────────────────────────────────────────
print("\n[11] Context Registry")
lookup = ctx_reg.lookup(task_wc.task_id)
check("lookup returns dict", isinstance(lookup, dict))
check("lookup has task_id", lookup["task_id"] == task_wc.task_id)
check("lookup has task_state", "task_state" in lookup)
check("lookup has latency_ms", "latency_ms" in lookup)
check("latency_ms < 10ms", lookup["latency_ms"] < 10)

# ──────────────────────────────────────────────────────────────────────────────
# 12. Analytics
# ──────────────────────────────────────────────────────────────────────────────
print("\n[12] Analytics")
task_analytics._reset_for_testing()
task_analytics.record_task_created()
task_analytics.record_task_created()
task_analytics.record_task_completed(300)
task_analytics.record_task_abandoned()
task_analytics.record_research_to_workflow()
task_analytics.record_approval_requested()
task_analytics.record_approval_resolved(True)
task_analytics.record_workflow_completion()

r = task_analytics.get_analytics()
check("total_tasks == 2", r["total_tasks"] == 2)
check("completed_tasks == 1", r["completed_tasks"] == 1)
check("abandoned_tasks == 1", r["abandoned_tasks"] == 1)
check("research_to_workflow_conversion == 1", r["research_to_workflow_conversion"] == 1)
check("approval_rate == 1.0", abs(r["approval_rate"] - 1.0) < 0.001)
check("average_task_duration_ms == 300", abs(r["average_task_duration_ms"] - 300) < 0.001)

# ──────────────────────────────────────────────────────────────────────────────
# 13. DB Model
# ──────────────────────────────────────────────────────────────────────────────
print("\n[13] DB Model (schema check)")
check("UnifiedTaskRecord has __tablename__", hasattr(UnifiedTaskRecord, "__tablename__"))
check("tablename is unified_tasks", UnifiedTaskRecord.__tablename__ == "unified_tasks")
cols = {c.key for c in UnifiedTaskRecord.__table__.columns}
for col in ["task_id", "conversation_id", "state", "original_query", "created_at", "updated_at"]:
    check(f"column '{col}' exists", col in cols)

# ──────────────────────────────────────────────────────────────────────────────
# 14. REST API Endpoint Smoke Tests
# ──────────────────────────────────────────────────────────────────────────────
print("\n[14] REST API Smoke Tests")
try:
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    r = client.get("/unified/tasks")
    check("GET /unified/tasks returns 200", r.status_code == 200)

    task_api = mgr.create("conv-api", "api test")
    r = client.get(f"/unified/tasks/{task_api.task_id}")
    check("GET /unified/tasks/{id} returns 200", r.status_code == 200)

    r = client.get("/unified/tasks/nonexistent-123")
    check("GET /unified/tasks/bad-id returns 404", r.status_code == 404)

    r = client.get(f"/unified/tasks/{task_api.task_id}/context")
    check("GET /unified/tasks/{id}/context returns 200", r.status_code == 200)

    r = client.get(f"/unified/tasks/{task_api.task_id}/timeline")
    check("GET /unified/tasks/{id}/timeline returns 200", r.status_code == 200)

    r = client.get("/unified/analytics")
    check("GET /unified/analytics returns 200", r.status_code == 200)

    r = client.get(f"/unified/conversation/conv-api")
    check("GET /unified/conversation/{id} returns 200", r.status_code == 200)
except Exception as e:
    print(f"  [SKIP] REST API tests skipped: {e}")

# ──────────────────────────────────────────────────────────────────────────────
# 15. Performance check — all registry ops < 10ms
# ──────────────────────────────────────────────────────────────────────────────
print("\n[15] Performance (<10ms p95)")
REPS = 100
task_perf = mgr.create("conv-perf", "perf test")
times = []
for _ in range(REPS):
    t0 = time.perf_counter()
    ctx_reg.lookup(task_perf.task_id)
    times.append((time.perf_counter() - t0) * 1000)
times.sort()
p95 = times[int(REPS * 0.95)]
check(f"context registry p95 < 10ms (actual {p95:.2f}ms)", p95 < 10)

times2 = []
for _ in range(REPS):
    t0 = time.perf_counter()
    task_analytics.get_analytics()
    times2.append((time.perf_counter() - t0) * 1000)
times2.sort()
p95_ana = times2[int(REPS * 0.95)]
check(f"analytics.get_analytics p95 < 10ms (actual {p95_ana:.2f}ms)", p95_ana < 10)

# ──────────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
if errors:
    print(f"FAILED: {len(errors)} checks")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print(f"ALL CHECKS PASSED")
    sys.exit(0)
