from __future__ import annotations

from typing import Any

from app.orchestrator.report_verifier import collect_page_evidence
from app.schemas.request import PageContext
from app.semantic_page.graph import SemanticPageGraph
from app.verification.models import ValidationEvidence


def collect_report_evidence(
    *,
    page_context: PageContext,
    semantic_graph: SemanticPageGraph | None = None,
    limit: int = 30,
) -> list[ValidationEvidence]:
    evidence: list[ValidationEvidence] = []
    for index, text in enumerate(collect_page_evidence(page_context)[:limit]):
        evidence.append(
            ValidationEvidence(
                evidence_id=f"page_text.{index + 1}",
                source="page_context",
                kind="visible_text",
                value=text,
            )
        )
    if semantic_graph is not None:
        evidence.append(
            ValidationEvidence(
                evidence_id="semantic_graph.snapshot",
                source="semantic_page_graph",
                kind="graph_reference",
                value=semantic_graph.graph_id,
                metadata={
                    "schema_version": semantic_graph.schema_version,
                    "observation_id": semantic_graph.observation_id,
                    "page_type": semantic_graph.page_type,
                    "target_count": len(semantic_graph.targets),
                    "fact_count": len(semantic_graph.facts),
                },
            )
        )
    return evidence


def collect_execution_evidence(
    *,
    action_type: str,
    selector: str,
    success: bool,
    execution_result: str,
    before_url: str | None = None,
    after_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[ValidationEvidence]:
    return [
        ValidationEvidence(
            evidence_id="execution.metadata",
            source="execution",
            kind="action_result",
            value=execution_result,
            metadata={
                "action_type": action_type,
                "selector_present": bool(selector),
                "success": success,
                "before_url": before_url,
                "after_url": after_url,
                **(metadata or {}),
            },
        )
    ]
