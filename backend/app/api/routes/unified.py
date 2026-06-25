"""
V4.5 Unified Task Graph — REST API routes.

Provides:
  GET  /unified/tasks                  → list all tasks (debug)
  GET  /unified/tasks/{task_id}        → full task view (debug center)
  GET  /unified/tasks/{task_id}/context → unified context registry lookup
  GET  /unified/tasks/{task_id}/timeline → ordered timeline
  POST /unified/tasks/{task_id}/approvals/{approval_id}/approve
  POST /unified/tasks/{task_id}/approvals/{approval_id}/deny
  GET  /unified/analytics              → task analytics
  GET  /unified/conversation/{conv_id} → task by conversation ID
"""
import time

from fastapi import APIRouter, HTTPException
from typing import Optional

from app.unified import store as task_store
from app.unified import approval_center, task_timeline, task_context_registry, analytics
from app.unified import restoration as task_restoration
from app.unified import snapshot as task_snapshot
from app.unified import bootstrap_consumer
from app.unified import prefill as prefill_layer
from app.unified.models import UnifiedTask
from app.schemas.unified import (
    UnifiedTaskSchema, TaskContextSchema, TaskAnalyticsSchema,
    TimelineEventSchema, ApprovalRecordSchema, TaskTabSchema,
    TaskSnapshotSchema, WorkflowPrefillSchema, TaskRestorationSchema,
    WorkflowBootstrapSchema,
)

router = APIRouter(prefix="/unified", tags=["unified"])


# ── Serialization helpers ─────────────────────────────────────────────────────

def _task_to_schema(task: UnifiedTask) -> UnifiedTaskSchema:
    approvals_s = [
        ApprovalRecordSchema(
            approval_id=a.approval_id,
            task_id=a.task_id,
            action=a.action,
            risk_level=a.risk_level,
            status=a.status.value,
            created_at=a.created_at.isoformat(),
            resolved_at=a.resolved_at.isoformat() if a.resolved_at else None,
            resolution_note=a.resolution_note,
        )
        for a in task.approvals
    ]
    tabs_s = [
        TaskTabSchema(
            tab_id=t.tab_id,
            url=t.url,
            title=t.title,
            role=t.role.value,
            added_at=t.added_at.isoformat(),
        )
        for t in task.tabs
    ]
    timeline_s = [
        TimelineEventSchema(
            event_id=e.event_id,
            type=e.event_type.value,
            timestamp=e.timestamp.isoformat(),
            data=e.data,
        )
        for e in task_timeline.get_ordered(task)
    ]
    return UnifiedTaskSchema(
        task_id=task.task_id,
        conversation_id=task.conversation_id,
        cognitive_session_id=task.cognitive_session_id,
        research_session_id=task.research_session_id,
        workflow_session_id=task.workflow_session_id,
        original_query=task.original_query,
        current_goal=task.current_goal,
        state=task.state.value,
        entities=task.entities,
        execution_plan=task.execution_plan,
        research_report=task.research_report,
        approval_state=task.approval_state.value,
        timeline_length=len(task.timeline.events),
        pending_approvals=len(task.pending_approvals()),
        tabs=tabs_s,
        approvals=approvals_s,
        timeline=timeline_s,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/tasks", response_model=list[UnifiedTaskSchema])
def list_tasks():
    """List all UnifiedTasks (debug view)."""
    return [_task_to_schema(t) for t in task_store.all_tasks()]


@router.get("/tasks/{task_id}", response_model=UnifiedTaskSchema)
def get_task(task_id: str):
    """Full debug view for a single UnifiedTask."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return _task_to_schema(task)


@router.get("/tasks/{task_id}/context", response_model=TaskContextSchema)
def get_context(task_id: str):
    """Unified context registry lookup for a task."""
    ctx = task_context_registry.lookup(task_id)
    if "error" in ctx:
        raise HTTPException(status_code=404, detail=ctx["error"])
    return TaskContextSchema(**ctx)


@router.get("/tasks/{task_id}/timeline", response_model=list[TimelineEventSchema])
def get_timeline(task_id: str):
    """Ordered timeline for a task."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return [
        TimelineEventSchema(
            event_id=e.event_id,
            type=e.event_type.value,
            timestamp=e.timestamp.isoformat(),
            data=e.data,
        )
        for e in task_timeline.get_ordered(task)
    ]


