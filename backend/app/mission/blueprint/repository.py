from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.feature_flags import is_shadow_or_active
from app.mission.blueprint.models import (
    BlueprintDependency,
    BlueprintDependencyKind,
    BlueprintNode,
    BlueprintNodeKind,
    BlueprintNodeState,
    BlueprintValidationError,
    MissionBlueprint,
    validate_blueprint,
)
from app.mission.blueprint.readiness import BlueprintReadinessSnapshot
from app.models.db import (
    MissionBlueprintDependencyRecord,
    MissionBlueprintExpansionRecord,
    MissionBlueprintNodeRecord,
    MissionBlueprintRecord,
    MissionBlueprintReadinessSnapshotRecord,
    MissionBlueprintRevisionRecord,
)


class MissionBlueprintRepository(ABC):
    """Persistence abstraction for passive Mission Blueprint artifacts."""

    @abstractmethod
    def create(self, blueprint: MissionBlueprint, *, reason: str = "initial", created_by: str = "mission_intelligence") -> MissionBlueprint:
        raise NotImplementedError

    @abstractmethod
    def get(self, mission_id: str) -> MissionBlueprint | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, blueprint: MissionBlueprint, *, reason: str = "update", created_by: str = "mission_intelligence") -> MissionBlueprint:
        raise NotImplementedError

    @abstractmethod
    def save_revision(self, blueprint: MissionBlueprint, *, reason: str, created_by: str = "mission_intelligence") -> str:
        raise NotImplementedError

    @abstractmethod
    def get_revision(self, mission_id: str, revision: int) -> MissionBlueprint | None:
        raise NotImplementedError

    @abstractmethod
    def list_revisions(self, mission_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_nodes(self, mission_id: str, *, revision: int | None = None) -> list[BlueprintNode]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, mission_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def save_readiness_snapshot(self, snapshot: BlueprintReadinessSnapshot) -> BlueprintReadinessSnapshot:
        raise NotImplementedError

    @abstractmethod
    def latest_readiness_snapshot(self, mission_id: str) -> BlueprintReadinessSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    def list_readiness_snapshots(self, mission_id: str) -> list[BlueprintReadinessSnapshot]:
        raise NotImplementedError

    @abstractmethod
    def record_expansion(
        self,
        *,
        mission_id: str,
        blueprint_id: str,
        blueprint_node_id: str,
        blueprint_revision: int,
        generated_intent_ids: list[str],
        diagnostics: dict[str, Any],
        status: str = "expanded",
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_expansions(self, mission_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def expansion_for_node(self, mission_id: str, blueprint_node_id: str, blueprint_revision: int) -> dict[str, Any] | None:
        raise NotImplementedError


class SqlAlchemyMissionBlueprintRepository(MissionBlueprintRepository):
    """SQLAlchemy-backed repository. Mission Intelligence should depend on the interface."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, blueprint: MissionBlueprint, *, reason: str = "initial", created_by: str = "mission_intelligence") -> MissionBlueprint:
        _require_persistence_enabled()
        validate_blueprint(blueprint)
        if self.db.get(MissionBlueprintRecord, blueprint.blueprint_id) is not None:
            raise BlueprintValidationError(f"Blueprint already exists: {blueprint.blueprint_id}")
        existing = self._record_for_mission(blueprint.mission_id)
        if existing is not None:
            raise BlueprintValidationError(f"Mission already has a blueprint: {blueprint.mission_id}")
        record = _record_from_blueprint(blueprint)
        self.db.add(record)
        self.db.flush()
        self.save_revision(blueprint, reason=reason, created_by=created_by)
        self.db.commit()
        return blueprint

    def get(self, mission_id: str) -> MissionBlueprint | None:
        _require_persistence_enabled()
        record = self._record_for_mission(mission_id)
        if record is None:
            return None
        return MissionBlueprint.from_dict(dict(record.snapshot or {}))

    def update(self, blueprint: MissionBlueprint, *, reason: str = "update", created_by: str = "mission_intelligence") -> MissionBlueprint:
        _require_persistence_enabled()
        validate_blueprint(blueprint)
        record = self.db.get(MissionBlueprintRecord, blueprint.blueprint_id)
        if record is None:
            raise LookupError(f"Blueprint not found: {blueprint.blueprint_id}")
        record.objective = blueprint.objective
        record.revision = blueprint.revision
        record.schema_version = blueprint.schema_version
        record.constraints = list(blueprint.constraints)
        record.success_criteria = list(blueprint.success_criteria)
        record.recovery_rules = list(blueprint.recovery_rules)
        record.termination_rules = list(blueprint.termination_rules)
        record.approval_policy = dict(blueprint.approval_policy)
        record.blueprint_metadata = dict(blueprint.metadata)
        record.snapshot = blueprint.to_dict()
        record.updated_at = datetime.now(UTC)
        self.save_revision(blueprint, reason=reason, created_by=created_by)
        self.db.commit()
        return blueprint

    def save_revision(self, blueprint: MissionBlueprint, *, reason: str, created_by: str = "mission_intelligence") -> str:
        _require_persistence_enabled()
        validate_blueprint(blueprint)
        revision_id = f"blueprint_revision_{uuid.uuid4().hex}"
        revision = MissionBlueprintRevisionRecord(
            revision_id=revision_id,
            blueprint_id=blueprint.blueprint_id,
            mission_id=blueprint.mission_id,
            revision=blueprint.revision,
            reason=reason,
            created_by=created_by,
            snapshot=blueprint.to_dict(),
            created_at=datetime.now(UTC),
        )
        self.db.add(revision)
        self.db.flush()
        for node in blueprint.nodes:
            self.db.add(_node_record(blueprint, revision_id, node))
        for dependency in blueprint.dependencies:
            self.db.add(_dependency_record(blueprint, revision_id, dependency))
        self.db.commit()
        return revision_id

    def get_revision(self, mission_id: str, revision: int) -> MissionBlueprint | None:
        _require_persistence_enabled()
        record = (
            self.db.query(MissionBlueprintRevisionRecord)
            .filter(MissionBlueprintRevisionRecord.mission_id == mission_id)
            .filter(MissionBlueprintRevisionRecord.revision == revision)
            .order_by(MissionBlueprintRevisionRecord.created_at.desc())
            .first()
        )
        if record is None:
            return None
        return MissionBlueprint.from_dict(dict(record.snapshot or {}))

    def list_revisions(self, mission_id: str) -> list[dict[str, Any]]:
        _require_persistence_enabled()
        records = (
            self.db.query(MissionBlueprintRevisionRecord)
            .filter(MissionBlueprintRevisionRecord.mission_id == mission_id)
            .order_by(MissionBlueprintRevisionRecord.revision.asc(), MissionBlueprintRevisionRecord.created_at.asc())
            .all()
        )
        return [
            {
                "revision_id": record.revision_id,
                "blueprint_id": record.blueprint_id,
                "mission_id": record.mission_id,
                "revision": record.revision,
                "reason": record.reason,
                "created_by": record.created_by,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            }
            for record in records
        ]

    def list_nodes(self, mission_id: str, *, revision: int | None = None) -> list[BlueprintNode]:
        _require_persistence_enabled()
        if revision is None:
            blueprint = self.get(mission_id)
        else:
            blueprint = self.get_revision(mission_id, revision)
        return list(blueprint.nodes) if blueprint is not None else []

    def delete(self, mission_id: str) -> bool:
        _require_persistence_enabled()
        record = self._record_for_mission(mission_id)
        if record is None:
            return False
        self.db.delete(record)
        self.db.commit()
        return True

    def save_readiness_snapshot(self, snapshot: BlueprintReadinessSnapshot) -> BlueprintReadinessSnapshot:
        _require_persistence_enabled()
        self.db.add(
            MissionBlueprintReadinessSnapshotRecord(
                snapshot_id=snapshot.snapshot_id,
                blueprint_id=snapshot.blueprint_id,
                mission_id=snapshot.mission_id,
                revision=snapshot.revision,
                snapshot=snapshot.to_dict(),
                created_at=snapshot.created_at,
            )
        )
        self.db.commit()
        return snapshot

    def latest_readiness_snapshot(self, mission_id: str) -> BlueprintReadinessSnapshot | None:
        _require_persistence_enabled()
        record = (
            self.db.query(MissionBlueprintReadinessSnapshotRecord)
            .filter(MissionBlueprintReadinessSnapshotRecord.mission_id == mission_id)
            .order_by(MissionBlueprintReadinessSnapshotRecord.created_at.desc())
            .first()
        )
        if record is None:
            return None
        return BlueprintReadinessSnapshot.from_dict(dict(record.snapshot or {}))

    def list_readiness_snapshots(self, mission_id: str) -> list[BlueprintReadinessSnapshot]:
        _require_persistence_enabled()
        records = (
            self.db.query(MissionBlueprintReadinessSnapshotRecord)
            .filter(MissionBlueprintReadinessSnapshotRecord.mission_id == mission_id)
            .order_by(MissionBlueprintReadinessSnapshotRecord.created_at.asc())
            .all()
        )
        return [BlueprintReadinessSnapshot.from_dict(dict(record.snapshot or {})) for record in records]

    def record_expansion(
        self,
        *,
        mission_id: str,
        blueprint_id: str,
        blueprint_node_id: str,
        blueprint_revision: int,
        generated_intent_ids: list[str],
        diagnostics: dict[str, Any],
        status: str = "expanded",
    ) -> dict[str, Any]:
        _require_persistence_enabled()
        existing = self.expansion_for_node(mission_id, blueprint_node_id, blueprint_revision)
        if existing is not None:
            return existing
        record = MissionBlueprintExpansionRecord(
            expansion_id=f"blueprint_expansion_{uuid.uuid4().hex}",
            blueprint_id=blueprint_id,
            mission_id=mission_id,
            blueprint_node_id=blueprint_node_id,
            blueprint_revision=blueprint_revision,
            status=status,
            generated_intent_ids=list(generated_intent_ids),
            diagnostics=dict(diagnostics),
            created_at=datetime.now(UTC),
        )
        self.db.add(record)
        self.db.commit()
        return _expansion_dict(record)

    def list_expansions(self, mission_id: str) -> list[dict[str, Any]]:
        _require_persistence_enabled()
        records = (
            self.db.query(MissionBlueprintExpansionRecord)
            .filter(MissionBlueprintExpansionRecord.mission_id == mission_id)
            .order_by(MissionBlueprintExpansionRecord.created_at.asc())
            .all()
        )
        return [_expansion_dict(record) for record in records]

    def expansion_for_node(self, mission_id: str, blueprint_node_id: str, blueprint_revision: int) -> dict[str, Any] | None:
        _require_persistence_enabled()
        record = (
            self.db.query(MissionBlueprintExpansionRecord)
            .filter(MissionBlueprintExpansionRecord.mission_id == mission_id)
            .filter(MissionBlueprintExpansionRecord.blueprint_node_id == blueprint_node_id)
            .filter(MissionBlueprintExpansionRecord.blueprint_revision == blueprint_revision)
            .order_by(MissionBlueprintExpansionRecord.created_at.desc())
            .first()
        )
        return _expansion_dict(record) if record is not None else None

    def _record_for_mission(self, mission_id: str) -> MissionBlueprintRecord | None:
        return (
            self.db.query(MissionBlueprintRecord)
            .filter(MissionBlueprintRecord.mission_id == mission_id)
            .order_by(MissionBlueprintRecord.updated_at.desc())
            .first()
        )


def _require_persistence_enabled() -> None:
    if not is_shadow_or_active("MISSION_BLUEPRINT_V1"):
        raise BlueprintValidationError("MISSION_BLUEPRINT_V1 is disabled")


def _record_from_blueprint(blueprint: MissionBlueprint) -> MissionBlueprintRecord:
    return MissionBlueprintRecord(
        blueprint_id=blueprint.blueprint_id,
        mission_id=blueprint.mission_id,
        schema_version=blueprint.schema_version,
        objective=blueprint.objective,
        revision=blueprint.revision,
        status="active",
        constraints=list(blueprint.constraints),
        success_criteria=list(blueprint.success_criteria),
        recovery_rules=list(blueprint.recovery_rules),
        termination_rules=list(blueprint.termination_rules),
        approval_policy=dict(blueprint.approval_policy),
        blueprint_metadata=dict(blueprint.metadata),
        snapshot=blueprint.to_dict(),
        created_at=blueprint.created_at,
        updated_at=blueprint.updated_at,
    )


def _node_record(blueprint: MissionBlueprint, revision_id: str, node: BlueprintNode) -> MissionBlueprintNodeRecord:
    return MissionBlueprintNodeRecord(
        node_record_id=f"blueprint_node_{uuid.uuid4().hex}",
        blueprint_id=blueprint.blueprint_id,
        revision_id=revision_id,
        mission_id=blueprint.mission_id,
        node_id=node.node_id,
        kind=node.kind.value if isinstance(node.kind, BlueprintNodeKind) else str(node.kind),
        state=node.state.value if isinstance(node.state, BlueprintNodeState) else str(node.state),
        objective=node.objective,
        priority=node.priority,
        owner_capabilities=list(node.owner_capabilities),
        success_criteria=list(node.success_criteria),
        evidence_requirements=[requirement.__dict__ for requirement in node.evidence_requirements],
        expansion_rules=[rule.__dict__ for rule in node.expansion_rules],
        clarification_requirements=[requirement.__dict__ for requirement in node.clarification_requirements],
        node_metadata=dict(node.metadata),
        created_at=datetime.now(UTC),
    )


def _dependency_record(
    blueprint: MissionBlueprint,
    revision_id: str,
    dependency: BlueprintDependency,
) -> MissionBlueprintDependencyRecord:
    return MissionBlueprintDependencyRecord(
        dependency_record_id=f"blueprint_dependency_{uuid.uuid4().hex}",
        blueprint_id=blueprint.blueprint_id,
        revision_id=revision_id,
        mission_id=blueprint.mission_id,
        dependency_id=dependency.dependency_id,
        from_node_id=dependency.from_node_id,
        to_node_id=dependency.to_node_id,
        kind=dependency.kind.value if isinstance(dependency.kind, BlueprintDependencyKind) else str(dependency.kind),
        required=dependency.required,
        dependency_metadata=dict(dependency.metadata),
        created_at=datetime.now(UTC),
    )


def _expansion_dict(record: MissionBlueprintExpansionRecord) -> dict[str, Any]:
    return {
        "expansion_id": record.expansion_id,
        "blueprint_id": record.blueprint_id,
        "mission_id": record.mission_id,
        "blueprint_node_id": record.blueprint_node_id,
        "blueprint_revision": record.blueprint_revision,
        "status": record.status,
        "generated_intent_ids": list(record.generated_intent_ids or []),
        "diagnostics": dict(record.diagnostics or {}),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
