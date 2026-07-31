from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from app.cognitive_runtime.comparison_repository import DecisionComparisonRepository
from app.cognitive_runtime.comparison_service import DecisionComparisonService
from app.cognitive_runtime.metrics import compute_metrics
from app.cognitive_runtime.models import (
    CognitiveCheckpoint,
    CognitiveEvidence,
    CognitiveMetrics,
    CognitiveMission,
    EvidenceCollection,
    ProgressSnapshot,
)
from app.cognitive_runtime.diagnostics import EvidenceDiagnostics, build_diagnostics
from app.cognitive_runtime.decision_engine import CognitiveDecisionContext, CognitiveDecisionEngine
from app.cognitive_runtime.policy import DecisionPolicy
from app.cognitive_runtime.recommendations import RecommendationResult
from app.cognitive_runtime.interpreter import EvidenceInterpretation, EvidenceInterpreter
from app.cognitive_runtime.clarification import ClarificationDiagnostics, ClarificationEngine
from app.cognitive_runtime.lifecycle import LifecycleSummary, MissionLifecycleAnalyzer
from app.cognitive_runtime.progress import compute_progress_snapshot
from app.cognitive_runtime.recovery import RecoveryDiagnostics, RecoveryStateEvaluator
from app.cognitive_runtime.replanning import ReplanningDiagnostics, ReplanningEvaluator
from app.cognitive_runtime.repository import CognitiveRuntimeRepository
from app.cognitive_runtime.snapshots import CognitiveReasoningSnapshot, CognitiveSnapshotBuilder
from app.cognitive_runtime.state_machine import CognitiveStateSnapshot, CognitiveStateMachine
from app.cognitive_runtime.transitions import TransitionDiagnostics, TransitionEngine, TransitionRecord
from app.cognitive_runtime.waits import WaitDiagnostics, WaitStateEvaluator


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

    def interpret_evidence(self, *, mission_id: str, blueprint: Any | None) -> EvidenceInterpretation:
        collection = self.evidence_collection(mission_id)
        return EvidenceInterpreter().interpret(blueprint=blueprint, collection=collection)

    def evidence_diagnostics(self, *, mission_id: str, blueprint: Any | None) -> EvidenceDiagnostics:
        return build_diagnostics(blueprint=blueprint, collection=self.evidence_collection(mission_id))

    def cognitive_state(self, *, mission_id: str, readiness: Any | None = None, blueprint: Any | None = None) -> CognitiveStateSnapshot:
        mission = self._require_runtime(mission_id)
        collection = self.evidence_collection(mission_id)
        clarification = ClarificationEngine().evaluate(blueprint=blueprint, evidence=collection)
        wait_state = WaitStateEvaluator().evaluate(collection)
        recovery = RecoveryStateEvaluator().evaluate(collection)
        diagnostics = self.evidence_diagnostics(mission_id=mission_id, blueprint=blueprint)
        replanning = ReplanningEvaluator().evaluate(collection, contradiction_count=len(diagnostics.contradictions))
        return CognitiveStateMachine().determine_state(
            evidence_count=len(collection.evidence),
            ready_nodes=list(getattr(readiness, "ready_nodes", []) or []),
            blocked_nodes=list(getattr(readiness, "blocked_nodes", []) or []),
            waiting_nodes=list(getattr(readiness, "waiting_nodes", []) or []),
            clarification_required=clarification.required_count > 0,
            wait_kind=wait_state.primary_wait,
            recovery_status=recovery.classification,
            replanning_status=replanning.recommendation,
        )

    def transition_diagnostics(self, mission_id: str) -> TransitionDiagnostics:
        mission = self._require_runtime(mission_id)
        return TransitionEngine(initial_state=mission.state).diagnostics()

    def wait_diagnostics(self, mission_id: str) -> WaitDiagnostics:
        return WaitStateEvaluator().evaluate(self.evidence_collection(mission_id))

    def clarification_diagnostics(self, *, mission_id: str, blueprint: Any | None) -> ClarificationDiagnostics:
        return ClarificationEngine().evaluate(blueprint=blueprint, evidence=self.evidence_collection(mission_id))

    def recovery_diagnostics(self, mission_id: str) -> RecoveryDiagnostics:
        return RecoveryStateEvaluator().evaluate(self.evidence_collection(mission_id))

    def replanning_diagnostics(self, *, mission_id: str, blueprint: Any | None) -> ReplanningDiagnostics:
        collection = self.evidence_collection(mission_id)
        diagnostics = self.evidence_diagnostics(mission_id=mission_id, blueprint=blueprint)
        return ReplanningEvaluator().evaluate(collection, contradiction_count=len(diagnostics.contradictions))

    def lifecycle_summary(self, mission_id: str, transitions: list[TransitionRecord] | None = None) -> LifecycleSummary:
        return MissionLifecycleAnalyzer().analyze(mission=self._require_runtime(mission_id), transitions=transitions)

    def reasoning_snapshot(
        self,
        *,
        mission_id: str,
        blueprint: Any | None,
        readiness: Any | None = None,
    ) -> CognitiveReasoningSnapshot:
        return CognitiveSnapshotBuilder().build(
            mission=self._require_runtime(mission_id),
            blueprint=blueprint,
            evidence=self.evidence_collection(mission_id),
            readiness=readiness,
        )

    def cognitive_decision(
        self,
        *,
        mission_id: str,
        blueprint: Any | None,
        readiness: Any | None = None,
        policy_name: str | None = None,
    ) -> RecommendationResult:
        self._require_runtime(mission_id)
        return CognitiveDecisionEngine().decide(
            CognitiveDecisionContext(
                blueprint=blueprint,
                readiness=readiness,
                evidence=self.evidence_collection(mission_id),
                policy=DecisionPolicy.from_name(policy_name),
            )
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


def comparison_service(repository: DecisionComparisonRepository) -> DecisionComparisonService:
    return DecisionComparisonService(repository)
