from __future__ import annotations

from typing import Any

from app.mission.blueprint.models import (
    BlueprintDependency,
    BlueprintNode,
    MissionBlueprint,
    create_blueprint,
    deserialize_blueprint,
    serialize_blueprint,
)
from app.mission.blueprint.repository import MissionBlueprintRepository


class MissionBlueprintPersistenceService:
    """Passive persistence service for Mission Blueprint artifacts.

    The service owns storage operations only. It does not decompose goals,
    generate intents, evaluate readiness, or affect Runtime V1 execution.
    """

    def __init__(self, repository: MissionBlueprintRepository):
        self.repository = repository

    def create(
        self,
        *,
        mission_id: str,
        objective: str,
        nodes: list[BlueprintNode],
        dependencies: list[BlueprintDependency] | None = None,
        reason: str = "initial",
        created_by: str = "mission_intelligence",
        **blueprint_fields: Any,
    ) -> MissionBlueprint:
        blueprint = create_blueprint(
            mission_id=mission_id,
            objective=objective,
            nodes=nodes,
            dependencies=dependencies,
            constraints=blueprint_fields.get("constraints"),
            success_criteria=blueprint_fields.get("success_criteria"),
            recovery_rules=blueprint_fields.get("recovery_rules"),
            termination_rules=blueprint_fields.get("termination_rules"),
            approval_policy=blueprint_fields.get("approval_policy"),
            metadata=blueprint_fields.get("metadata"),
        )
        return self.repository.create(blueprint, reason=reason, created_by=created_by)

    def load(self, mission_id: str) -> MissionBlueprint | None:
        return self.repository.get(mission_id)

    def save(self, blueprint: MissionBlueprint, *, reason: str = "update", created_by: str = "mission_intelligence") -> MissionBlueprint:
        return self.repository.update(blueprint, reason=reason, created_by=created_by)

    def save_revision(self, blueprint: MissionBlueprint, *, reason: str, created_by: str = "mission_intelligence") -> str:
        return self.repository.save_revision(blueprint, reason=reason, created_by=created_by)

    def get_revision(self, mission_id: str, revision: int) -> MissionBlueprint | None:
        return self.repository.get_revision(mission_id, revision)

    def list_revisions(self, mission_id: str) -> list[dict[str, Any]]:
        return self.repository.list_revisions(mission_id)

    def list_nodes(self, mission_id: str, *, revision: int | None = None) -> list[BlueprintNode]:
        return self.repository.list_nodes(mission_id, revision=revision)

    def serialize(self, blueprint: MissionBlueprint) -> dict[str, Any]:
        return serialize_blueprint(blueprint)

    def deserialize(self, payload: dict[str, Any]) -> MissionBlueprint:
        return deserialize_blueprint(payload)
