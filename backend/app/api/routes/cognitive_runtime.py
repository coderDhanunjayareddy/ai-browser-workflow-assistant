from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.cognitive_runtime.repository import SqlAlchemyCognitiveRuntimeRepository
from app.cognitive_runtime.service import CognitiveRuntimeService
from app.core.database import get_db
from app.feature_flags import is_shadow_or_active
from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository


router = APIRouter(tags=["cognitive-runtime-v2"])


@router.get("/{mission_id}/cognitive")
def get_cognitive_runtime(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    mission = service.load_runtime(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Cognitive Runtime for mission {mission_id!r} not found")
    return mission.to_dict()


@router.get("/{mission_id}/cognitive/checkpoints")
def get_cognitive_checkpoints(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return {
        "mission_id": mission_id,
        "checkpoints": [checkpoint.to_dict() for checkpoint in service.list_checkpoints(mission_id)],
    }


@router.get("/{mission_id}/cognitive/evidence")
def get_cognitive_evidence(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    collection = service.evidence_collection(mission_id)
    return collection.to_dict()


@router.get("/{mission_id}/cognitive/evidence/diagnostics")
def get_cognitive_evidence_diagnostics(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    blueprint = _blueprint(db, mission_id)
    return service.evidence_diagnostics(mission_id=mission_id, blueprint=blueprint).to_dict()


@router.get("/{mission_id}/cognitive/evidence/coverage")
def get_cognitive_evidence_coverage(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    blueprint = _blueprint(db, mission_id)
    diagnostics = service.evidence_diagnostics(mission_id=mission_id, blueprint=blueprint)
    return {
        "mission_id": mission_id,
        "coverage": diagnostics.coverage,
        "missing_evidence": diagnostics.missing_evidence,
    }


@router.get("/{mission_id}/cognitive/evidence/confidence")
def get_cognitive_evidence_confidence(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    blueprint = _blueprint(db, mission_id)
    diagnostics = service.evidence_diagnostics(mission_id=mission_id, blueprint=blueprint)
    return {
        "mission_id": mission_id,
        "confidence": diagnostics.confidence,
        "provider_distribution": diagnostics.provider_distribution,
    }


@router.get("/{mission_id}/cognitive/evidence/contradictions")
def get_cognitive_evidence_contradictions(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    blueprint = _blueprint(db, mission_id)
    diagnostics = service.evidence_diagnostics(mission_id=mission_id, blueprint=blueprint)
    return {
        "mission_id": mission_id,
        "contradictions": diagnostics.contradictions,
    }


@router.get("/{mission_id}/cognitive/progress")
def get_cognitive_progress(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    mission = _require_runtime(service, mission_id)
    blueprint_repository = SqlAlchemyMissionBlueprintRepository(db)
    blueprint = blueprint_repository.get(mission_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint for mission {mission_id!r} not found")
    readiness = blueprint_repository.latest_readiness_snapshot(mission_id)
    snapshot = service.compute_progress_snapshot(
        mission_id=mission_id,
        blueprint=blueprint,
        readiness=readiness,
        ledger_summary={"source": "cognitive_runtime_v2_api", "execution_impact": "none"},
    )
    return snapshot.to_dict()


@router.get("/{mission_id}/cognitive/metrics")
def get_cognitive_metrics(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return service.retrieve_metrics(mission_id).to_dict()


def _service_or_disabled(db: Session) -> CognitiveRuntimeService:
    if not is_shadow_or_active("COGNITIVE_RUNTIME_V2"):
        raise HTTPException(status_code=404, detail="COGNITIVE_RUNTIME_V2 is disabled")
    return CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db))


def _require_runtime(service: CognitiveRuntimeService, mission_id: str):
    mission = service.load_runtime(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Cognitive Runtime for mission {mission_id!r} not found")
    return mission


def _blueprint(db: Session, mission_id: str):
    return SqlAlchemyMissionBlueprintRepository(db).get(mission_id)
