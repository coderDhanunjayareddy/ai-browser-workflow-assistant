"""
V4.6 Unified Task Persistence + Workflow Bootstrap Consumption
Validation Suite

Validates all 10 V4.6 components end-to-end in one script.
Run: python -X utf8 validate_v46.py
Exit code: 0 = all pass, 1 = failures
"""
import sys
import traceback
from datetime import datetime

# ── Isolation: SQLite in-memory with StaticPool ───────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
import app.models.db  # noqa: F401
from app.core.config import settings

_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(bind=_engine)
_factory = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

from app.unified import persistence as task_persistence
from app.unified import timeline_persistence, approval_persistence
from app.unified import snapshot as snap_system
from app.unified import restoration as task_restoration
from app.unified import store as task_store
from app.unified import analytics as task_analytics
from app.unified.bootstrap_consumer import WorkflowBootstrapConsumer
from app.unified import prefill as prefill_layer
from app.unified.models import (
    UnifiedTask, TaskState, TaskTimeline, TimelineEvent, TimelineEventType,
    ApprovalRecord, ApprovalStatus,
)

task_persistence._set_session_factory(_factory)
timeline_persistence._set_session_factory(_factory)
approval_persistence._set_session_factory(_factory)
snap_system._set_session_factory(_factory)

settings.unified_task_persistence = True

# ── Test harness ──────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0
_checks: list[tuple[bool, str]] = []


def check(label: str, cond: bool) -> None:
    global PASS, FAIL
    _checks.append((cond, label))
    if cond:
        PASS += 1
        print(f"  [OK]  {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n  {title}\n{'=' * 60}")


def _make_task(task_id, conv="c1", state=TaskState.researching):
    t = UnifiedTask(task_id=task_id, conversation_id=conv, original_query="book a flight")
    t.state = state
    t.entities = {"destination": "NYC", "date": "2025-12-01"}
    t.research_report = {
        "executive_summary": "5 flights found",
        "key_findings": ["AA $180"],
        "recommended_actions": ["Book AA"],
        "confidence_score": 0.87,
    }
    t.execution_plan = {
        "workflow_type": "flight_booking",
        "approval_level": "REQUIRES_APPROVAL",
        "confidence": 0.85,
        "missing_inputs": ["passenger"],
        "recommended_next_action": "fill_form",
    }
    return t


def _wipe():
    with _factory() as db:
        from app.models.db import (
            UnifiedTaskRecord, TaskTimelineRecord,
            TaskApprovalRecord, TaskSnapshotRecord,
        )
        db.query(TaskSnapshotRecord).delete()
        db.query(TaskApprovalRecord).delete()
        db.query(TaskTimelineRecord).delete()
        db.query(UnifiedTaskRecord).delete()
        db.commit()
    task_store._reset_for_testing()


# ══════════════════════════════════════════════════════════════════════════════
# Component 1: Persistent Unified Task Store
# ══════════════════════════════════════════════════════════════════════════════
section("1. Persistent Unified Task Store")
_wipe()
try:
    t = _make_task("v1", "c1")
    task_persistence.save(t)

    loaded = task_persistence.load("v1")
    check("save() then load() returns a task", loaded is not None)
    check("task_id preserved", loaded.task_id == "v1")
    check("conversation_id preserved", loaded.conversation_id == "c1")
    check("original_query preserved", loaded.original_query == "book a flight")
    check("entities round-trip", loaded.entities.get("destination") == "NYC")
    check("execution_plan round-trip", loaded.execution_plan.get("workflow_type") == "flight_booking")
    check("research_report round-trip", "5 flights" in (loaded.research_report or {}).get("executive_summary", ""))

    t2 = _make_task("v2", "c2")
    t2.state = TaskState.completed
    task_persistence.save(t2)
    check("load_by_conversation finds task", task_persistence.load_by_conversation("c1") is not None)
    check("load_active excludes completed", all(x.task_id != "v2" for x in task_persistence.load_active()))

    deleted = task_persistence.delete("v1")
    check("delete() returns True", deleted)
    check("deleted task not loadable", task_persistence.load("v1") is None)
    check("delete non-existent returns False", not task_persistence.delete("no-such-task"))
