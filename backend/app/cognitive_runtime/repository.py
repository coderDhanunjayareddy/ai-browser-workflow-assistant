from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.cognitive_runtime.models import (
    CognitiveCheckpoint,
    CognitiveEvidence,
    CognitiveMetrics,
    CognitiveMission,
)
from app.models.db import (
    CognitiveCheckpointRecord,
    CognitiveEvidenceRecord,
    CognitiveMetricsRecord,
    CognitiveRuntimeMissionRecord,
)


class CognitiveRuntimeRepository(ABC):
    @abstractmethod
    def create(self, mission: CognitiveMission) -> CognitiveMission:
        raise NotImplementedError

    @abstractmethod
    def update(self, mission: CognitiveMission) -> CognitiveMission:
        raise NotImplementedError

    @abstractmethod
    def get(self, mission_id: str) -> CognitiveMission | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, mission_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def save_checkpoint(self, checkpoint: CognitiveCheckpoint) -> CognitiveCheckpoint:
        raise NotImplementedError

    @abstractmethod
    def list_checkpoints(self, mission_id: str) -> list[CognitiveCheckpoint]:
        raise NotImplementedError

    @abstractmethod
    def save_metrics(self, metrics: CognitiveMetrics) -> CognitiveMetrics:
        raise NotImplementedError

    @abstractmethod
    def get_metrics(self, mission_id: str) -> CognitiveMetrics | None:
        raise NotImplementedError

    @abstractmethod
    def save_evidence(self, evidence: CognitiveEvidence) -> CognitiveEvidence:
        raise NotImplementedError

    @abstractmethod
    def list_evidence(self, mission_id: str) -> list[CognitiveEvidence]:
        raise NotImplementedError


class SqlAlchemyCognitiveRuntimeRepository(CognitiveRuntimeRepository):
    def __init__(self, db: Session):
        self.db = db

    def create(self, mission: CognitiveMission) -> CognitiveMission:
        existing = self.db.get(CognitiveRuntimeMissionRecord, mission.mission_id)
        if existing is not None:
            return _mission_from_record(existing)
        record = CognitiveRuntimeMissionRecord(
            mission_id=mission.mission_id,
            blueprint_id=mission.blueprint_id,
            blueprint_revision=mission.blueprint_revision,
            runtime_version=mission.runtime_version.runtime_version,
            schema_version=mission.runtime_version.schema_version,
            state=mission.state.value,
            runtime_metadata=dict(mission.metadata),
            snapshot=mission.to_dict(),
            created_at=mission.created_at,
            updated_at=mission.updated_at,
        )
        self.db.add(record)
        self.db.commit()
        return mission

    def update(self, mission: CognitiveMission) -> CognitiveMission:
        record = self.db.get(CognitiveRuntimeMissionRecord, mission.mission_id)
        if record is None:
            return self.create(mission)
        record.blueprint_id = mission.blueprint_id
        record.blueprint_revision = mission.blueprint_revision
        record.runtime_version = mission.runtime_version.runtime_version
        record.schema_version = mission.runtime_version.schema_version
        record.state = mission.state.value
        record.runtime_metadata = dict(mission.metadata)
        record.snapshot = mission.to_dict()
        record.updated_at = mission.updated_at
        self.db.commit()
        return mission

    def get(self, mission_id: str) -> CognitiveMission | None:
        record = self.db.get(CognitiveRuntimeMissionRecord, mission_id)
        return _mission_from_record(record) if record is not None else None

    def delete(self, mission_id: str) -> bool:
        record = self.db.get(CognitiveRuntimeMissionRecord, mission_id)
        if record is None:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def save_checkpoint(self, checkpoint: CognitiveCheckpoint) -> CognitiveCheckpoint:
        record = CognitiveCheckpointRecord(
            checkpoint_id=checkpoint.checkpoint_id,
            mission_id=checkpoint.mission_id,
            blueprint_revision=checkpoint.blueprint_revision,
            serialized_state=dict(checkpoint.serialized_state),
            created_at=checkpoint.timestamp,
        )
        self.db.merge(record)
        self.db.commit()
        return checkpoint

    def list_checkpoints(self, mission_id: str) -> list[CognitiveCheckpoint]:
        records = (
            self.db.query(CognitiveCheckpointRecord)
            .filter(CognitiveCheckpointRecord.mission_id == mission_id)
            .order_by(CognitiveCheckpointRecord.created_at.asc())
            .all()
        )
        return [_checkpoint_from_record(record) for record in records]

    def save_metrics(self, metrics: CognitiveMetrics) -> CognitiveMetrics:
        record = CognitiveMetricsRecord(
            mission_id=metrics.mission_id,
            reasoning_iterations=metrics.reasoning_iterations,
            clarification_count=metrics.clarification_count,
            evidence_count=metrics.evidence_count,
            confidence_average=metrics.confidence_average,
            recovery_count=metrics.recovery_count,
            replanning_count=metrics.replanning_count,
            execution_duration_ms=metrics.execution_duration_ms,
            metrics_metadata=dict(metrics.metadata),
            snapshot=metrics.to_dict(),
            updated_at=metrics.updated_at,
        )
        self.db.merge(record)
        self.db.commit()
        return metrics

    def get_metrics(self, mission_id: str) -> CognitiveMetrics | None:
        record = self.db.get(CognitiveMetricsRecord, mission_id)
        return _metrics_from_record(record) if record is not None else None

    def save_evidence(self, evidence: CognitiveEvidence) -> CognitiveEvidence:
        record = CognitiveEvidenceRecord(
            evidence_id=evidence.evidence_id,
            mission_id=evidence.mission_id,
            source=evidence.source,
            provider=evidence.provider,
            evidence_type=evidence.evidence_type,
            confidence=evidence.confidence,
            payload=dict(evidence.payload),
            provenance=dict(evidence.provenance),
            created_at=evidence.timestamp,
        )
        self.db.merge(record)
        self.db.commit()
        return evidence

    def list_evidence(self, mission_id: str) -> list[CognitiveEvidence]:
        records = (
            self.db.query(CognitiveEvidenceRecord)
            .filter(CognitiveEvidenceRecord.mission_id == mission_id)
            .order_by(CognitiveEvidenceRecord.created_at.asc())
            .all()
        )
        return [_evidence_from_record(record) for record in records]


