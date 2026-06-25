"""
V4.6 Unified Task Graph — WorkflowBootstrapConsumer.

When a workflow session begins from a task that already has research + intelligence
context, the planner should receive that context directly instead of starting cold.

This consumer reads the UnifiedTask's cached context and produces a
WorkflowBootstrapContext that the workflow orchestrator can pass to the planner.

No re-extraction. No duplicate AI calls.
Human remains in control — bootstrap provides CONTEXT, not auto-execution.

Performance target: < 10ms p95 (pure dict operations, no DB or AI calls).
"""
from __future__ import annotations

import time
from typing import Optional

from app.unified.models import UnifiedTask, TaskState
from app.unified import store as task_store


class WorkflowBootstrapContext:
    """
    Structured context package passed to the workflow planner on startup.

    Fields mirror what a planner would otherwise need to extract from scratch.
    """

    def __init__(
        self,
        task_id: str,
        original_query: str,
        current_goal: Optional[str],
        entities: dict,
        execution_plan: dict,
        research_summary: str,
        key_findings: list,
        recommended_actions: list,
        confidence: float,
        approval_level: str,
        workflow_type: str,
        missing_inputs: list,
        recommended_next_action: str,
        pre_filled_facts: dict,
        latency_ms: int,
    ) -> None:
        self.task_id = task_id
        self.original_query = original_query
        self.current_goal = current_goal
        self.entities = entities
        self.execution_plan = execution_plan
        self.research_summary = research_summary
        self.key_findings = key_findings
        self.recommended_actions = recommended_actions
        self.confidence = confidence
        self.approval_level = approval_level
        self.workflow_type = workflow_type
        self.missing_inputs = missing_inputs
        self.recommended_next_action = recommended_next_action
        self.pre_filled_facts = pre_filled_facts
        self.latency_ms = latency_ms

    def to_dict(self) -> dict:
        return {
            "task_id":                  self.task_id,
            "original_query":           self.original_query,
            "current_goal":             self.current_goal,
            "entities":                 self.entities,
            "execution_plan":           self.execution_plan,
            "research_summary":         self.research_summary,
            "key_findings":             self.key_findings,
            "recommended_actions":      self.recommended_actions,
            "confidence":               self.confidence,
            "approval_level":           self.approval_level,
            "workflow_type":            self.workflow_type,
            "missing_inputs":           self.missing_inputs,
            "recommended_next_action":  self.recommended_next_action,
            "pre_filled_facts":         self.pre_filled_facts,
            "latency_ms":               self.latency_ms,
        }

    def as_bootstrap_facts(self) -> dict:
        """
        Convert to the flat fact dict that StatePersistence.save_facts() expects.
        This merges entities with any structured fields the planner knows about.
        """
        facts: dict = {}
        facts.update(self.entities)
        if self.current_goal:
            facts["goal"] = self.current_goal
        if self.workflow_type:
            facts["workflow_type"] = self.workflow_type
        if self.approval_level:
            facts["approval_level"] = self.approval_level
        if self.recommended_next_action:
            facts["next_action"] = self.recommended_next_action
        facts.update(self.pre_filled_facts)
        return facts

    @property
    def is_ready(self) -> bool:
        """True when enough context exists to skip cold-start extraction."""
        return bool(
            self.entities or self.execution_plan or self.research_summary
        )


class WorkflowBootstrapConsumer:
    """
    Consumes a UnifiedTask's cached context and produces a WorkflowBootstrapContext.
    """

    def consume(self, task: UnifiedTask) -> WorkflowBootstrapContext:
        """
        Build a WorkflowBootstrapContext from a UnifiedTask.

        Pure dict operations — no DB or AI calls.
        """
        t0 = time.perf_counter()

        plan = task.execution_plan or {}
        report = task.research_report or {}

        # Build pre-filled facts: entity values that are already known
        pre_filled: dict = {}
        for key, value in task.entities.items():
            if isinstance(value, (str, int, float, bool)):
                pre_filled[key] = value
            elif isinstance(value, dict) and "value" in value:
                pre_filled[key] = value["value"]

        latency_ms = int((time.perf_counter() - t0) * 1000)

        return WorkflowBootstrapContext(
            task_id=task.task_id,
            original_query=task.original_query,
            current_goal=task.current_goal,
            entities=task.entities or {},
            execution_plan=plan,
            research_summary=report.get("executive_summary", ""),
            key_findings=report.get("key_findings", []),
            recommended_actions=report.get("recommended_actions", []),
            confidence=plan.get("confidence", report.get("confidence_score", 0.0)),
            approval_level=plan.get("approval_level", "REQUIRES_APPROVAL"),
            workflow_type=plan.get("workflow_type", ""),
            missing_inputs=plan.get("missing_inputs", []),
            recommended_next_action=plan.get("recommended_next_action", ""),
            pre_filled_facts=pre_filled,
            latency_ms=latency_ms,
        )

    def consume_by_task_id(self, task_id: str) -> Optional[WorkflowBootstrapContext]:
        """Convenience: look up task by ID then consume."""
        task = task_store.get(task_id)
        if task is None:
            return None
        return self.consume(task)

    def enrich_handoff_payload(self, task: UnifiedTask, payload_dict: dict) -> dict:
        """
        Merge bootstrap context into an existing handoff payload dict.
        Non-destructive: existing keys are not overwritten.
        """
        ctx = self.consume(task)
        enriched = dict(payload_dict)
        enriched.setdefault("task_id", ctx.task_id)
        enriched.setdefault("goal", ctx.current_goal)
        enriched.setdefault("entities", ctx.entities)
        enriched.setdefault("execution_plan", ctx.execution_plan)
        enriched.setdefault("research_summary", ctx.research_summary)
        enriched.setdefault("key_findings", ctx.key_findings)
        enriched.setdefault("approval_level", ctx.approval_level)
        enriched.setdefault("workflow_type", ctx.workflow_type)
        for k, v in ctx.pre_filled_facts.items():
            enriched.setdefault(k, v)
        return enriched


# Module-level singleton
_consumer = WorkflowBootstrapConsumer()


def consume(task: UnifiedTask) -> WorkflowBootstrapContext:
    return _consumer.consume(task)


def consume_by_task_id(task_id: str) -> Optional[WorkflowBootstrapContext]:
    return _consumer.consume_by_task_id(task_id)


def enrich_handoff_payload(task: UnifiedTask, payload_dict: dict) -> dict:
    return _consumer.enrich_handoff_payload(task, payload_dict)