except Exception:
    traceback.print_exc()
    check("Component 1: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 2: Persistent Timeline
# ══════════════════════════════════════════════════════════════════════════════
section("2. Persistent Timeline")
_wipe()
try:
    t = _make_task("t2", "c2")
    task_persistence.save(t)

    import uuid
    ev1 = TimelineEvent(
        event_id=str(uuid.uuid4())[:8],
        event_type=TimelineEventType.user_message,
        task_id="t2",
        data={"msg": "hi"},
    )
    ev2 = TimelineEvent(
        event_id=str(uuid.uuid4())[:8],
        event_type=TimelineEventType.research_started,
        task_id="t2",
        data={"topic": "flights"},
    )
    timeline_persistence.save_event(ev1)
    timeline_persistence.save_event(ev2)

    loaded_tl = timeline_persistence.load_timeline("t2")
    check("save_event() + load_timeline() returns events", len(loaded_tl.events) == 2)
    check("event_id preserved", loaded_tl.events[0].event_id == ev1.event_id)
    check("event_type preserved", any(e.event_type == TimelineEventType.research_started for e in loaded_tl.events))
    check("data preserved", loaded_tl.events[0].data.get("msg") == "hi" or
          any(e.data.get("msg") == "hi" for e in loaded_tl.events))

    # idempotency
    timeline_persistence.save_event(ev1)
    loaded_tl2 = timeline_persistence.load_timeline("t2")
    check("save_event is idempotent (no duplicate)", len(loaded_tl2.events) == 2)

    count = timeline_persistence.delete_events("t2")
    check("delete_events() removes all", count == 2)
    check("load_timeline after delete returns empty", len(timeline_persistence.load_timeline("t2").events) == 0)

    check("load_timeline for unknown task returns empty", len(timeline_persistence.load_timeline("unknown-t2-99").events) == 0)
except Exception:
    traceback.print_exc()
    check("Component 2: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 3: Persistent Approval Center
# ══════════════════════════════════════════════════════════════════════════════
section("3. Persistent Approval Center")
_wipe()
try:
    t = _make_task("t3", "c3")
    task_persistence.save(t)

    rec = ApprovalRecord(
        approval_id="a3-1",
        task_id="t3",
        action="click buy",
        risk_level="HIGH_RISK",
        status=ApprovalStatus.pending,
    )
    approval_persistence.save(rec)

    loaded_recs = approval_persistence.load_all("t3")
    check("save() + load_all() returns record", len(loaded_recs) == 1)
    check("approval_id preserved", loaded_recs[0].approval_id == "a3-1")
    check("action preserved", loaded_recs[0].action == "click buy")
    check("status round-trip PENDING", loaded_recs[0].status == ApprovalStatus.pending)

    rec.status = ApprovalStatus.approved
    rec.resolution_note = "user approved"
    approval_persistence.save(rec)
    updated = approval_persistence.load_all("t3")
    check("upsert updates status to APPROVED", updated[0].status == ApprovalStatus.approved)
    check("resolution_note preserved", "approved" in updated[0].resolution_note)

    deleted_count = approval_persistence.delete_all("t3")
    check("delete_all() removes all records", deleted_count == 1)
    check("load_all after delete returns empty", approval_persistence.load_all("t3") == [])
except Exception:
    traceback.print_exc()
    check("Component 3: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 4: Workflow Bootstrap Consumption
# ══════════════════════════════════════════════════════════════════════════════
section("4. Workflow Bootstrap Consumption")
_wipe()
try:
    t = _make_task("t4", "c4", TaskState.ready_for_workflow)
    task_store.put(t)

    consumer = WorkflowBootstrapConsumer()
    ctx = consumer.consume(t)

    check("consume() returns context", ctx is not None)
    check("task_id matches", ctx.task_id == "t4")
    check("entities populated", ctx.entities.get("destination") == "NYC")
    check("research_summary from report", "5 flights" in ctx.research_summary)
    check("key_findings from report", "AA $180" in ctx.key_findings)
    check("workflow_type from plan", ctx.workflow_type == "flight_booking")
    check("approval_level from plan", ctx.approval_level == "REQUIRES_APPROVAL")
    check("missing_inputs from plan", "passenger" in ctx.missing_inputs)
    check("recommended_next_action from plan", ctx.recommended_next_action == "fill_form")
    check("confidence from plan", ctx.confidence == 0.85)
    check("is_ready True when context exists", ctx.is_ready is True)
    check("latency_ms under 10", ctx.latency_ms < 10)

    facts = ctx.as_bootstrap_facts()
    check("as_bootstrap_facts includes entities", "destination" in facts)
    check("as_bootstrap_facts includes goal", "goal" in facts or "workflow_type" in facts)

    payload = {"session_id": "s1"}
    enriched = consumer.enrich_handoff_payload(t, payload)
    check("enrich_handoff_payload adds task_id", enriched["task_id"] == "t4")
    check("enrich_handoff_payload preserves existing keys", enriched["session_id"] == "s1")

    empty_t = UnifiedTask(task_id="empty-t4", conversation_id="empty-c4")
    empty_ctx = consumer.consume(empty_t)
    check("is_ready False when no context", empty_ctx.is_ready is False)
except Exception:
    traceback.print_exc()
    check("Component 4: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 5: Workflow Prefill Layer
# ══════════════════════════════════════════════════════════════════════════════
section("5. Workflow Prefill Layer")
_wipe()
try:
    t = _make_task("t5", "c5", TaskState.ready_for_workflow)
    task_store.put(t)
    t.current_goal = "book cheapest NYC flight"

    payload = prefill_layer.build(t)
    check("build() returns payload", payload is not None)
    check("task_id matches", payload.task_id == "t5")
    check("title from goal", "NYC" in payload.title or "cheapest" in payload.title)
    check("goal populated", payload.goal == "book cheapest NYC flight")
    check("entities passed through", payload.entities.get("destination") == "NYC")
    check("readiness_state READY for ready_for_workflow", payload.readiness_state == "READY")
    check("approval_classification from plan", payload.approval_classification == "REQUIRES_APPROVAL")
    check("workflow_type from plan", payload.workflow_type == "flight_booking")
    check("missing_inputs from plan", "passenger" in payload.missing_inputs)
    check("research_summary from report", "5 flights" in payload.research_summary)
    check("key_findings from report", "AA $180" in payload.key_findings)
    check("latency_ms under 10", payload.latency_ms < 10)
    check("pre_filled_facts has destination", payload.pre_filled_facts.get("destination") == "NYC")

    task_store.put(t)
    by_id = prefill_layer.build_by_task_id("t5")
    check("build_by_task_id finds task", by_id is not None)
    check("build_by_task_id returns None for unknown", prefill_layer.build_by_task_id("unknown-t5") is None)
except Exception:
    traceback.print_exc()
    check("Component 5: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 6: Unified Task Restoration
# ══════════════════════════════════════════════════════════════════════════════
section("6. Unified Task Restoration")
_wipe()
try:
    # Fast path
    t_mem = UnifiedTask(task_id="t6-mem", conversation_id="c6-mem")
    task_store.put(t_mem)
    restored_fast = task_restoration.restore("t6-mem")
    check("restore() fast path returns task", restored_fast is not None)
    check("fast path task_id correct", restored_fast.task_id == "t6-mem")

    # Slow path
    t_db = _make_task("t6-db", "c6-db")
    task_persistence.save(t_db)
    ev = TimelineEvent(
        event_id=str(uuid.uuid4())[:8],
        event_type=TimelineEventType.user_message,
        task_id="t6-db",
        data={"msg": "hello"},
    )
    timeline_persistence.save_event(ev)
    rec = ApprovalRecord("a6-1", "t6-db", "click", "SAFE")
    approval_persistence.save(rec)

    restored_slow = task_restoration.restore("t6-db")
    check("restore() slow path from DB", restored_slow is not None)
    check("slow path task_id correct", restored_slow.task_id == "t6-db")
    check("timeline hydrated", len(restored_slow.timeline.events) == 1)
    check("approvals hydrated", len(restored_slow.approvals) == 1)
    check("added to memory store", task_store.get("t6-db") is not None)

    # restore_by_conversation
    restored_conv = task_restoration.restore_by_conversation("c6-db")
    check("restore_by_conversation finds task", restored_conv is not None)

    check("restore nonexistent returns None", task_restoration.restore("no-such-t6") is None)
    check("restore_by_conversation nonexistent returns None",
          task_restoration.restore_by_conversation("no-such-conv") is None)
except Exception:
    traceback.print_exc()
    check("Component 6: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 7: Task Snapshot System
# ══════════════════════════════════════════════════════════════════════════════
section("7. Task Snapshot System")
_wipe()
try:
    t = _make_task("t7", "c7")
    task_persistence.save(t)

    sid = snap_system.create(t, "research_complete")
    check("create() returns snapshot_id", isinstance(sid, str) and len(sid) > 0)

    sid2 = snap_system.create(t, "workflow_prepared")
    check("second snapshot created", sid2 is not None)

    latest = snap_system.load_latest("t7")
    check("load_latest() returns most recent", latest is not None)
    check("load_latest() returns a snapshot", latest is not None)
    check("latest has snapshot_id", "snapshot_id" in latest)
    check("latest has created_at", "created_at" in latest)
    check("entities in snapshot", latest.get("entities", {}).get("destination") == "NYC")
    check("research_report in snapshot", "5 flights" in (latest.get("research_report") or {}).get("executive_summary", ""))
    check("task_state captured", latest.get("task_state") is not None)
    check("timeline_length captured", "timeline_length" in latest)

    all_snaps = snap_system.load_all("t7")
    check("load_all() returns 2 snapshots", len(all_snaps) == 2)
    all_triggers = {s["trigger"] for s in all_snaps}
    check("load_all has both triggers", all_triggers == {"research_complete", "workflow_prepared"})

    check("count() returns 2", snap_system.count("t7") == 2)
    check("count() returns 0 for unknown task", snap_system.count("no-such-t7") == 0)
    check("load_latest() None for unknown task", snap_system.load_latest("no-such-t7") is None)
    check("load_all() empty for unknown task", snap_system.load_all("no-such-t7") == [])

    check("invalid trigger returns None", snap_system.create(t, "not_a_trigger") is None)

    for trigger in snap_system.SNAPSHOT_TRIGGERS:
        check(f"valid trigger '{trigger}' works",
              snap_system.create(_make_task(f"trig-{trigger}", f"c-{trigger}"),
                                 trigger) is not None
              if (task_persistence.save(_make_task(f"trig-{trigger}", f"c-{trigger}")), True)[1]
              else False)
except Exception:
    traceback.print_exc()
    check("Component 7: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 8: Unified Analytics Expansion
# ══════════════════════════════════════════════════════════════════════════════
section("8. Unified Analytics Expansion")
_wipe()
try:
    task_analytics._reset_for_testing()

    task_analytics.record_persisted_task()
    task_analytics.record_persisted_task()
    task_analytics.record_persisted_task()

    task_analytics.record_restored_task(12)
    task_analytics.record_restored_task(8)

    task_analytics.record_restoration_hit(2)

    task_analytics.record_snapshot_created()
    task_analytics.record_snapshot_created()
    task_analytics.record_snapshot_created()
    task_analytics.record_snapshot_created()

    task_analytics.record_workflow_resumed()

    stats = task_analytics.get_analytics()
    check("persisted_tasks counter", stats["persisted_tasks"] == 3)
    check("restored_tasks counter", stats["restored_tasks"] == 2)
    check("restoration_hits counter", stats["restoration_hits"] == 1)
    check("snapshot_count counter", stats["snapshot_count"] == 4)
    check("workflow_resumes counter", stats["workflow_resumes"] == 1)
    # (12 + 8 + 2) // (2 restored + 1 hit) == 7
    check("average_restoration_latency_ms computed", stats["average_restoration_latency_ms"] == 7)
    check("approval_completion_rate present", "approval_completion_rate" in stats)
    check("workflow_resume_rate present", "workflow_resume_rate" in stats)
    check("existing analytics keys still present", "total_tasks" in stats)
    check("research_to_workflow_conversion still present", "research_to_workflow_conversion" in stats)
except Exception:
    traceback.print_exc()
    check("Component 8: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 9: Debugging Center — Unified Task Inspector
# ══════════════════════════════════════════════════════════════════════════════
section("9. Debugging Center — Unified Task Inspector")
_wipe()
try:
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    t = _make_task("t9", "c9", TaskState.ready_for_workflow)
    task_store.put(t)
    task_persistence.save(t)

    resp = client.get(f"/unified/tasks/t9/inspect")
    check("GET /unified/tasks/{id}/inspect returns 200", resp.status_code == 200)
    check("inspect response has task_id", resp.json().get("task_id") == "t9")
    check("inspect response has state", resp.json().get("state") is not None)

    resp404 = client.get("/unified/tasks/no-such-inspect/inspect")
    check("inspect 404 for unknown task", resp404.status_code == 404)

    # DB-only task (not in memory)
    t_db = _make_task("t9-db", "c9-db")
    task_persistence.save(t_db)
    resp_db = client.get("/unified/tasks/t9-db/inspect")
    check("inspect restores from DB", resp_db.status_code == 200)
    check("inspect DB restoration task_id", resp_db.json().get("task_id") == "t9-db")
except Exception:
    traceback.print_exc()
    check("Component 9: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Component 10: Migration Strategy
# ══════════════════════════════════════════════════════════════════════════════
section("10. Migration Strategy — Feature Flag + Additive-Only")
_wipe()
try:
    # Verify no-op when flag is disabled
    settings.unified_task_persistence = False
    task_persistence._reset_session_factory()  # point to real DB (disabled, no-op)

    t_noop = _make_task("t10", "c10")
    task_persistence.save(t_noop)  # should no-op
    loaded_noop = task_persistence.load("t10")
    check("save is no-op when flag=False", loaded_noop is None)

    snap_noop = snap_system.create(t_noop, "research_complete")
    check("snapshot is no-op when flag=False", snap_noop is None)

    restored_noop = task_restoration.restore("t10")
    check("restore returns None when flag=False and no memory", restored_noop is None)

    # Re-enable
    settings.unified_task_persistence = True
    task_persistence._set_session_factory(_factory)
    snap_system._set_session_factory(_factory)

    t10 = _make_task("t10-enabled", "c10-enabled")
    task_persistence.save(t10)
    check("save works when flag=True", task_persistence.load("t10-enabled") is not None)

    # V4.5 style tasks (no persistence) still work
    t_v45 = UnifiedTask(task_id="t10-v45", conversation_id="c10-v45")
    task_store.put(t_v45)
    check("V4.5 in-memory tasks unaffected", task_store.get("t10-v45") is not None)

    # New ORM tables don't modify existing tables (additive only)
    from app.models.db import UnifiedTaskRecord, TaskTimelineRecord, TaskApprovalRecord, TaskSnapshotRecord
    check("UnifiedTaskRecord table exists", hasattr(UnifiedTaskRecord, '__tablename__'))
    check("TaskTimelineRecord table exists", hasattr(TaskTimelineRecord, '__tablename__'))
    check("TaskApprovalRecord table exists", hasattr(TaskApprovalRecord, '__tablename__'))
    check("TaskSnapshotRecord table exists", hasattr(TaskSnapshotRecord, '__tablename__'))
    check("All tables have correct names", all([
        UnifiedTaskRecord.__tablename__ == "unified_tasks",
        TaskTimelineRecord.__tablename__ == "unified_task_timeline",
        TaskApprovalRecord.__tablename__ == "unified_task_approvals",
        TaskSnapshotRecord.__tablename__ == "unified_task_snapshots",
    ]))
except Exception:
    traceback.print_exc()
    check("Component 10: no unexpected exception", False)

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 60}")
print(f"  V4.6 Validation Summary")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'=' * 60}")
print(f"  Total checks : {PASS + FAIL}")
print(f"  Passed       : {PASS}")
print(f"  Failed       : {FAIL}")
print(f"{'=' * 60}")

if FAIL > 0:
    print("\n  Failed checks:")
    for ok, label in _checks:
        if not ok:
            print(f"    - {label}")

sys.exit(0 if FAIL == 0 else 1)
