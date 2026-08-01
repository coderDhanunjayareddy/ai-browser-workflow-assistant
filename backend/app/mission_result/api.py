from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.mission_result.models import MissionResult, MissionResultArtifact, MissionResultArtifactSummary, MissionResultSummary
from app.mission_result.service import MissionResultService


router = APIRouter(tags=["mission-result"])


@router.get("/{mission_id}/result", response_model=MissionResult)
def get_result(mission_id: str, db: Session = Depends(get_db)) -> MissionResult:
    result = MissionResultService(db).get(mission_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Mission Result for mission {mission_id!r} not found")
    return result


@router.get("/{mission_id}/result/artifacts", response_model=list[MissionResultArtifactSummary])
def get_result_artifacts(mission_id: str, db: Session = Depends(get_db)) -> list[MissionResultArtifactSummary]:
    service = MissionResultService(db)
    if service.get(mission_id) is None:
        raise HTTPException(status_code=404, detail=f"Mission Result for mission {mission_id!r} not found")
    return service.artifact_summaries(mission_id)


@router.get("/{mission_id}/result/summary", response_model=MissionResultSummary)
def get_result_summary(mission_id: str, db: Session = Depends(get_db)) -> MissionResultSummary:
    summary = MissionResultService(db).summary(mission_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Mission Result for mission {mission_id!r} not found")
    return summary


@router.get("/{mission_id}/result/download")
def download_result(mission_id: str, db: Session = Depends(get_db)) -> Response:
    result = MissionResultService(db).get(mission_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Mission Result for mission {mission_id!r} not found")
    artifact = _download_artifact(result.artifacts)
    filename = f"mission-result-{mission_id}.md"
    return Response(
        content=artifact.content or result.final_answer,
        media_type=artifact.content_type or "text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _download_artifact(artifacts: list[MissionResultArtifact]) -> MissionResultArtifact:
    for artifact in artifacts:
        if artifact.kind == "markdown_report":
            return artifact
    if artifacts:
        return artifacts[0]
    raise HTTPException(status_code=404, detail="Mission Result has no downloadable artifacts")
