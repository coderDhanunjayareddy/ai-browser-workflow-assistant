from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.mission_result.models import MissionResult, MissionResultArtifact, MissionResultArtifactSummary, MissionResultSummary, MissionResultVersion
from app.mission_result.persistence import MissionResultArtifactRecord, MissionResultRecord, MissionResultVersionRecord


class MissionResultRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, result: MissionResult, *, reason: str = "mission_result_builder") -> MissionResult:
        existing = self.latest_for_mission(result.mission_id)
        if existing is not None and existing.mission_result_id == result.mission_result_id:
            record = self.db.get(MissionResultRecord, result.mission_result_id)
            if record is None:
                raise LookupError(f"Mission Result {result.mission_result_id!r} not found")
            record.outcome = result.outcome
            record.final_answer = result.final_answer
            record.report_format = result.report_format
            record.report_artifact_id = result.report_artifact_id
            record.knowledge_artifact_id = result.knowledge_artifact_id
            record.completion_reason = result.completion_reason
            record.confidence = result.confidence
            record.result_metadata = result.metadata
            record.updated_at = datetime.utcnow()
            self.db.query(MissionResultArtifactRecord).filter(
                MissionResultArtifactRecord.mission_result_id == result.mission_result_id
            ).delete()
        else:
            record = MissionResultRecord(
                mission_result_id=result.mission_result_id,
                mission_id=result.mission_id,
                outcome=result.outcome,
                final_answer=result.final_answer,
                report_format=result.report_format,
                report_artifact_id=result.report_artifact_id,
                knowledge_artifact_id=result.knowledge_artifact_id,
                completion_reason=result.completion_reason,
                confidence=result.confidence,
                result_metadata=result.metadata,
                created_at=result.created_at,
                updated_at=result.updated_at,
            )
            self.db.add(record)

        for artifact in result.artifacts:
            self.db.add(
                MissionResultArtifactRecord(
                    artifact_id=artifact.artifact_id,
                    mission_result_id=artifact.mission_result_id,
                    mission_id=artifact.mission_id,
                    kind=artifact.kind,
                    title=artifact.title,
                    content_type=artifact.content_type,
                    content=artifact.content,
                    structured=artifact.structured,
                    artifact_metadata=artifact.metadata,
                    created_at=artifact.created_at,
                )
            )

        next_version = self._next_version(result.mission_result_id)
        self.db.add(
            MissionResultVersionRecord(
                version_id=f"{result.mission_result_id}_v{next_version}",
                mission_result_id=result.mission_result_id,
                mission_id=result.mission_id,
                version=next_version,
                reason=reason,
                snapshot=result.model_dump(mode="json"),
                created_at=datetime.utcnow(),
            )
        )
        self.db.commit()
        return self.get(result.mission_id) or result

    def get(self, mission_id: str) -> MissionResult | None:
        record = self._latest_record(mission_id)
        if record is None:
            return None
        artifacts = (
            self.db.query(MissionResultArtifactRecord)
            .filter(MissionResultArtifactRecord.mission_result_id == record.mission_result_id)
            .order_by(MissionResultArtifactRecord.created_at.asc())
            .all()
        )
        return _result_from_record(record, artifacts)

    def latest_for_mission(self, mission_id: str) -> MissionResult | None:
        return self.get(mission_id)

    def artifacts(self, mission_id: str) -> list[MissionResultArtifact]:
        result = self.get(mission_id)
        return result.artifacts if result else []

    def artifact_summaries(self, mission_id: str) -> list[MissionResultArtifactSummary]:
        return [_artifact_summary(artifact) for artifact in self.artifacts(mission_id)]

    def summary(self, mission_id: str) -> MissionResultSummary | None:
        result = self.get(mission_id)
        if result is None:
            return None
        return MissionResultSummary(
            mission_result_id=result.mission_result_id,
            mission_id=result.mission_id,
            outcome=result.outcome,
            report_artifact_id=result.report_artifact_id,
            knowledge_artifact_id=result.knowledge_artifact_id,
            completion_reason=result.completion_reason,
            confidence=result.confidence,
            artifact_count=len(result.artifacts),
            created_at=result.created_at,
            updated_at=result.updated_at,
        )

    def versions(self, mission_id: str) -> list[MissionResultVersion]:
        record = self._latest_record(mission_id)
        if record is None:
            return []
        versions = (
            self.db.query(MissionResultVersionRecord)
            .filter(MissionResultVersionRecord.mission_result_id == record.mission_result_id)
            .order_by(MissionResultVersionRecord.version.asc())
            .all()
        )
        return [
            MissionResultVersion(
                version_id=item.version_id,
                mission_result_id=item.mission_result_id,
                mission_id=item.mission_id,
                version=item.version,
                reason=item.reason,
                snapshot=dict(item.snapshot or {}),
                created_at=item.created_at,
            )
            for item in versions
        ]

    def _latest_record(self, mission_id: str) -> MissionResultRecord | None:
        return (
            self.db.query(MissionResultRecord)
            .filter(MissionResultRecord.mission_id == mission_id)
            .order_by(MissionResultRecord.created_at.desc())
            .first()
        )

    def _next_version(self, mission_result_id: str) -> int:
        latest = (
            self.db.query(MissionResultVersionRecord)
            .filter(MissionResultVersionRecord.mission_result_id == mission_result_id)
            .order_by(MissionResultVersionRecord.version.desc())
            .first()
        )
        return int(latest.version if latest else 0) + 1


def _result_from_record(record: MissionResultRecord, artifacts: list[MissionResultArtifactRecord]) -> MissionResult:
    return MissionResult(
        mission_result_id=record.mission_result_id,
        mission_id=record.mission_id,
        outcome=record.outcome,  # type: ignore[arg-type]
        final_answer=record.final_answer,
        report_format=record.report_format,
        report_artifact_id=record.report_artifact_id,
        knowledge_artifact_id=record.knowledge_artifact_id,
        completion_reason=record.completion_reason,
        confidence=float(record.confidence or 0.0),
        metadata=dict(record.result_metadata or {}),
        artifacts=[_artifact_from_record(artifact) for artifact in artifacts],
        created_at=record.created_at,
        updated_at=record.updated_at or record.created_at,
    )


def _artifact_from_record(record: MissionResultArtifactRecord) -> MissionResultArtifact:
    return MissionResultArtifact(
        artifact_id=record.artifact_id,
        mission_result_id=record.mission_result_id,
        mission_id=record.mission_id,
        kind=record.kind,  # type: ignore[arg-type]
        title=record.title,
        content_type=record.content_type,
        content=record.content,
        structured=dict(record.structured or {}),
        metadata=dict(record.artifact_metadata or {}),
        created_at=record.created_at,
    )


def _artifact_summary(artifact: MissionResultArtifact) -> MissionResultArtifactSummary:
    return MissionResultArtifactSummary(
        artifact_id=artifact.artifact_id,
        mission_result_id=artifact.mission_result_id,
        mission_id=artifact.mission_id,
        kind=artifact.kind,
        title=artifact.title,
        content_type=artifact.content_type,
        metadata=artifact.metadata,
        created_at=artifact.created_at,
    )
