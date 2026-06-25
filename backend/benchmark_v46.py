"""
V4.6 Unified Task Persistence + Workflow Bootstrap Consumption
Benchmark Suite

Measures p50, p95, p99 latency for all V4.6 operations.
Run: python benchmark_v46.py
Exit code: 0 = all targets met, 1 = regressions
"""
import sys
import time
import statistics
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
import app.models.db  # noqa: F401
from app.core.config import settings

# ── Isolated SQLite setup ──────────────────────────────────────────────────────
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
from app.unified.bootstrap_consumer import WorkflowBootstrapConsumer, consume
from app.unified import prefill as prefill_layer
from app.unified.models import (
    UnifiedTask, TaskState, TimelineEvent, TimelineEventType,
    ApprovalRecord, ApprovalStatus,
)

task_persistence._set_session_factory(_factory)
timeline_persistence._set_session_factory(_factory)
approval_persistence._set_session_factory(_factory)
snap_system._set_session_factory(_factory)
settings.unified_task_persistence = True

# ── Performance targets (ms) ───────────────────────────────────────────────────
TARGETS: dict[str, float] = {
    "task_persistence_save":           10.0,
    "task_persistence_load":           10.0,
    "task_persistence_load_active":    50.0,
    "timeline_persistence_save_event": 10.0,
    "timeline_persistence_load":       25.0,
    "approval_persistence_save":       10.0,
    "approval_persistence_load_all":   10.0,
    "snapshot_create":                 15.0,
    "snapshot_load_latest":            10.0,
    "snapshot_load_all":               15.0,
    "restore_fast_path":                2.0,
    "restore_slow_path":               50.0,
    "restore_by_conversation":         50.0,
    "bootstrap_consume":               10.0,
    "bootstrap_consume_by_task_id":    10.0,
    "prefill_build":                   10.0,
    "prefill_build_by_task_id":        10.0,
}

REPS = 200
results: dict[str, list[float]] = {}
PASS = 0
FAIL = 0


def bench(name: str, fn, reps: int = REPS):
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    results[name] = times


def _make_task(task_id: str, conv: str = "c1") -> UnifiedTask:
    t = UnifiedTask(
        task_id=task_id,
        conversation_id=conv,
        original_query="book a flight",
        current_goal="book cheapest flight to NYC",
        state=TaskState.ready_for_workflow,
    )
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


print("V4.6 Benchmark Suite")
print(f"  {REPS} repetitions per operation")
print(f"  Targets: p95 < target_ms")
print()

# ── 1. Task persistence ────────────────────────────────────────────────────────
_wipe()
_base = _make_task("bench-base", "c-base")
task_persistence.save(_base)

_counter = [0]
def _save():
    _counter[0] += 1
    t = _make_task(f"b-s-{_counter[0]}", f"cs{_counter[0]}")
    task_persistence.save(t)

bench("task_persistence_save", _save)
bench("task_persistence_load", lambda: task_persistence.load("bench-base"))
bench("task_persistence_load_active", lambda: task_persistence.load_active())

# ── 2. Timeline persistence ────────────────────────────────────────────────────
_ev_counter = [0]
def _save_event():
    _ev_counter[0] += 1
    ev = TimelineEvent(
        event_id=str(uuid.uuid4())[:8],
        event_type=TimelineEventType.user_message,
        task_id="bench-base",
        data={"msg": f"hello {_ev_counter[0]}"},
    )
    timeline_persistence.save_event(ev)

bench("timeline_persistence_save_event", _save_event)
bench("timeline_persistence_load", lambda: timeline_persistence.load_timeline("bench-base"))

# ── 3. Approval persistence ────────────────────────────────────────────────────
_ap_counter = [0]
def _save_approval():
    _ap_counter[0] += 1
    rec = ApprovalRecord(
        approval_id=f"a-bench-{_ap_counter[0]}",
        task_id="bench-base",
        action="click",
        risk_level="SAFE",
    )
    approval_persistence.save(rec)

bench("approval_persistence_save", _save_approval)
bench("approval_persistence_load_all", lambda: approval_persistence.load_all("bench-base"))

# ── 4. Snapshot system ─────────────────────────────────────────────────────────
_snap_task = _make_task("bench-snap", "c-snap")
task_persistence.save(_snap_task)
snap_system.create(_snap_task, "research_complete")  # prime for load benchmarks

bench("snapshot_create", lambda: snap_system.create(_snap_task, "research_complete"))
bench("snapshot_load_latest", lambda: snap_system.load_latest("bench-snap"))
bench("snapshot_load_all", lambda: snap_system.load_all("bench-snap"))

# ── 5. Restoration ─────────────────────────────────────────────────────────────
# Fast path: in memory
_mem_task = _make_task("bench-mem", "c-mem")
task_store.put(_mem_task)
bench("restore_fast_path", lambda: task_restoration.restore("bench-mem"))

# Slow path: from DB only (not in memory)
_db_task = _make_task("bench-db", "c-db")
task_persistence.save(_db_task)

def _restore_slow():
    task_store._reset_for_testing()
    # Re-seed memory with other tasks so bench-db stays DB-only
    task_store.put(_mem_task)
    return task_restoration.restore("bench-db")

bench("restore_slow_path", _restore_slow, reps=50)  # fewer reps — each wipes store

_db_conv_task = _make_task("bench-conv", "c-conv-bench")
task_persistence.save(_db_conv_task)

def _restore_by_conv():
    task_store._reset_for_testing()
    task_store.put(_mem_task)
    return task_restoration.restore_by_conversation("c-conv-bench")

bench("restore_by_conversation", _restore_by_conv, reps=50)

# ── 6. Bootstrap consumer ──────────────────────────────────────────────────────
_boot_task = _make_task("bench-boot", "c-boot")
task_store.put(_boot_task)
_consumer = WorkflowBootstrapConsumer()
bench("bootstrap_consume", lambda: _consumer.consume(_boot_task))
bench("bootstrap_consume_by_task_id", lambda: _consumer.consume_by_task_id("bench-boot"))

# ── 7. Prefill builder ────────────────────────────────────────────────────────
_pf_task = _make_task("bench-pf", "c-pf")
task_store.put(_pf_task)
bench("prefill_build", lambda: prefill_layer.build(_pf_task))
bench("prefill_build_by_task_id", lambda: prefill_layer.build_by_task_id("bench-pf"))

# ── Report ─────────────────────────────────────────────────────────────────────
print(f"{'Operation':<38} {'p50':>8} {'p95':>8} {'p99':>8} {'Target':>8} {'Status'}")
print("-" * 82)

for op_name, target_ms in TARGETS.items():
    times = results.get(op_name, [])
    if not times:
        print(f"{op_name:<38} {'NO DATA':>8}")
        continue
    p50 = statistics.median(times)
    p95 = statistics.quantiles(times, n=100)[94]
    p99 = statistics.quantiles(times, n=100)[98]
    ok = p95 <= target_ms
    status = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"{op_name:<38} {p50:>7.2f}ms {p95:>7.2f}ms {p99:>7.2f}ms {target_ms:>7.1f}ms  {status}")

print("-" * 82)
print(f"\nPASS: {PASS}  FAIL: {FAIL}  Total: {len(TARGETS)}")
print()

if FAIL > 0:
    print("Regressions detected:")
    for op_name, target_ms in TARGETS.items():
        times = results.get(op_name, [])
        if not times:
            continue
        p95 = statistics.quantiles(times, n=100)[94]
        if p95 > target_ms:
            print(f"  {op_name}: p95={p95:.2f}ms > target={target_ms}ms")

sys.exit(0 if FAIL == 0 else 1)
