from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from app.mission.blueprint.models import (
    BlueprintDependencyKind,
    BlueprintNode,
    ClarificationRequirement,
    MissionBlueprint,
)


class BlueprintNodeReadiness(str, Enum):
    READY = "ready"
    WAITING = "waiting"
    BLOCKED = "blocked"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class BlueprintEvidence:
    evidence_id: str
    evidence_kind: str
    subject: str
    confidence: float = 1.0
    validation_status: str = "raw"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlueprintNodeReadinessEvaluation:
    node_id: str
    readiness: BlueprintNodeReadiness
    expandable: bool
    dependency_reasons: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    critical_path: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["readiness"] = self.readiness.value
        return data


@dataclass(frozen=True)
class BlueprintReadinessSnapshot:
    schema_version: str
    snapshot_id: str
    blueprint_id: str
    mission_id: str
    revision: int
    ready_nodes: list[str]
    waiting_nodes: list[str]
    blocked_nodes: list[str]
    unreachable_nodes: list[str]
    parallel_ready_nodes: list[str]
    critical_path_ready_nodes: list[str]
    evaluations: list[BlueprintNodeReadinessEvaluation]
    evidence_count: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["evaluations"] = [evaluation.to_dict() for evaluation in self.evaluations]
        return data

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> BlueprintReadinessSnapshot:
        return cls(
            schema_version=str(payload.get("schema_version") or "mission_blueprint_readiness.v1"),
            snapshot_id=str(payload.get("snapshot_id") or ""),
            blueprint_id=str(payload.get("blueprint_id") or ""),
            mission_id=str(payload.get("mission_id") or ""),
            revision=int(payload.get("revision") or 1),
            ready_nodes=list(payload.get("ready_nodes") or []),
            waiting_nodes=list(payload.get("waiting_nodes") or []),
            blocked_nodes=list(payload.get("blocked_nodes") or []),
            unreachable_nodes=list(payload.get("unreachable_nodes") or []),
            parallel_ready_nodes=list(payload.get("parallel_ready_nodes") or []),
            critical_path_ready_nodes=list(payload.get("critical_path_ready_nodes") or []),
            evaluations=[
                BlueprintNodeReadinessEvaluation(
                    node_id=str(item.get("node_id") or ""),
                    readiness=BlueprintNodeReadiness(str(item.get("readiness") or BlueprintNodeReadiness.WAITING.value)),
                    expandable=bool(item.get("expandable")),
                    dependency_reasons=list(item.get("dependency_reasons") or []),
                    missing_evidence=list(item.get("missing_evidence") or []),
                    blocking_reasons=list(item.get("blocking_reasons") or []),
                    supporting_evidence=list(item.get("supporting_evidence") or []),
                    critical_path=bool(item.get("critical_path")),
                )
                for item in list(payload.get("evaluations") or [])
            ],
            evidence_count=int(payload.get("evidence_count") or 0),
            created_at=_datetime(payload.get("created_at")),
        )


