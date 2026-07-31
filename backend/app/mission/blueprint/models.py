from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.feature_flags import is_shadow_or_active


SCHEMA_VERSION = "mission_blueprint.v1"
RUNTIME_EXECUTION_STATES = {
    "QUEUED",
    "DISPATCHED",
    "EXECUTING",
    "WAITING_BROWSER",
    "WAITING_PROVIDER",
    "WAITING_USER",
    "WAITING_EXTERNAL",
    "COMPLETED",
    "FAILED",
    "BLOCKED",
}


class BlueprintValidationError(ValueError):
    """Raised when an in-memory Mission Blueprint violates its contract."""


class BlueprintNodeKind(str, Enum):
    OBJECTIVE = "objective"
    DISCOVERY = "discovery"
    COLLECTION = "collection"
    SELECTION = "selection"
    ACQUISITION = "acquisition"
    READING = "reading"
    EXTRACTION = "extraction"
    VALIDATION = "validation"
    SYNTHESIS = "synthesis"
    REPORTING = "reporting"
    CLARIFICATION = "clarification"
    APPROVAL = "approval"
    EXTERNAL_WAIT = "external_wait"
    GENERAL = "general"
    SEARCH_ENGINE_ENTRY = "search_engine_entry"
    SEARCH_QUERY = "search_query"
    SERP_COLLECTION = "serp_collection"
    RESULT_SELECTION = "result_selection"
    OPEN_RESULT = "open_result"
    PAGE_READ = "page_read"
    FIELD_EXTRACTION = "field_extraction"
    USER_CLARIFICATION = "user_clarification"
    WAIT = "wait"


class BlueprintNodeState(str, Enum):
    PROPOSED = "proposed"
    READY = "ready"
    WAITING_EVIDENCE = "waiting_evidence"
    NEEDS_CLARIFICATION = "needs_clarification"
    NEEDS_REPLAN = "needs_replan"
    SATISFIED = "satisfied"
    CANCELLED = "cancelled"


class BlueprintDependencyKind(str, Enum):
    PREREQUISITE = "prerequisite"
    EVIDENCE = "evidence"
    CLARIFICATION = "clarification"
    APPROVAL = "approval"
    OPTIONAL = "optional"
    PARALLEL_GROUP = "parallel_group"


@dataclass(frozen=True)
class BlueprintEvidenceRequirement:
    requirement_id: str
    evidence_kind: str
    subject: str
    required: bool = True
    cardinality: int = 1
    confidence_threshold: float = 0.0
    freshness_seconds: int | None = None
    validation_policy: str = "raw"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BlueprintExpansionRule:
    rule_id: str
    capability: str
    intent_template: str
    requires_evidence: list[str] = field(default_factory=list)
    max_intents: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClarificationRequirement:
    clarification_id: str
    question: str
    required: bool = True
    blocks_node_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BlueprintDependency:
    dependency_id: str
    from_node_id: str
    to_node_id: str
    kind: BlueprintDependencyKind = BlueprintDependencyKind.PREREQUISITE
    required: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BlueprintNode:
    node_id: str
    objective: str
    kind: BlueprintNodeKind = BlueprintNodeKind.GENERAL
    execution_type: str = "passive"
    required_capability: str = "General"
    expected_evidence: list[str] = field(default_factory=lambda: ["blueprint_node_satisfied"])
    expansion_template: dict[str, Any] = field(default_factory=lambda: {"provider": "mission_blueprint", "action": "record_node_ready", "passive": True})
    repeat_policy: dict[str, Any] = field(default_factory=lambda: {"mode": "single", "max_repeats": 1})
    parallel_policy: dict[str, Any] = field(default_factory=lambda: {"mode": "sequential", "parallelizable": False})
    state: BlueprintNodeState = BlueprintNodeState.PROPOSED
    priority: int = 3
    owner_capabilities: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=lambda: ["blueprint_node_satisfied"])
    evidence_requirements: list[BlueprintEvidenceRequirement] = field(default_factory=list)
    expansion_rules: list[BlueprintExpansionRule] = field(default_factory=list)
    clarification_requirements: list[ClarificationRequirement] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MissionBlueprint:
    blueprint_id: str
    mission_id: str
    objective: str
    nodes: list[BlueprintNode]
    dependencies: list[BlueprintDependency] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    revision: int = 1
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    recovery_rules: list[str] = field(default_factory=list)
    termination_rules: list[str] = field(default_factory=list)
    approval_policy: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MissionBlueprint:
        blueprint = cls(
            blueprint_id=str(payload.get("blueprint_id") or ""),
            mission_id=str(payload.get("mission_id") or ""),
            objective=str(payload.get("objective") or ""),
            nodes=[_node_from_dict(item) for item in list(payload.get("nodes") or [])],
            dependencies=[_dependency_from_dict(item) for item in list(payload.get("dependencies") or [])],
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
            revision=int(payload.get("revision") or 1),
            constraints=list(payload.get("constraints") or []),
            success_criteria=list(payload.get("success_criteria") or []),
            recovery_rules=list(payload.get("recovery_rules") or []),
            termination_rules=list(payload.get("termination_rules") or []),
            approval_policy=dict(payload.get("approval_policy") or {}),
            metadata=dict(payload.get("metadata") or {}),
            created_at=_datetime_from_value(payload.get("created_at")),
            updated_at=_datetime_from_value(payload.get("updated_at")),
        )
        validate_blueprint(blueprint)
        return blueprint


