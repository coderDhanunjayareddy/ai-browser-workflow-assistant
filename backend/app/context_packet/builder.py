from __future__ import annotations

import time
from typing import Any

from app.context_packet.budget import ContextPacketBudget, packet_size_chars
from app.context_packet.models import ContextBudgetMetadata, PlannerPacket
from app.context_packet.projection import project_semantic_graph
from app.schemas.request import PageContext
from app.semantic_page.graph import SemanticPageGraph


class ContextPacketBuilder:
    def __init__(self, budget: ContextPacketBudget | None = None):
        self.budget = budget or ContextPacketBudget()

    def build(
        self,
        *,
        run_id: str,
        task: str,
        page_context: PageContext,
        semantic_graph: SemanticPageGraph,
        prior_steps: list[Any],
        supplemental_context: str,
        verified_facts: dict[str, Any],
        compressed_context: dict[str, Any],
    ) -> tuple[PlannerPacket, int]:
        started = time.perf_counter()
        semantic_projection, original_counts, trimmed_counts = project_semantic_graph(
            semantic_graph,
            self.budget,
        )
        packet_data = {
            "run": {
                "run_id": run_id,
                "semantic_graph_id": semantic_graph.graph_id,
                "observation_id": semantic_graph.observation_id,
            },
            "mission_context": {
                "mission": task,
                "objective": task,
                "constraints": _bounded_list(compressed_context.get("task_constraints", []), 8),
                "current_step": len(prior_steps) + 1,
                "recent_attempts": _recent_attempts(prior_steps),
            },
            "task_context": {
                "active_goal": compressed_context.get("active_goal", task),
                "verified_facts": verified_facts,
            },
            "browser_context": {
                "current_page": {
                    "url": page_context.url,
                    "title": page_context.title,
                    "page_type": semantic_graph.page_type,
                },
                "browser_metadata": dict(sorted(page_context.metadata.items())),
                "active_dialogs": [
                    item for item in semantic_projection["controls"]
                    if item.get("node_type") == "dialog"
                ],
                "downloads_uploads": [
                    item for item in semantic_projection["controls"]
                    if item.get("node_type") in {"download", "upload"}
                ],
            },
            "page_context": {
                "semantic": semantic_projection,
                "headings": list(page_context.headings[:10]),
            },
            "memory_context": {
                "task_workspace": supplemental_context,
                "mission_snapshot": supplemental_context,
                "selected_memory": compressed_context.get("cognitive_context", {}),
                "previous_planner_outputs": _bounded_list(compressed_context.get("recent_actions", []), 8),
                "run_identifiers": {"run_id": run_id, "session_id": run_id},
            },
            "policy_context": {
                "constraints": _bounded_list(compressed_context.get("task_constraints", []), 8),
            },
            "capability_context": {},
            "recovery_context": {
                "important_failures": _bounded_list(compressed_context.get("important_failures", []), 8),
            },
            "validation_context": {
                "verified_facts": compressed_context.get("verified_facts", {}),
            },
            "output_contract": "planner_contract_v2",
        }
        packet_chars = packet_size_chars(packet_data)
        budget_metadata = ContextBudgetMetadata(
            max_entities=self.budget.max_entities,
            max_targets=self.budget.max_targets,
            max_facts=self.budget.max_facts,
            max_controls=self.budget.max_controls,
            max_packet_chars=self.budget.max_packet_chars,
            original_counts=original_counts,
            trimmed_counts=trimmed_counts,
            packet_chars=packet_chars,
        )
        packet = PlannerPacket(
            **packet_data,
            budget_metadata=budget_metadata,
        )
        return packet, int((time.perf_counter() - started) * 1000)


def _recent_attempts(prior_steps: list[Any]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for index, step in enumerate(prior_steps[-8:]):
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step) if isinstance(step, dict) else {}
        attempts.append(
            {
                "index": index,
                "action_type": data.get("action_type", ""),
                "description": data.get("description", ""),
                "execution_result": data.get("execution_result", ""),
            }
        )
    return attempts


def _bounded_list(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[-limit:]