class BlueprintReadinessEvaluator:
    """Evaluates which Blueprint nodes are eligible for later expansion."""

    def evaluate(
        self,
        blueprint: MissionBlueprint,
        evidence: list[BlueprintEvidence] | None = None,
    ) -> BlueprintReadinessSnapshot:
        evidence = list(evidence or [])
        incoming = _incoming_dependencies(blueprint)
        satisfied_nodes = _satisfied_nodes(evidence)
        evaluations = [
            self._evaluate_node(
                node,
                incoming=incoming.get(node.node_id, []),
                satisfied_nodes=satisfied_nodes,
                evidence=evidence,
            )
            for node in blueprint.nodes
        ]
        ready = [item.node_id for item in evaluations if item.readiness == BlueprintNodeReadiness.READY]
        waiting = [item.node_id for item in evaluations if item.readiness == BlueprintNodeReadiness.WAITING]
        blocked = [item.node_id for item in evaluations if item.readiness == BlueprintNodeReadiness.BLOCKED]
        unreachable = [item.node_id for item in evaluations if item.readiness == BlueprintNodeReadiness.UNREACHABLE]
        return BlueprintReadinessSnapshot(
            schema_version="mission_blueprint_readiness.v1",
            snapshot_id=f"readiness_{blueprint.blueprint_id}_{int(datetime.now(UTC).timestamp() * 1000)}",
            blueprint_id=blueprint.blueprint_id,
            mission_id=blueprint.mission_id,
            revision=blueprint.revision,
            ready_nodes=ready,
            waiting_nodes=waiting,
            blocked_nodes=blocked,
            unreachable_nodes=unreachable,
            parallel_ready_nodes=[
                item.node_id for item in evaluations
                if item.readiness == BlueprintNodeReadiness.READY and not item.critical_path
            ],
            critical_path_ready_nodes=[
                item.node_id for item in evaluations
                if item.readiness == BlueprintNodeReadiness.READY and item.critical_path
            ],
            evaluations=evaluations,
            evidence_count=len(evidence),
        )

    def _evaluate_node(
        self,
        node: BlueprintNode,
        *,
        incoming: list[Any],
        satisfied_nodes: set[str],
        evidence: list[BlueprintEvidence],
    ) -> BlueprintNodeReadinessEvaluation:
        dependency_reasons: list[str] = []
        missing_evidence: list[str] = []
        blocking_reasons: list[str] = []
        supporting_evidence: list[str] = []

        for dependency in incoming:
            if not dependency.required or dependency.kind == BlueprintDependencyKind.OPTIONAL:
                continue
            if dependency.kind == BlueprintDependencyKind.CLARIFICATION:
                if not _has_clarification_evidence(evidence, dependency.from_node_id, node.node_id):
                    blocking_reasons.append(f"Required clarification dependency is unsatisfied: {dependency.from_node_id}")
                continue
            if dependency.kind == BlueprintDependencyKind.EVIDENCE:
                matched = _matching_evidence(evidence, dependency.from_node_id, validation_optional=True)
                if matched:
                    supporting_evidence.extend(item.evidence_id for item in matched)
                else:
                    missing_evidence.append(f"evidence_dependency:{dependency.from_node_id}")
                continue
            if dependency.from_node_id not in satisfied_nodes:
                dependency_reasons.append(f"Required prerequisite not satisfied: {dependency.from_node_id}")

        for clarification in node.clarification_requirements:
            if clarification.required and not _clarification_satisfied(evidence, clarification):
                blocking_reasons.append(f"Required clarification missing: {clarification.clarification_id}")

        for requirement in node.evidence_requirements:
            if not requirement.required or not bool(requirement.metadata.get("prerequisite")):
                continue
            matched = _matching_evidence(evidence, requirement.subject, evidence_kind=requirement.evidence_kind)
            if matched and max(item.confidence for item in matched) >= requirement.confidence_threshold:
                supporting_evidence.extend(item.evidence_id for item in matched)
            else:
                missing_evidence.append(requirement.requirement_id)

        critical = bool(node.metadata.get("critical_path", False))
        if blocking_reasons:
            readiness = BlueprintNodeReadiness.BLOCKED
        elif any(reason.startswith("Required prerequisite") and reason.split(": ", 1)[-1] in _blocked_subjects(evidence) for reason in dependency_reasons):
            readiness = BlueprintNodeReadiness.UNREACHABLE
        elif dependency_reasons or missing_evidence:
            readiness = BlueprintNodeReadiness.WAITING
        else:
            readiness = BlueprintNodeReadiness.READY
        return BlueprintNodeReadinessEvaluation(
            node_id=node.node_id,
            readiness=readiness,
            expandable=readiness == BlueprintNodeReadiness.READY,
            dependency_reasons=dependency_reasons,
            missing_evidence=missing_evidence,
            blocking_reasons=blocking_reasons,
            supporting_evidence=sorted(set(supporting_evidence)),
            critical_path=critical,
        )


def _incoming_dependencies(blueprint: MissionBlueprint) -> dict[str, list[Any]]:
    incoming: dict[str, list[Any]] = {node.node_id: [] for node in blueprint.nodes}
    for dependency in blueprint.dependencies:
        incoming.setdefault(dependency.to_node_id, []).append(dependency)
    return incoming


def _satisfied_nodes(evidence: list[BlueprintEvidence]) -> set[str]:
    return {
        item.subject
        for item in evidence
        if item.evidence_kind in {"node_satisfied", "blueprint_node_satisfied"}
        and item.validation_status in {"raw", "validated"}
        and item.confidence > 0.0
    }


def _blocked_subjects(evidence: list[BlueprintEvidence]) -> set[str]:
    return {item.subject for item in evidence if item.evidence_kind in {"node_blocked", "blueprint_node_blocked"}}


def _matching_evidence(
    evidence: list[BlueprintEvidence],
    subject: str,
    *,
    evidence_kind: str | None = None,
    validation_optional: bool = False,
) -> list[BlueprintEvidence]:
    return [
        item for item in evidence
        if item.subject == subject
        and (evidence_kind is None or item.evidence_kind == evidence_kind)
        and (validation_optional or item.validation_status in {"raw", "validated"})
    ]


def _has_clarification_evidence(evidence: list[BlueprintEvidence], clarification_node_id: str, blocked_node_id: str) -> bool:
    return any(
        item.evidence_kind == "clarification_obtained"
        and (
            item.subject == clarification_node_id
            or item.subject == blocked_node_id
            or item.metadata.get("blocks_node_id") == blocked_node_id
        )
        for item in evidence
    )


def _clarification_satisfied(evidence: list[BlueprintEvidence], clarification: ClarificationRequirement) -> bool:
    return any(
        item.evidence_kind == "clarification_obtained"
        and (
            item.subject == clarification.clarification_id
            or item.metadata.get("clarification_id") == clarification.clarification_id
        )
        for item in evidence
    )


def _datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return datetime.now(UTC)
