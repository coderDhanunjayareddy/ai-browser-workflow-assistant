"""
V4.6 Unified Task Graph — WorkflowPrefillLayer.

When the user clicks "Prepare Workflow", the frontend receives a
WorkflowPrefillPayload with all context pre-populated so the workflow panel
opens ready to use.

User retains full control:
  - every field is editable before submission
  - approval classification is shown, not bypassed
  - no automatic execution

Performance target: < 10ms p95 (pure dict/Pydantic, no DB or AI calls).
"""
from __future__ import annotations

import time
from typing import Optional, Any

from pydantic import BaseModel, Field

from app.unified.models import UnifiedTask, TaskState
from app.unified import store as task_store
from app.unified.bootstrap_consumer import WorkflowBootstrapConsumer


# ── Pydantic schema (API boundary) ────────────────────────────────────────────

class WorkflowPrefillPayload(BaseModel):
    """
    Sent to the frontend when "Prepare Workflow" is clicked.
    All fields are pre-populated from the UnifiedTask context.
    All fields are editable by the user in the workflow panel.
    """
    task_id:                 str
    title:                   str = ""            # human-readable task title
    goal:                    Optional[str] = None
    entities:                dict[str, Any] = Field(default_factory=dict)
    execution_plan:          dict[str, Any] = Field(default_factory=dict)
    readiness_state:         str = "NOT_READY"   # READY | NOT_READY | PARTIAL
    approval_classification: str = "REQUIRES_APPROVAL"
    workflow_type:           str = ""
    missing_inputs:          list[str] = Field(default_factory=list)
    recommended_next_action: str = ""
    research_summary:        str = ""
    key_findings:            list[str] = Field(default_factory=list)
    recommended_actions:     list[str] = Field(default_factory=list)
    confidence:              float = 0.0
    pre_filled_facts:        dict[str, Any] = Field(default_factory=dict)
    task_state:              str = "CREATED"
    latency_ms:              int = 0


# ── Builder ───────────────────────────────────────────────────────────────────

_bootstrap_consumer = WorkflowBootstrapConsumer()

_READY_STATES = {
    TaskState.ready_for_workflow,
    TaskState.workflow_running,
    TaskState.waiting_approval,
}

_PARTIAL_STATES = {
    TaskState.research_complete,
}


def _readiness(task: UnifiedTask) -> str:
    if task.state in _READY_STATES:
        return "READY"
    if task.state in _PARTIAL_STATES:
        return "PARTIAL"
    return "NOT_READY"


def build(task: UnifiedTask) -> WorkflowPrefillPayload:
    """
    Construct a WorkflowPrefillPayload from a UnifiedTask.

    Pure computation — no DB or AI calls. < 10ms p95.
    """
    t0 = time.perf_counter()

    ctx = _bootstrap_consumer.consume(task)
    readiness = _readiness(task)

    title = task.current_goal or task.original_query or ""
    if len(title) > 80:
        title = title[:77] + "..."

    latency_ms = int((time.perf_counter() - t0) * 1000)

    return WorkflowPrefillPayload(
        task_id=task.task_id,
        title=title,
        goal=task.current_goal,
        entities=ctx.entities,
        execution_plan=ctx.execution_plan,
        readiness_state=readiness,
        approval_classification=ctx.approval_level,
        workflow_type=ctx.workflow_type,
        missing_inputs=ctx.missing_inputs,
        recommended_next_action=ctx.recommended_next_action,
        research_summary=ctx.research_summary,
        key_findings=ctx.key_findings,
        recommended_actions=ctx.recommended_actions,
        confidence=ctx.confidence,
        pre_filled_facts=ctx.pre_filled_facts,
        task_state=task.state.value,
        latency_ms=latency_ms,
    )


def build_by_task_id(task_id: str) -> Optional[WorkflowPrefillPayload]:
    """Convenience: look up task then build prefill payload."""
    task = task_store.get(task_id)
    if task is None:
        return None
    return build(task)
