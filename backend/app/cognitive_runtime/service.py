from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.cognitive_runtime.metrics import compute_metrics
from app.cognitive_runtime.models import (
    CognitiveCheckpoint,
    CognitiveEvidence,
    CognitiveMetrics,
    CognitiveMission,
    EvidenceCollection,
    ProgressSnapshot,
)
from app.cognitive_runtime.progress import compute_progress_snapshot
from app.cognitive_runtime.repository import CognitiveRuntimeRepository


class CognitiveRuntimeService:
    """Passive Cognitive Runtime V2 service. It never executes providers or creates intents."""

    def __init__(self, repository: CognitiveRuntimeRepository):
        self.repository = repository

    def create_runtime(
        self,
        *,
        mission_id: str,
        blueprint_id: str,
        blueprint_revision: int,
        metadata: dict[str, Any] | None = None,
    ) -> CognitiveMission:
        mission = CognitiveMission(
            mission_id=mission_id,
            blueprint_id=blueprint_id,
            blueprint_revision=blueprint_revision,
            metadata={"execution_impact": "none", **dict(metadata or {})},
        )
        return self.repository.create(mission)

    def load_runtime(self, mission_id: str) -> CognitiveMission | None:
        return self.repository.get(mission_id)

    def save_checkpoint(self, mission_id: str, serialized_state: dict[str, Any]) -> CognitiveCheckpoint:
        mission = self._require_runtime(mission_id)
        checkpoint = CognitiveCheckpoint.create(
            mission_id=mission_id,
            blueprint_revision=mission.blueprint_revision,
            serialized_state=serialized_state,
        )
        return self.repository.save_checkpoint(checkpoint)

    def restore_checkpoint(self, mission_id: str, checkpoint_id: str | None = None) -> CognitiveCheckpoint | None:
        checkpoints = self.repository.list_checkpoints(mission_id)
        if checkpoint_id is None:
            return checkpoints[-1] if checkpoints else None
        return next((item for item in checkpoints if item.checkpoint_id == checkpoint_id), None)

    def list_checkpoints(self, mission_id: str) -> list[CognitiveCheckpoint]:
        return self.repository.list_checkpoints(mission_id)

    def attach_evidence(self, evidence: CognitiveEvidence) -> CognitiveEvidence:
        saved = self.repository.save_evidence(evidence)
        metrics = compute_metrics(
            mission_id=evidence.mission_id,
            evidence=self.repository.list_evidence(evidence.mission_id),
            previous=self.repository.get_metrics(evidence.mission_id),
        )
        self.repository.save_metrics(metrics)
        mission = self.repository.get(evidence.mission_id)
        if mission is not None:
            self.repository.update(replace(mission, updated_at=datetime.now(UTC)))
        return saved

    def evidence_collection(self, mission_id: str) -> EvidenceCollection:
        return EvidenceCollection(mission_id=mission_id, evidence=tuple(self.repository.list_evidence(mission_id)))

    def compute_progress_snapshot(
        self,
        *,
        mission_id: str,
        blueprint: Any,
        readiness: Any | None = None,
        ledger_summary: dict[str, Any] | None = None,
    ) -> ProgressSnapshot:
        evidence = self.repository.list_evidence(mission_id)
        return compute_progress_snapshot(
            blueprint=blueprint,
            evidence=evidence,
            readiness=readiness,
            ledger_summary=ledger_summary,
        )

    def retrieve_metrics(self, mission_id: str) -> CognitiveMetrics:
        existing = self.repository.get_metrics(mission_id)
        if existing is not None:
            return existing
        return compute_metrics(mission_id=mission_id, evidence=self.repository.list_evidence(mission_id))

    def _require_runtime(self, mission_id: str) -> CognitiveMission:
        mission = self.repository.get(mission_id)
        if mission is None:
            raise LookupError(f"Cognitive Runtime for mission {mission_id!r} not found")
        return mission
