from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from app.knowledge_extraction.models import KnowledgePipelineSnapshot
from app.mission_completion.models import MissionCompletionSnapshot
from app.mission_result.models import MissionResult, MissionResultArtifact


class MissionResultBuilder:
    def build(
        self,
        *,
        mission_id: str,
        task: str,
        knowledge_snapshot: KnowledgePipelineSnapshot,
        completion_snapshot: MissionCompletionSnapshot,
    ) -> MissionResult | None:
        workflow_result = completion_snapshot.workflow_result
        if workflow_result is None or not workflow_result.report_artifact:
            return None

        report = dict(workflow_result.report_artifact)
        content = str(report.get("content") or "")
        if not content.strip():
            return None

        structured = dict(report.get("structured") or {})
        report_artifact_id = str(report.get("id") or "")
        knowledge_artifact_id = str(report.get("source_knowledge_id") or "")
        result_id = _stable_id("mission_result", mission_id, report_artifact_id, content)
        now = datetime.utcnow()
        metadata = {
            "schema_version": "mission_result.v1",
            "task": task,
            "mission_completion": completion_snapshot.to_compact_context(),
            "metrics": dict(workflow_result.metrics or {}),
            "evidence_summary": dict(workflow_result.evidence_summary or {}),
            "resource_usage": dict(workflow_result.resource_usage or {}),
            "replay_reference": workflow_result.replay_reference,
        }
        artifacts = [
            MissionResultArtifact(
                artifact_id=report_artifact_id or _stable_id("artifact", result_id, "markdown"),
                mission_result_id=result_id,
                mission_id=mission_id,
                kind="markdown_report",
                title="Mission Report",
                content_type="text/markdown",
                content=content,
                structured=structured,
                metadata={"format": report.get("format") or "markdown"},
                created_at=now,
            ),
            MissionResultArtifact(
                artifact_id=_stable_id("artifact", result_id, "structured_json"),
                mission_result_id=result_id,
                mission_id=mission_id,
                kind="structured_json",
                title="Structured Mission Result",
                content_type="application/json",
                content="",
                structured={
                    "columns": list(structured.get("columns") or []),
                    "rows": list(structured.get("rows") or []),
                    "records": [record.to_dict() for record in knowledge_snapshot.extraction_records],
                },
                metadata={"source_knowledge_id": knowledge_artifact_id},
                created_at=now,
            ),
        ]
        if structured.get("columns") and structured.get("rows"):
            artifacts.append(
                MissionResultArtifact(
                    artifact_id=_stable_id("artifact", result_id, "comparison_table"),
                    mission_result_id=result_id,
                    mission_id=mission_id,
                    kind="comparison_table",
                    title="Comparison Table",
                    content_type="application/json",
                    content="",
                    structured=structured,
                    metadata={"row_count": len(list(structured.get("rows") or []))},
                    created_at=now,
                )
            )

        return MissionResult(
            mission_result_id=result_id,
            mission_id=mission_id,
            outcome=completion_snapshot.status.value,  # type: ignore[arg-type]
            final_answer=content,
            report_format=str(report.get("format") or "markdown"),
            report_artifact_id=report_artifact_id or None,
            knowledge_artifact_id=knowledge_artifact_id or None,
            completion_reason=completion_snapshot.reason,
            confidence=float(completion_snapshot.confidence),
            metadata=metadata,
            artifacts=artifacts,
            created_at=now,
            updated_at=now,
        )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