@router.post("/tasks/{task_id}/approvals/{approval_id}/approve")
def approve_action(task_id: str, approval_id: str, note: str = ""):
    """Grant an approval. Does NOT trigger execution — UI handles that."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    rec = approval_center.approve(task, approval_id, note=note)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found or not pending")
    return {"approved": True, "approval_id": rec.approval_id, "status": rec.status.value}


@router.post("/tasks/{task_id}/approvals/{approval_id}/deny")
def deny_action(task_id: str, approval_id: str, reason: str = ""):
    """Deny an approval."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    rec = approval_center.deny(task, approval_id, reason=reason)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Approval {approval_id!r} not found or not pending")
    return {"denied": True, "approval_id": rec.approval_id, "status": rec.status.value}


@router.get("/analytics", response_model=TaskAnalyticsSchema)
def get_analytics():
    """Unified task lifecycle analytics."""
    return TaskAnalyticsSchema(**analytics.get_analytics())


@router.get("/conversation/{conversation_id}", response_model=UnifiedTaskSchema)
def get_by_conversation(conversation_id: str):
    """Look up a task by conversation_id."""
    task = task_store.get_by_conversation(conversation_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No task for conversation {conversation_id!r}")
    return _task_to_schema(task)


# ── V4.6 Endpoints ────────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}/restore", response_model=TaskRestorationSchema)
def restore_task(task_id: str):
    """
    Restore a UnifiedTask from persistence.
    Fast path: in-memory (< 1ms). Slow path: DB reconstruction (< 50ms p95).
    """
    t0 = time.perf_counter()
    in_memory = task_store.get(task_id) is not None
    task = task_restoration.restore(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found in memory or DB")
    latency_ms = int((time.perf_counter() - t0) * 1000)
    snap = task_snapshot.load_latest(task_id)
    return TaskRestorationSchema(
        task_id=task.task_id,
        restored_from="memory" if in_memory else "database",
        task_state=task.state.value,
        timeline_events=len(task.timeline.events),
        approval_count=len(task.approvals),
        snapshot_used=snap is not None and not in_memory,
        latency_ms=latency_ms,
        original_query=task.original_query,
        current_goal=task.current_goal,
    )


@router.get("/tasks/{task_id}/snapshots", response_model=list[TaskSnapshotSchema])
def get_snapshots(task_id: str):
    """List all snapshots for a task, newest first."""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    snaps = task_snapshot.load_all(task_id)
    return [
        TaskSnapshotSchema(
            snapshot_id=s["snapshot_id"],
            trigger=s["trigger"],
            task_state=s["task_state"],
            created_at=s["created_at"],
            context={k: v for k, v in s.items()
                     if k not in {"snapshot_id", "trigger", "task_state", "created_at"}},
        )
        for s in snaps
    ]


@router.get("/tasks/{task_id}/bootstrap", response_model=WorkflowBootstrapSchema)
def get_bootstrap(task_id: str):
    """
    Get workflow bootstrap context for a task.
    Planner receives this instead of starting cold.
    """
    task = task_store.get(task_id)
    if task is None:
        # Try restoring from DB before giving up
        task = task_restoration.restore(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    ctx = bootstrap_consumer.consume(task)
    d = ctx.to_dict()
    return WorkflowBootstrapSchema(
        task_id=d["task_id"],
        original_query=d["original_query"],
        current_goal=d["current_goal"],
        entities=d["entities"],
        execution_plan=d["execution_plan"],
        research_summary=d["research_summary"],
        key_findings=d["key_findings"],
        recommended_actions=d["recommended_actions"],
        confidence=d["confidence"],
        approval_level=d["approval_level"],
        workflow_type=d["workflow_type"],
        missing_inputs=d["missing_inputs"],
        recommended_next_action=d["recommended_next_action"],
        pre_filled_facts=d["pre_filled_facts"],
        is_ready=ctx.is_ready,
        latency_ms=d["latency_ms"],
    )


@router.get("/tasks/{task_id}/prefill", response_model=WorkflowPrefillSchema)
def get_prefill(task_id: str):
    """
    Get workflow panel prefill payload.
    Returned when user clicks 'Prepare Workflow'.
    All fields are editable — user remains in control.
    """
    task = task_store.get(task_id)
    if task is None:
        task = task_restoration.restore(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    payload = prefill_layer.build(task)
    return WorkflowPrefillSchema(**payload.model_dump())


@router.get("/tasks/{task_id}/inspect", response_model=UnifiedTaskSchema)
def inspect_task(task_id: str):
    """
    Unified Task Inspector: full debug view with restoration fallback.
    Tries memory first, then DB. Single source of truth.
    """
    task = task_store.get(task_id)
    if task is None:
        task = task_restoration.restore(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found in memory or DB")
    return _task_to_schema(task)
