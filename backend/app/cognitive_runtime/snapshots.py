from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.clarification import ClarificationDiagnostics, ClarificationEngine
from app.cognitive_runtime.diagnostics import build_diagnostics
from app.cognitive_runtime.lifecycle import LifecycleSummary, MissionLifecycleAnalyzer
from app.cognitive_runtime.models import CognitiveMission, EvidenceCollection
from app.cognitive_runtime.progress import compute_progress_snapshot
from app.cognitive_runtime.recovery import RecoveryDiagnostics, RecoveryStateEvaluator
from app.cognitive_runtime.replanning import ReplanningDiagnostics, ReplanningEvaluator
from app.cognitive_runtime.state_machine import CognitiveStateMachine, CognitiveStateSnapshot
from app.cognitive_runtime.waits import WaitDiagnostics, WaitStateEvaluator


@dataclass(frozen=True)
class CognitiveReasoningSnapshot:
    mission_id: str
    cognitive_state: dict[str, Any]
    evidence_summary: dict[str, Any]
    readiness_summary: dict[str, Any]
    wait_state: dict[str, Any]
    clarification_summary: dict[str, Any]
    recovery_summary: dict[str, Any]
    replanning_summary: dict[str, Any]
    progress_summary: dict[str, Any]
    lifecycle_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CognitiveSnapshotBuilder:
    """Builds a complete read-only reasoning snapshot."""

    def build(
        self,
        *,
        mission: CognitiveMission,
        blueprint: Any | None,
        evidence: EvidenceCollection,
        readiness: Any | None = None,
    ) -> CognitiveReasoningSnapshot:
        diagnostics = build_diagnostics(blueprint=blueprint, collection=evidence)
        wait_state: WaitDiagnostics = WaitStateEvaluator().evaluate(evidence)
        clarification: ClarificationDiagnostics = ClarificationEngine().evaluate(blueprint=blueprint, evidence=evidence)
        recovery: RecoveryDiagnostics = RecoveryStateEvaluator().evaluate(evidence)
        replanning: ReplanningDiagnostics = ReplanningEvaluator().evaluate(
            evidence,
            contradiction_count=len(diagnostics.contradictions),
        )
        progress = compute_progress_snapshot(
            blueprint=blueprint,
            evidence=list(evidence.evidence),
            readiness=readiness,
            ledger_summary={"source": "cognitive_snapshot_builder", "execution_impact": "none"},
        )
        state: CognitiveStateSnapshot = CognitiveStateMachine().determine_state(
            evidence_count=len(evidence.evidence),
            ready_nodes=list(getattr(readiness, "ready_nodes", []) or []),
            blocked_nodes=list(getattr(readiness, "blocked_nodes", []) or []),
            waiting_nodes=list(getattr(readiness, "waiting_nodes", []) or []),
            clarification_required=clarification.required_count > 0,
            wait_kind=wait_state.primary_wait,
            recovery_status=recovery.classification,
            replanning_status=replanning.recommendation,
        )
        lifecycle: LifecycleSummary = MissionLifecycleAnalyzer().analyze(mission=mission)
        return CognitiveReasoningSnapshot(
            mission_id=mission.mission_id,
            cognitive_state=state.to_dict(),
            evidence_summary=diagnostics.to_dict(),
            readiness_summary={
                "ready_nodes": list(getattr(readiness, "ready_nodes", []) or []),
                "blocked_nodes": list(getattr(readiness, "blocked_nodes", []) or []),
                "waiting_nodes": list(getattr(readiness, "waiting_nodes", []) or []),
            },
            wait_state=wait_state.to_dict(),
            clarification_summary=clarification.to_dict(),
            recovery_summary=recovery.to_dict(),
            replanning_summary=replanning.to_dict(),
            progress_summary=progress.to_dict(),
            lifecycle_summary=lifecycle.to_dict(),
        )
