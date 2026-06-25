"""
V4.5 Benchmark — Unified Task Graph performance.

All operations should be < 10ms p95.
Reports: min, p50, p95, p99, max for each operation.
"""
import sys
import time
import statistics

sys.path.insert(0, ".")

from app.unified import store as task_store, analytics as task_analytics
from app.unified.task_lifecycle import TaskLifecycleManager
from app.unified.task_timeline import TaskTimelineManager
from app.unified.approval_center import ApprovalCenter
from app.unified.tab_registry import TaskTabRegistry
from app.unified.workflow_continuity import WorkflowContinuityLayer
from app.unified.task_context_registry import TaskContextRegistry
from app.unified.models import TabRole

task_store._reset_for_testing()
task_analytics._reset_for_testing()

mgr = TaskLifecycleManager()
timeline = TaskTimelineManager()
ac = ApprovalCenter()
tab_reg = TaskTabRegistry()
continuity = WorkflowContinuityLayer()
ctx_reg = TaskContextRegistry()

REPS = 500
TARGET_P95_MS = 10.0


def bench(name: str, fn) -> dict:
    times = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    result = {
        "name": name,
        "min": times[0],
        "p50": times[int(REPS * 0.50)],
        "p95": times[int(REPS * 0.95)],
        "p99": times[int(REPS * 0.99)],
        "max": times[-1],
        "mean": statistics.mean(times),
    }
    ok = "PASS" if result["p95"] < TARGET_P95_MS else "FAIL"
    print(
        f"  [{ok}] {name:40s}  "
        f"min={result['min']:.2f}ms  p50={result['p50']:.2f}ms  "
        f"p95={result['p95']:.2f}ms  p99={result['p99']:.2f}ms  "
        f"max={result['max']:.2f}ms"
    )
    return result


print("V4.5 Benchmark — Unified Task Graph")
print("="*80)
print(f"Repetitions: {REPS}   Target p95: < {TARGET_P95_MS}ms")
print()

# ── Pre-create baseline objects ───────────────────────────────────────────────
BASE_TASK = mgr.create("conv-bench-0", "baseline benchmark task")
for _ in range(5):
    timeline.record_user_message(BASE_TASK, "test message")
rec_b = ac.request(BASE_TASK, "click", "SAFE")

# Populate store with 100 tasks for list benchmark
for i in range(100):
    mgr.create(f"conv-bench-{i+1}", f"task {i}")

print("[1] Core Lifecycle Operations")
bench("task_store.get (hit)", lambda: task_store.get(BASE_TASK.task_id))
bench("task_store.get_by_conversation", lambda: task_store.get_by_conversation("conv-bench-0"))
bench("task_store.all_tasks (100+ tasks)", lambda: task_store.all_tasks())
bench("task_store.count", lambda: task_store.count())

print()
print("[2] Context Registry")
bench("ctx_reg.lookup (basic)", lambda: ctx_reg.lookup(BASE_TASK.task_id))

print()
print("[3] Timeline")
bench("timeline.get_ordered", lambda: timeline.get_ordered(BASE_TASK))
bench("timeline.get_summary", lambda: timeline.get_summary(BASE_TASK))
bench("timeline.record_user_message", lambda: timeline.record_user_message(BASE_TASK, "q"))

print()
print("[4] Approval Center")
bench("ac.pending", lambda: ac.pending(BASE_TASK))
bench("ac.history", lambda: ac.history(BASE_TASK))

print()
print("[5] Tab Registry")
bench("tab_reg.get_all", lambda: tab_reg.get_all(BASE_TASK))
bench("tab_reg.summary", lambda: tab_reg.summary(BASE_TASK))

print()
print("[6] Analytics")
bench("analytics.get_analytics", lambda: task_analytics.get_analytics())
bench("analytics.record_task_created", lambda: task_analytics.record_task_created())
bench("analytics.record_timeline_event", lambda: task_analytics.record_timeline_event("user_message"))

print()
print("[7] Workflow Continuity")
bench("continuity.is_ready_for_workflow", lambda: continuity.is_ready_for_workflow(BASE_TASK))
bench("continuity.get_handoff_context", lambda: continuity.get_handoff_context(BASE_TASK))

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("="*80)
print("Benchmark complete.")
