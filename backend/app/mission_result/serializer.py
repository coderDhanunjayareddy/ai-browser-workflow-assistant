from __future__ import annotations

from app.mission_result.models import MissionResult, MissionResultArtifact, MissionResultSummary


def serialize_result(result: MissionResult) -> dict:
    return result.model_dump(mode="json")


def serialize_artifact(artifact: MissionResultArtifact) -> dict:
    return artifact.model_dump(mode="json")


def serialize_summary(summary: MissionResultSummary) -> dict:
    return summary.model_dump(mode="json")
