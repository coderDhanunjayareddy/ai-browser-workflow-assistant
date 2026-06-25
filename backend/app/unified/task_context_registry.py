"""
V4.5 Unified Task Graph — TaskContextRegistry.

Single lookup layer: given a task_id, return a unified context dict
containing entities, goals, research findings, intelligence plan, and
workflow facts without calling 5 separate systems.

This is a read-only aggregation layer — it does NOT modify any system.
All sources remain authoritative; the registry just combines their outputs.
"""
from __future__ import annotations

import time
from typing import Optional

from app.unified import store as task_store
from app.unified.models import UnifiedTask


class TaskContextRegistry:
    """Aggregate context for a task from all subsystems."""

    def lookup(
        self,
        task_id: str,
        cognitive_session=None,    # Optional[CognitiveSession]
        research_session=None,     # Optional[ResearchSession]
    ) -> dict:
        """
        Return a unified context dict for the task.

        Parameters
        ----------
        task_id:
            The ID of the UnifiedTask to look up.
        cognitive_session:
            If provided, entity and goal data are extracted from it.
            If None, only cached data from the task itself is used.
        research_session:
            If provided, research findings are extracted from it.
            If None, only cached data from the task itself is used.

        Returns
        -------
        dict with keys:
            task_id, task_state, conversation_id,
            entities, goals, memory_summary,
            research_findings, research_topic, research_confidence,
            workflow_facts, execution_plan,
            timeline_length, pending_approvals
        """
        t0 = time.perf_counter()
        task = task_store.get(task_id)
        if task is None:
            return {"error": f"Task {task_id!r} not found", "latency_ms": 0}

        # Entities from cognitive session (authoritative) or task cache
        entities: dict = {}
        goals: list = []
        memory_summary: str = ""

        if cognitive_session is not None:
            try:
                entities = {
                    e.name: getattr(e, "metadata", {})
                    for e in cognitive_session.active_entities.values()
                }
                if cognitive_session.active_goal:
                    goals = [cognitive_session.active_goal.goal_text]
                memory_summary = cognitive_session.conversation_summary
            except Exception:
                pass
        else:
            entities = task.entities or {}

        # Research from research session (authoritative) or task cache
        research_findings: list = []
        research_topic: str = ""
        research_confidence: float = 0.0

        if research_session is not None:
            try:
                if research_session.report:
                    research_findings = research_session.report.key_findings
                    research_confidence = research_session.report.confidence_score
                research_topic = research_session.topic
            except Exception:
                pass
        elif task.research_report:
            research_findings = task.research_report.get("key_findings", [])
            research_topic = task.research_report.get("topic", "")
            research_confidence = task.research_report.get("confidence_score", 0.0)

        # Execution plan from task cache
        execution_plan = task.execution_plan or {}

        # Workflow facts (simple)
        workflow_facts: dict = {
            "workflow_session_id": task.workflow_session_id,
            "approval_state": task.approval_state.value,
        }

        latency_ms = int((time.perf_counter() - t0) * 1000)

        return {
            "task_id": task.task_id,
            "task_state": task.state.value,
            "conversation_id": task.conversation_id,
            "original_query": task.original_query,
            "current_goal": task.current_goal,
            "entities": entities,
            "goals": goals,
            "memory_summary": memory_summary,
            "research_findings": research_findings,
            "research_topic": research_topic,
            "research_confidence": research_confidence,
            "workflow_facts": workflow_facts,
            "execution_plan": execution_plan,
            "timeline_length": len(task.timeline.events),
            "pending_approvals": len(task.pending_approvals()),
            "latency_ms": latency_ms,
        }

    def update_entity_cache(self, task: UnifiedTask, entities: dict) -> None:
        """Cache extracted entities on the task for offline lookup."""
        task.entities.update(entities)
        task.touch()
        task_store.put(task)

    def update_research_cache(self, task: UnifiedTask, report_dict: dict) -> None:
        """Cache serializable research report on the task."""
        task.research_report = report_dict
        task.touch()
        task_store.put(task)

    def update_plan_cache(self, task: UnifiedTask, plan_dict: dict) -> None:
        """Cache execution plan on the task."""
        task.execution_plan = plan_dict
        task.touch()
        task_store.put(task)


# Module-level singleton
_registry = TaskContextRegistry()


def lookup(task_id: str, cognitive_session=None, research_session=None) -> dict:
    return _registry.lookup(task_id, cognitive_session, research_session)


def update_entity_cache(task: UnifiedTask, entities: dict) -> None:
    _registry.update_entity_cache(task, entities)


def update_research_cache(task: UnifiedTask, report_dict: dict) -> None:
    _registry.update_research_cache(task, report_dict)


def update_plan_cache(task: UnifiedTask, plan_dict: dict) -> None:
    _registry.update_plan_cache(task, plan_dict)