def new_evidence_id() -> str:
    return f"cognitive_evidence_{uuid.uuid4().hex}"


def _mission_from_record(record: CognitiveRuntimeMissionRecord) -> CognitiveMission:
    return CognitiveMission.from_dict(dict(record.snapshot or {}))


def _checkpoint_from_record(record: CognitiveCheckpointRecord) -> CognitiveCheckpoint:
    return CognitiveCheckpoint.from_dict(
        {
            "checkpoint_id": record.checkpoint_id,
            "mission_id": record.mission_id,
            "blueprint_revision": record.blueprint_revision,
            "serialized_state": record.serialized_state,
            "timestamp": record.created_at,
        }
    )


def _metrics_from_record(record: CognitiveMetricsRecord) -> CognitiveMetrics:
    if record.snapshot:
        return CognitiveMetrics.from_dict(dict(record.snapshot))
    return CognitiveMetrics(
        mission_id=record.mission_id,
        reasoning_iterations=record.reasoning_iterations,
        clarification_count=record.clarification_count,
        evidence_count=record.evidence_count,
        confidence_average=record.confidence_average,
        recovery_count=record.recovery_count,
        replanning_count=record.replanning_count,
        execution_duration_ms=record.execution_duration_ms,
        metadata=dict(record.metrics_metadata or {}),
        updated_at=record.updated_at,
    )


def _evidence_from_record(record: CognitiveEvidenceRecord) -> CognitiveEvidence:
    return CognitiveEvidence(
        evidence_id=record.evidence_id,
        mission_id=record.mission_id,
        source=record.source,
        provider=record.provider,
        evidence_type=record.evidence_type,
        payload=dict(record.payload or {}),
        confidence=record.confidence,
        timestamp=_timestamp(record.created_at),
        provenance=dict(record.provenance or {}),
    )


def _timestamp(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.utcnow()
