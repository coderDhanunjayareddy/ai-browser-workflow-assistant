from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.cognitive_runtime.repository import SqlAlchemyCognitiveRuntimeRepository
from app.cognitive_runtime.service import CognitiveRuntimeService
from app.cognitive_runtime.policy import DecisionPolicy
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


@router.get("/{mission_id}/cognitive/state")
def get_cognitive_state(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    blueprint = _blueprint(db, mission_id)
    readiness = SqlAlchemyMissionBlueprintRepository(db).latest_readiness_snapshot(mission_id)
    return service.cognitive_state(mission_id=mission_id, blueprint=blueprint, readiness=readiness).to_dict()


@router.get("/{mission_id}/cognitive/transitions")
def get_cognitive_transitions(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return service.transition_diagnostics(mission_id).to_dict()


@router.get("/{mission_id}/cognitive/waits")
def get_cognitive_waits(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return service.wait_diagnostics(mission_id).to_dict()


@router.get("/{mission_id}/cognitive/clarifications")
def get_cognitive_clarifications(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return service.clarification_diagnostics(mission_id=mission_id, blueprint=_blueprint(db, mission_id)).to_dict()


@router.get("/{mission_id}/cognitive/recovery")
def get_cognitive_recovery(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return service.recovery_diagnostics(mission_id).to_dict()


@router.get("/{mission_id}/cognitive/replanning")
def get_cognitive_replanning(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return service.replanning_diagnostics(mission_id=mission_id, blueprint=_blueprint(db, mission_id)).to_dict()


@router.get("/{mission_id}/cognitive/lifecycle")
def get_cognitive_lifecycle(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    return service.lifecycle_summary(mission_id).to_dict()


@router.get("/{mission_id}/cognitive/snapshot")
def get_cognitive_snapshot(mission_id: str, db: Session = Depends(get_db)) -> dict:
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    blueprint = _blueprint(db, mission_id)
    readiness = SqlAlchemyMissionBlueprintRepository(db).latest_readiness_snapshot(mission_id)
    return service.reasoning_snapshot(mission_id=mission_id, blueprint=blueprint, readiness=readiness).to_dict()


@router.get("/{mission_id}/cognitive/decision")
def get_cognitive_decision(mission_id: str, policy: str | None = None, db: Session = Depends(get_db)) -> dict:
    result = _decision_result(db, mission_id, policy)
    return result.decision.to_dict()


@router.get("/{mission_id}/cognitive/recommendations")
def get_cognitive_recommendations(mission_id: str, policy: str | None = None, db: Session = Depends(get_db)) -> dict:
    result = _decision_result(db, mission_id, policy)
    return {
        "mission_id": mission_id,
        "recommended": result.decision.to_dict(),
        "alternatives": result.decision.alternatives,
        "rejected_decisions": result.decision.rejected_decisions,
        "ranked_signals": result.ranked_signals,
    }


@router.get("/{mission_id}/cognitive/decision/confidence")
def get_cognitive_decision_confidence(mission_id: str, policy: str | None = None, db: Session = Depends(get_db)) -> dict:
    decision = _decision_result(db, mission_id, policy).decision
    return {
        "mission_id": mission_id,
        "decision_type": decision.decision_type.value,
        "confidence": decision.confidence,
        "confidence_breakdown": decision.metadata.get("confidence", {}),
    }


@router.get("/{mission_id}/cognitive/decision/explanation")
def get_cognitive_decision_explanation(mission_id: str, policy: str | None = None, db: Session = Depends(get_db)) -> dict:
    result = _decision_result(db, mission_id, policy)
    return {
        "mission_id": mission_id,
        "decision": result.decision.to_dict(),
        "explanation": result.explanation.to_dict(),
    }


@router.get("/{mission_id}/cognitive/decision/policy")
def get_cognitive_decision_policy(policy: str | None = None) -> dict:
    if not is_shadow_or_active("COGNITIVE_RUNTIME_V2"):
        raise HTTPException(status_code=404, detail="COGNITIVE_RUNTIME_V2 is disabled")
    return DecisionPolicy.from_name(policy).to_dict()


@router.get("/{mission_id}/cognitive/decision/alternatives")
def get_cognitive_decision_alternatives(mission_id: str, policy: str | None = None, db: Session = Depends(get_db)) -> dict:
    decision = _decision_result(db, mission_id, policy).decision
    return {
        "mission_id": mission_id,
        "alternatives": decision.alternatives,
        "rejected_decisions": decision.rejected_decisions,
    }


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


def _decision_result(db: Session, mission_id: str, policy: str | None = None):
    service = _service_or_disabled(db)
    _require_runtime(service, mission_id)
    blueprint_repository = SqlAlchemyMissionBlueprintRepository(db)
    return service.cognitive_decision(
        mission_id=mission_id,
        blueprint=blueprint_repository.get(mission_id),
        readiness=blueprint_repository.latest_readiness_snapshot(mission_id),
        policy_name=policy,
    )
