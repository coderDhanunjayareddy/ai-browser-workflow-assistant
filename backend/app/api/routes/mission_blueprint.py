from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.feature_flags import is_shadow_or_active
from app.mission.blueprint.models import BlueprintValidationError, MissionBlueprint
from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository
from app.mission.blueprint.service import MissionBlueprintPersistenceService
from app.schemas.mission_blueprint import (
    BlueprintExpansionSummarySchema,
    BlueprintExpansionsResponse,
    BlueprintReadinessSnapshotSchema,
    BlueprintReadinessSnapshotsResponse,
    MissionBlueprintNodeSchema,
    MissionBlueprintNodesResponse,
    MissionBlueprintRevisionSummary,
    MissionBlueprintRevisionsResponse,
    MissionBlueprintSchema,
)


router = APIRouter(tags=["mission-blueprint"])


@router.get("/{mission_id}/blueprint", response_model=MissionBlueprintSchema)
def get_blueprint(mission_id: str, db: Session = Depends(get_db)) -> MissionBlueprintSchema:
    service = _service_or_disabled(db)
    blueprint = service.load(mission_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint for mission {mission_id!r} not found")
    return _blueprint_schema(blueprint)


@router.get("/{mission_id}/blueprint/nodes", response_model=MissionBlueprintNodesResponse)
def get_blueprint_nodes(mission_id: str, revision: int | None = None, db: Session = Depends(get_db)) -> MissionBlueprintNodesResponse:
    service = _service_or_disabled(db)
    nodes = service.list_nodes(mission_id, revision=revision)
    if not nodes and service.load(mission_id) is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint for mission {mission_id!r} not found")
    return MissionBlueprintNodesResponse(
        mission_id=mission_id,
        revision=revision,
        nodes=[_node_schema(node) for node in nodes],
    )


@router.get("/{mission_id}/blueprint/revisions", response_model=MissionBlueprintRevisionsResponse)
def get_blueprint_revisions(mission_id: str, db: Session = Depends(get_db)) -> MissionBlueprintRevisionsResponse:
    service = _service_or_disabled(db)
    revisions = service.list_revisions(mission_id)
    if not revisions and service.load(mission_id) is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint for mission {mission_id!r} not found")
    return MissionBlueprintRevisionsResponse(
        mission_id=mission_id,
        revisions=[MissionBlueprintRevisionSummary(**revision) for revision in revisions],
    )


@router.get("/{mission_id}/blueprint/revision/{revision}", response_model=MissionBlueprintSchema)
def get_blueprint_revision(mission_id: str, revision: int, db: Session = Depends(get_db)) -> MissionBlueprintSchema:
    service = _service_or_disabled(db)
    blueprint = service.get_revision(mission_id, revision)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint revision {revision} for mission {mission_id!r} not found")
    return _blueprint_schema(blueprint)


@router.get("/{mission_id}/blueprint/readiness", response_model=BlueprintReadinessSnapshotSchema)
def get_blueprint_readiness(mission_id: str, db: Session = Depends(get_db)) -> BlueprintReadinessSnapshotSchema:
    service = _service_or_disabled(db)
    snapshot = service.latest_readiness_snapshot(mission_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint readiness for mission {mission_id!r} not found")
    return BlueprintReadinessSnapshotSchema(**snapshot.to_dict())


@router.get("/{mission_id}/blueprint/readiness/snapshots", response_model=BlueprintReadinessSnapshotsResponse)
def get_blueprint_readiness_snapshots(mission_id: str, db: Session = Depends(get_db)) -> BlueprintReadinessSnapshotsResponse:
    service = _service_or_disabled(db)
    snapshots = service.list_readiness_snapshots(mission_id)
    if not snapshots and service.load(mission_id) is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint for mission {mission_id!r} not found")
    return BlueprintReadinessSnapshotsResponse(
        mission_id=mission_id,
        snapshots=[BlueprintReadinessSnapshotSchema(**snapshot.to_dict()) for snapshot in snapshots],
    )


@router.get("/{mission_id}/blueprint/expansions", response_model=BlueprintExpansionsResponse)
def get_blueprint_expansions(mission_id: str, db: Session = Depends(get_db)) -> BlueprintExpansionsResponse:
    service = _service_or_disabled(db)
    expansions = service.list_expansions(mission_id)
    if not expansions and service.load(mission_id) is None:
        raise HTTPException(status_code=404, detail=f"Mission Blueprint for mission {mission_id!r} not found")
    expanded_nodes = [str(item.get("blueprint_node_id")) for item in expansions]
    generated_intent_ids = [
        str(intent_id)
        for item in expansions
        for intent_id in list(item.get("generated_intent_ids") or [])
    ]
    blueprint = service.load(mission_id)
    pending_nodes = [
        node.node_id
        for node in list(blueprint.nodes if blueprint else [])
        if node.node_id not in set(expanded_nodes)
    ]
    return BlueprintExpansionsResponse(
        mission_id=mission_id,
        expanded_nodes=expanded_nodes,
        pending_nodes=pending_nodes,
        generated_intent_ids=generated_intent_ids,
        expansions=[BlueprintExpansionSummarySchema(**item) for item in expansions],
    )


def _service_or_disabled(db: Session) -> MissionBlueprintPersistenceService:
    if not is_shadow_or_active("MISSION_BLUEPRINT_V1"):
        raise HTTPException(status_code=404, detail="MISSION_BLUEPRINT_V1 is disabled")
    return MissionBlueprintPersistenceService(SqlAlchemyMissionBlueprintRepository(db))


def _blueprint_schema(blueprint: MissionBlueprint) -> MissionBlueprintSchema:
    payload = blueprint.to_dict()
    metadata = dict(blueprint.metadata or {})
    return MissionBlueprintSchema(
        **{
            **payload,
            "mission_analysis": dict(metadata.get("mission_analysis") or {}),
            "capability_requirements": dict(metadata.get("capability_requirements") or {}),
            "risk_summary": dict(metadata.get("risk_summary") or {}),
            "clarification_requirements": list(metadata.get("clarification_requirements") or []),
            "dependency_graph": dict(metadata.get("dependency_analysis") or {}),
            "nodes": [_node_schema(node) for node in blueprint.nodes],
            "dependencies": [
                {
                    "dependency_id": dependency.dependency_id,
                    "from_node_id": dependency.from_node_id,
                    "to_node_id": dependency.to_node_id,
                    "kind": dependency.kind.value,
                    "required": dependency.required,
                    "metadata": dependency.metadata,
                }
                for dependency in blueprint.dependencies
            ],
        }
    )


def _node_schema(node) -> MissionBlueprintNodeSchema:
    return MissionBlueprintNodeSchema(
        node_id=node.node_id,
        objective=node.objective,
        kind=node.kind.value,
        state=node.state.value,
        priority=node.priority,
        owner_capabilities=list(node.owner_capabilities),
        success_criteria=list(node.success_criteria),
        evidence_requirements=[requirement.__dict__ for requirement in node.evidence_requirements],
        expansion_rules=[rule.__dict__ for rule in node.expansion_rules],
        clarification_requirements=[requirement.__dict__ for requirement in node.clarification_requirements],
        metadata=dict(node.metadata),
    )
