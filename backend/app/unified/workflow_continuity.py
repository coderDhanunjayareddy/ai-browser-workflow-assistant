"""
V4.5 Unified Task Graph — WorkflowContinuityLayer.

Ensures that when a task transitions from research → workflow,
all context is preserved on the UnifiedTask so nothing is lost:

  ExecutionPlan + ResearchReport + GoalTree + Entities

remain attached to the same task through the entire lifecycle.

This replaces the V3.5/V4.0 point-to-point handoff with task-scoped
context continuity. The existing WorkflowHandoffPayload continues to
work — this layer enriches it with task context.
"""
from __future__ import annotations

from typing import Optional

from app.unified.models import UnifiedTask
from app.unified import store as task_store
from app.unified import task_context_registry


class WorkflowContinuityLayer:
    """
    Attach and retrieve context for seamless research → workflow transitions.
    """

    def attach_research(
        self,
        task: UnifiedTask,
        research_session_id: str,
        topic: str,
        executive_summary: str,
        key_findings: list,
        recommended_actions: list,
        confidence_score: float,
    ) -> None:
        """Cache research report context on the task."""
        task.research_session_id = research_session_id
        task.current_goal = task.current_goal or topic
        task_context_registry.update_research_cache(task, {
            "session_id": research_session_id,
            "topic": topic,
            "executive_summary": executive_summary,
            "key_findings": key_findings,
            "recommended_actions": recommended_actions,
            "confidence_score": confidence_score,
        })
        task_store.put(task)

    def attach_intelligence(
        self,
        task: UnifiedTask,
        plan_id: str,
        workflow_type: str,
        approval_level: str,
        confidence: float,
        missing_inputs: list,
        recommended_next_action: str,
    ) -> None:
        """Cache intelligence execution plan on the task."""
        task_context_registry.update_plan_cache(task, {
            "plan_id": plan_id,
            "workflow_type": workflow_type,
            "approval_level": approval_level,
            "confidence": confidence,
            "missing_inputs": missing_inputs,
            "recommended_next_action": recommended_next_action,
        })
        task_store.put(task)

    def attach_entities(self, task: UnifiedTask, entities: dict) -> None:
        """Cache entity dict on the task."""
        task_context_registry.update_entity_cache(task, entities)

    def get_handoff_context(self, task: UnifiedTask) -> dict:
        """
        Return a unified context dict for workflow initialization.
        This replaces the simple WorkflowHandoffPayload for task-aware handoffs.
        """
        research = task.research_report or {}
        plan = task.execution_plan or {}
        return {
            "task_id": task.task_id,
            "conversation_id": task.conversation_id,
            "original_query": task.original_query,
            "current_goal": task.current_goal,
            "entities": task.entities,
            "research_topic": research.get("topic", ""),
            "research_summary": research.get("executive_summary", ""),
            "research_findings": research.get("key_findings", []),
            "workflow_type": plan.get("workflow_type", ""),
            "approval_level": plan.get("approval_level", "REQUIRES_APPROVAL"),
            "pre_filled_inputs": {
                k: v for k, v in task.entities.items()
            },
        }

    def is_ready_for_workflow(self, task: UnifiedTask) -> bool:
        """True when research is complete and an execution plan is attached."""
        from app.unified.models import TaskState
        return task.state in (
            TaskState.ready_for_workflow,
            TaskState.workflow_running,
            TaskState.waiting_approval,
        )


# Module-level singleton
_continuity = WorkflowContinuityLayer()


def attach_research(
    task: UnifiedTask,
    research_session_id: str,
    topic: str,
    executive_summary: str,
    key_findings: list,
    recommended_actions: list,
    confidence_score: float,
) -> None:
    _continuity.attach_research(
        task, research_session_id, topic, executive_summary,
        key_findings, recommended_actions, confidence_score,
    )


def attach_intelligence(
    task: UnifiedTask,
    plan_id: str,
    workflow_type: str,
    approval_level: str,
    confidence: float,
    missing_inputs: list,
    recommended_next_action: str,
) -> None:
    _continuity.attach_intelligence(
        task, plan_id, workflow_type, approval_level,
        confidence, missing_inputs, recommended_next_action,
    )


def attach_entities(task: UnifiedTask, entities: dict) -> None:
    _continuity.attach_entities(task, entities)


def get_handoff_context(task: UnifiedTask) -> dict:
    return _continuity.get_handoff_context(task)


def is_ready_for_workflow(task: UnifiedTask) -> bool:
    return _continuity.is_ready_for_workflow(task)
