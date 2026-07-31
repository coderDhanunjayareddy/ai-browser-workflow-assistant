from __future__ import annotations

from typing import Any

from app.cognitive_runtime.diagnostics import EvidenceDiagnostics
from app.cognitive_runtime.interpreter import EvidenceInterpretation
from app.cognitive_runtime.models import CognitiveCheckpoint, CognitiveMetrics, CognitiveMission, ProgressSnapshot
from app.cognitive_runtime.service import CognitiveRuntimeService


class CognitiveRuntimeController:
    """Read-only/passive controller for Cognitive Runtime V2 Wave 1."""

    def __init__(self, service: CognitiveRuntimeService):
        self.service = service

    def initialize(
        self,
        *,
        mission_id: str,
        blueprint_id: str,
        blueprint_revision: int,
        metadata: dict[str, Any] | None = None,
    ) -> CognitiveMission:
        return self.service.create_runtime(
            mission_id=mission_id,
            blueprint_id=blueprint_id,
            blueprint_revision=blueprint_revision,
            metadata=metadata,
        )

    def snapshot(self, *, mission_id: str, blueprint: Any, readiness: Any | None = None) -> ProgressSnapshot:
        return self.service.compute_progress_snapshot(
            mission_id=mission_id,
            blueprint=blueprint,
            readiness=readiness,
            ledger_summary={"source": "cognitive_runtime_wave1", "execution_impact": "none"},
        )

    def checkpoint(self, mission_id: str, serialized_state: dict[str, Any]) -> CognitiveCheckpoint:
        return self.service.save_checkpoint(mission_id, serialized_state)

    def restore(self, mission_id: str, checkpoint_id: str | None = None) -> CognitiveCheckpoint | None:
        return self.service.restore_checkpoint(mission_id, checkpoint_id)

    def metrics(self, mission_id: str) -> CognitiveMetrics:
        return self.service.retrieve_metrics(mission_id)

    def interpret(self, *, mission_id: str, blueprint: Any | None) -> EvidenceInterpretation:
        return self.service.interpret_evidence(mission_id=mission_id, blueprint=blueprint)

    def diagnostics(self, *, mission_id: str, blueprint: Any | None) -> EvidenceDiagnostics:
        return self.service.evidence_diagnostics(mission_id=mission_id, blueprint=blueprint)
