from __future__ import annotations

from typing import Any

from app.cognitive_runtime.models import CognitiveEvidence, ProgressSnapshot


def compute_progress_snapshot(
    *,
    blueprint: Any,
    evidence: list[CognitiveEvidence],
    readiness: Any | None = None,
    ledger_summary: dict[str, Any] | None = None,
) -> ProgressSnapshot:
    node_ids = [node.node_id for node in list(getattr(blueprint, "nodes", []) or [])]
    completed = sorted({
        str(item.provenance.get("blueprint_node_id") or item.payload.get("blueprint_node_id") or item.payload.get("node_id"))
        for item in evidence
        if item.evidence_type in {"node_satisfied", "blueprint_node_satisfied", "completion_evidence"}
        and (item.provenance.get("blueprint_node_id") or item.payload.get("blueprint_node_id") or item.payload.get("node_id"))
    })
    ready = [
        node_id for node_id in list(getattr(readiness, "ready_nodes", []) or [])
        if node_id not in set(completed)
    ]
    blocked = list(getattr(readiness, "blocked_nodes", []) or [])
    waiting = list(getattr(readiness, "waiting_nodes", []) or [])
    total_nodes = len(node_ids)
    covered_nodes = len(set(completed) | set(ready) | set(blocked) | set(waiting))
    evidence_coverage = covered_nodes / total_nodes if total_nodes else 0.0
    completion_percentage = len(set(completed)) / total_nodes if total_nodes else 0.0
    return ProgressSnapshot(
        mission_id=str(getattr(blueprint, "mission_id", "")),
        blueprint_id=str(getattr(blueprint, "blueprint_id", "")),
        blueprint_revision=int(getattr(blueprint, "revision", 1) or 1),
        completed_nodes=completed,
        ready_nodes=ready,
        blocked_nodes=blocked,
        waiting_nodes=waiting,
        evidence_coverage=round(evidence_coverage, 4),
        completion_percentage=round(completion_percentage, 4),
        metadata={
            "ledger_summary": dict(ledger_summary or {}),
            "diagnostic_only": True,
            "execution_impact": "none",
        },
    )
