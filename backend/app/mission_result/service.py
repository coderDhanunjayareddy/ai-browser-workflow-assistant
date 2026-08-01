from __future__ import annotations

from sqlalchemy.orm import Session

from app.knowledge_extraction.models import KnowledgePipelineSnapshot
from app.mission_completion import observe_mission_completion
from app.mission_completion.models import CompletionDecision
from app.mission_result.builder import MissionResultBuilder
from app.mission_result.models import MissionResult, MissionResultArtifact, MissionResultArtifactSummary, MissionResultSummary
from app.mission_result.repository import MissionResultRepository


class MissionResultService:
    def __init__(self, db: Session) -> None:
        self.repository = MissionResultRepository(db)
        self.builder = MissionResultBuilder()

    def persist_from_knowledge_snapshot(
        self,
        *,
        mission_id: str,
        task: str,
        knowledge_snapshot: KnowledgePipelineSnapshot,
    ) -> MissionResult | None:
        completion = observe_mission_completion(
            session_id=mission_id,
            task=task,
            knowledge_snapshot=knowledge_snapshot,
        )
        if completion is None or completion.workflow_result is None:
            return None
        if completion.decision not in {
            CompletionDecision.COMPLETE,
            CompletionDecision.PARTIAL_SUCCESS,
            CompletionDecision.FAILED,
        }:
            return None
        result = self.builder.build(
            mission_id=mission_id,
            task=task,
            knowledge_snapshot=knowledge_snapshot,
            completion_snapshot=completion,
        )
        if result is None:
            return None
        return self.repository.save(result, reason="generate_report_completed")

    def get(self, mission_id: str) -> MissionResult | None:
        return self.repository.get(mission_id)

    def artifacts(self, mission_id: str) -> list[MissionResultArtifact]:
        return self.repository.artifacts(mission_id)

    def artifact_summaries(self, mission_id: str) -> list[MissionResultArtifactSummary]:
        return self.repository.artifact_summaries(mission_id)

    def summary(self, mission_id: str) -> MissionResultSummary | None:
        return self.repository.summary(mission_id)