def create_blueprint(
    *,
    mission_id: str,
    objective: str,
    nodes: list[BlueprintNode],
    dependencies: list[BlueprintDependency] | None = None,
    constraints: list[str] | None = None,
    success_criteria: list[str] | None = None,
    recovery_rules: list[str] | None = None,
    termination_rules: list[str] | None = None,
    approval_policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> MissionBlueprint:
    """Create and validate an in-memory Blueprint when the feature flag is enabled."""
    _require_enabled()
    blueprint = MissionBlueprint(
        blueprint_id=f"blueprint_{uuid.uuid4().hex}",
        mission_id=mission_id,
        objective=objective,
        nodes=list(nodes),
        dependencies=list(dependencies or []),
        constraints=list(constraints or []),
        success_criteria=list(success_criteria or []),
        recovery_rules=list(recovery_rules or []),
        termination_rules=list(termination_rules or []),
        approval_policy=dict(approval_policy or {}),
        metadata=dict(metadata or {}),
    )
    validate_blueprint(blueprint)
    return blueprint


def serialize_blueprint(blueprint: MissionBlueprint) -> dict[str, Any]:
    _require_enabled()
    validate_blueprint(blueprint)
    return blueprint.to_dict()


def deserialize_blueprint(payload: dict[str, Any]) -> MissionBlueprint:
    _require_enabled()
    return MissionBlueprint.from_dict(payload)


def validate_blueprint(blueprint: MissionBlueprint) -> None:
    if blueprint.schema_version != SCHEMA_VERSION:
        raise BlueprintValidationError(f"Unsupported blueprint schema version: {blueprint.schema_version}")
    if not blueprint.mission_id.strip():
        raise BlueprintValidationError("mission_id is required")
    if not blueprint.blueprint_id.strip():
        raise BlueprintValidationError("blueprint_id is required")
    if not blueprint.objective.strip():
        raise BlueprintValidationError("objective is required")
    if blueprint.revision < 1:
        raise BlueprintValidationError("revision must be >= 1")
    if not blueprint.nodes:
        raise BlueprintValidationError("at least one blueprint node is required")

    node_ids = [node.node_id for node in blueprint.nodes]
    if len(set(node_ids)) != len(node_ids):
        raise BlueprintValidationError("blueprint node ids must be unique")
    known_nodes = set(node_ids)

    for node in blueprint.nodes:
        _validate_node(node)

    dependency_ids: set[str] = set()
    graph: dict[str, list[str]] = {node_id: [] for node_id in known_nodes}
    for dependency in blueprint.dependencies:
        if dependency.dependency_id in dependency_ids:
            raise BlueprintValidationError("dependency ids must be unique")
        dependency_ids.add(dependency.dependency_id)
        if dependency.from_node_id not in known_nodes:
            raise BlueprintValidationError(f"dependency references unknown from_node_id: {dependency.from_node_id}")
        if dependency.to_node_id not in known_nodes:
            raise BlueprintValidationError(f"dependency references unknown to_node_id: {dependency.to_node_id}")
        if dependency.from_node_id == dependency.to_node_id:
            raise BlueprintValidationError("dependency cannot reference the same node")
        graph[dependency.from_node_id].append(dependency.to_node_id)

    _validate_acyclic(graph)


def _validate_node(node: BlueprintNode) -> None:
    if not node.node_id.strip():
        raise BlueprintValidationError("node_id is required")
    if not node.objective.strip():
        raise BlueprintValidationError(f"node {node.node_id} objective is required")
    if not node.execution_type.strip():
        raise BlueprintValidationError(f"node {node.node_id} execution_type is required")
    if not node.required_capability.strip():
        raise BlueprintValidationError(f"node {node.node_id} required_capability is required")
    if not node.expected_evidence:
        raise BlueprintValidationError(f"node {node.node_id} expected_evidence is required")
    if not node.success_criteria:
        raise BlueprintValidationError(f"node {node.node_id} success_criteria is required")
    if not node.expansion_template:
        raise BlueprintValidationError(f"node {node.node_id} expansion_template is required")
    provider = str(node.expansion_template.get("provider") or "").strip()
    action = str(node.expansion_template.get("action") or "").strip()
    if not provider or not action:
        raise BlueprintValidationError(f"node {node.node_id} expansion_template provider and action are required")
    if not node.repeat_policy:
        raise BlueprintValidationError(f"node {node.node_id} repeat_policy is required")
    if not node.parallel_policy:
        raise BlueprintValidationError(f"node {node.node_id} parallel_policy is required")
    if node.state.value.upper() in RUNTIME_EXECUTION_STATES:
        raise BlueprintValidationError("blueprint nodes cannot use runtime execution states")
    if node.priority < 1 or node.priority > 5:
        raise BlueprintValidationError(f"node {node.node_id} priority must be between 1 and 5")
    for requirement in node.evidence_requirements:
        if requirement.cardinality < 1:
            raise BlueprintValidationError(f"requirement {requirement.requirement_id} cardinality must be >= 1")
        if requirement.confidence_threshold < 0.0 or requirement.confidence_threshold > 1.0:
            raise BlueprintValidationError(f"requirement {requirement.requirement_id} confidence_threshold must be 0..1")
    for rule in node.expansion_rules:
        if not rule.capability.strip():
            raise BlueprintValidationError(f"expansion rule {rule.rule_id} capability is required")
        if not rule.intent_template.strip():
            raise BlueprintValidationError(f"expansion rule {rule.rule_id} intent_template is required")
        if rule.max_intents is not None and rule.max_intents < 1:
            raise BlueprintValidationError(f"expansion rule {rule.rule_id} max_intents must be >= 1")


def _validate_acyclic(graph: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise BlueprintValidationError("blueprint dependencies must be acyclic")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in graph.get(node_id, []):
            visit(child)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in graph:
        visit(node_id)


def _node_from_dict(payload: dict[str, Any]) -> BlueprintNode:
    return BlueprintNode(
        node_id=str(payload.get("node_id") or ""),
        objective=str(payload.get("objective") or ""),
        kind=BlueprintNodeKind(str(payload.get("kind") or BlueprintNodeKind.GENERAL.value)),
        execution_type=str(payload.get("execution_type") or "passive"),
        required_capability=str(payload.get("required_capability") or "General"),
        expected_evidence=list(payload.get("expected_evidence") or ["blueprint_node_satisfied"]),
        expansion_template=dict(payload.get("expansion_template") or {"provider": "mission_blueprint", "action": "record_node_ready", "passive": True}),
        repeat_policy=dict(payload.get("repeat_policy") or {"mode": "single", "max_repeats": 1}),
        parallel_policy=dict(payload.get("parallel_policy") or {"mode": "sequential", "parallelizable": False}),
        state=BlueprintNodeState(str(payload.get("state") or BlueprintNodeState.PROPOSED.value)),
        priority=int(payload.get("priority") or 3),
        owner_capabilities=list(payload.get("owner_capabilities") or []),
        success_criteria=list(payload.get("success_criteria") or ["blueprint_node_satisfied"]),
        evidence_requirements=[
            BlueprintEvidenceRequirement(**item)
            for item in list(payload.get("evidence_requirements") or [])
        ],
        expansion_rules=[
            BlueprintExpansionRule(**item)
            for item in list(payload.get("expansion_rules") or [])
        ],
        clarification_requirements=[
            ClarificationRequirement(**item)
            for item in list(payload.get("clarification_requirements") or [])
        ],
        metadata=dict(payload.get("metadata") or {}),
    )


def _dependency_from_dict(payload: dict[str, Any]) -> BlueprintDependency:
    return BlueprintDependency(
        dependency_id=str(payload.get("dependency_id") or ""),
        from_node_id=str(payload.get("from_node_id") or ""),
        to_node_id=str(payload.get("to_node_id") or ""),
        kind=BlueprintDependencyKind(str(payload.get("kind") or BlueprintDependencyKind.PREREQUISITE.value)),
        required=bool(payload.get("required", True)),
        metadata=dict(payload.get("metadata") or {}),
    )


def _datetime_from_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return datetime.now(UTC)


def _require_enabled() -> None:
    if not is_shadow_or_active("MISSION_BLUEPRINT_V1"):
        raise BlueprintValidationError("MISSION_BLUEPRINT_V1 is disabled")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
