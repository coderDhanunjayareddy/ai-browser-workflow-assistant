from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from app.mission.blueprint.models import (
    BlueprintDependency,
    BlueprintDependencyKind,
    BlueprintEvidenceRequirement,
    BlueprintExpansionRule,
    BlueprintNode,
    BlueprintNodeKind,
    ClarificationRequirement,
    MissionBlueprint,
    validate_blueprint,
)
from app.mission.blueprint.readiness import BlueprintReadinessSnapshot
from app.mission.blueprint.repository import MissionBlueprintRepository
from app.mission.blueprint.service import MissionBlueprintPersistenceService


class MissionType(str, Enum):
    RESEARCH = "research"
    NAVIGATION = "navigation"
    DATA_EXTRACTION = "data_extraction"
    FILE_PROCESSING = "file_processing"


@dataclass(frozen=True)
class MissionUnderstanding:
    raw_goal: str
    normalized_goal: str
    deliverable: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionAnalysis:
    primary_objective: str
    secondary_objectives: list[str]
    constraints: list[str]
    deliverables: list[str]
    success_criteria: list[str]
    quality_requirements: list[str]
    external_dependencies: list[str]
    unknown_information: list[str]
    user_preferences: list[str]
    risk_factors: list[str]
    blocking_requirements: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityRequirements:
    capabilities: list[str]
    rationale: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskAssessment:
    risks: list[str]
    annotations: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DependencyAnalysis:
    sequential_dependencies: list[dict[str, str]]
    parallel_opportunities: list[list[str]]
    critical_path: list[str]
    evidence_dependencies: list[dict[str, str]]
    clarification_dependencies: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlueprintBuildResult:
    blueprint: MissionBlueprint
    understanding: MissionUnderstanding
    analysis: MissionAnalysis
    mission_type: MissionType
    capabilities: CapabilityRequirements
    risks: RiskAssessment
    dependencies: DependencyAnalysis


class MissionBlueprintBuilder:
    """Creates passive Mission Blueprints from Mission Intelligence understanding."""

    def build(self, *, mission_id: str, user_goal: str) -> BlueprintBuildResult:
        understanding = _understand(user_goal)
        mission_type = _classify(understanding)
        analysis = _analyze(understanding, mission_type)
        capabilities = _capabilities(mission_type, analysis)
        risks = _risks(understanding, analysis)
        nodes = _nodes(mission_type, analysis, capabilities)
        clarifications = _clarifications(analysis, nodes)
        nodes = _attach_clarifications(nodes, clarifications)
        dependencies = _dependencies(mission_type, nodes, clarifications)
        dependency_analysis = _dependency_analysis(nodes, dependencies, clarifications)
        metadata = {
            "mission_understanding": understanding.to_dict(),
            "mission_analysis": analysis.to_dict(),
            "mission_classification": {"primary_type": mission_type.value},
            "capability_requirements": capabilities.to_dict(),
            "risk_summary": risks.to_dict(),
            "dependency_analysis": dependency_analysis.to_dict(),
            "clarification_requirements": [asdict(item) for item in clarifications],
            "wave": "mission_blueprint_v1_wave2",
            "execution_impact": "none",
        }
        service = _in_memory_service()
        blueprint = service.create(
            mission_id=mission_id,
            objective=analysis.primary_objective,
            nodes=nodes,
            dependencies=dependencies,
            constraints=analysis.constraints,
            success_criteria=analysis.success_criteria,
            recovery_rules=[
                "revise_blueprint_when_evidence_contradicts_objective",
                "record_clarification_requirement_when_required_information_is_missing",
                "do_not_expand_nodes_until_wave_3",
            ],
            termination_rules=[
                "mission_completion_remains_the_only_completion_authority",
                "blueprint_is_passive_and_never_executes",
            ],
            approval_policy={
                "require_user_approval_for": [
                    risk for risk in risks.risks if risk in {"payment", "irreversible_action", "privacy"}
                ]
            },
            metadata=metadata,
        )
        validate_blueprint(blueprint)
        return BlueprintBuildResult(
            blueprint=blueprint,
            understanding=understanding,
            analysis=analysis,
            mission_type=mission_type,
            capabilities=capabilities,
            risks=risks,
            dependencies=dependency_analysis,
        )


def create_and_store_blueprint(
    *,
    mission_id: str,
    user_goal: str,
    repository: MissionBlueprintRepository,
    created_by: str = "mission_intelligence",
) -> BlueprintBuildResult:
    """Build and persist a passive Mission Blueprint revision 1."""
    result = MissionBlueprintBuilder().build(mission_id=mission_id, user_goal=user_goal)
    service = MissionBlueprintPersistenceService(repository)
    persisted = service.repository.create(
        result.blueprint,
        reason="mission intelligence decomposition",
        created_by=created_by,
    )
    return BlueprintBuildResult(
        blueprint=persisted,
        understanding=result.understanding,
        analysis=result.analysis,
        mission_type=result.mission_type,
        capabilities=result.capabilities,
        risks=result.risks,
        dependencies=result.dependencies,
    )


def _understand(goal: str) -> MissionUnderstanding:
    normalized = " ".join(str(goal or "").strip().split())
    deliverable = "user_visible_outcome"
    if _has(normalized, "table", "comparison"):
        deliverable = "comparison_table"
    elif _has(normalized, "summary", "summarize", "report"):
        deliverable = "report"
    elif _has(normalized, "download", "file"):
        deliverable = "file_artifact"
    elif _has(normalized, "open", "go to", "navigate"):
        deliverable = "browser_state"
    return MissionUnderstanding(raw_goal=goal, normalized_goal=normalized, deliverable=deliverable)


def _classify(understanding: MissionUnderstanding) -> MissionType:
    text = understanding.normalized_goal.lower()
    if _has(text, "research", "compare", "best ", "top ", "summarize", "report"):
        return MissionType.RESEARCH
    if _has(text, "extract", "scrape", "collect fields", "records", "table with columns"):
        return MissionType.DATA_EXTRACTION
    if _has(text, "upload", "download", "file", "pdf", "csv", "spreadsheet"):
        return MissionType.FILE_PROCESSING
    return MissionType.NAVIGATION


def _analyze(understanding: MissionUnderstanding, mission_type: MissionType) -> MissionAnalysis:
    text = understanding.normalized_goal
    constraints = _constraints(text)
    fields = _requested_fields(text)
    deliverables = [understanding.deliverable]
    secondary: list[str]
    success: list[str]
    quality: list[str] = ["use_observed_evidence", "avoid_provider_specific_assumptions"]
    external = ["external_system_availability"] if mission_type in {MissionType.NAVIGATION, MissionType.RESEARCH, MissionType.DATA_EXTRACTION} else []

    if mission_type == MissionType.RESEARCH:
        secondary = ["discover_sources", "collect_candidates", "read_sources", "extract_required_information", "validate_coverage", "produce_report"]
        success = ["sources_discovered", "relevant_sources_selected", "source_pages_read", "required_information_extracted", f"{understanding.deliverable}_delivered"]
    elif mission_type == MissionType.DATA_EXTRACTION:
        secondary = ["locate_source", "read_source", "extract_records", "validate_records", "deliver_structured_artifact"]
        success = ["source_available", "records_extracted", "records_validated", "structured_artifact_delivered"]
    elif mission_type == MissionType.FILE_PROCESSING:
        secondary = ["identify_file_requirement", "access_file", "process_file", "validate_file_artifact", "deliver_file_result"]
        success = ["file_identified", "file_processed", "file_artifact_validated", "file_result_delivered"]
    else:
        secondary = ["identify_target_state", "reach_target_state", "verify_target_state"]
        success = ["target_state_identified", "target_state_reached", "target_state_verified"]

    unknowns = []
    if _has(text, "top ", "best ", "relevant"):
        unknowns.append("ranking_or_relevance_policy")
    if _has(text, "account", "login", "sign in") and not _has(text, "use current account"):
        unknowns.append("account_or_authentication_context")
    if fields:
        quality.append("required_fields:" + ",".join(fields))

    return MissionAnalysis(
        primary_objective=text,
        secondary_objectives=secondary,
        constraints=constraints,
        deliverables=deliverables,
        success_criteria=success,
        quality_requirements=quality,
        external_dependencies=external,
        unknown_information=unknowns,
        user_preferences=_preferences(text),
        risk_factors=[],
        blocking_requirements=[],
    )


def _capabilities(mission_type: MissionType, analysis: MissionAnalysis) -> CapabilityRequirements:
    capabilities: list[str]
    if mission_type == MissionType.RESEARCH:
        capabilities = ["Search", "Browser", "Knowledge Extraction", "Validation", "Report Generation"]
    elif mission_type == MissionType.DATA_EXTRACTION:
        capabilities = ["Browser", "Knowledge Extraction", "Validation", "Report Generation"]
    elif mission_type == MissionType.FILE_PROCESSING:
        capabilities = ["File Processing", "Validation", "Report Generation"]
        if any("image" in item.lower() or "scan" in item.lower() for item in analysis.constraints):
            capabilities.extend(["OCR", "Vision"])
    else:
        capabilities = ["Browser", "Validation"]
    return CapabilityRequirements(
        capabilities=capabilities,
        rationale={capability: _capability_reason(capability, mission_type) for capability in capabilities},
    )


def _risks(understanding: MissionUnderstanding, analysis: MissionAnalysis) -> RiskAssessment:
    text = understanding.normalized_goal.lower()
    risks: list[str] = []
    annotations: dict[str, str] = {}
    checks = {
        "authentication": ("login", "sign in", "account", "authenticated"),
        "payment": ("buy", "purchase", "checkout", "payment", "book"),
        "irreversible_action": ("submit", "send", "publish", "delete", "apply"),
        "privacy": ("personal", "email", "phone", "address", "resume"),
        "external_dependency": ("wait for", "confirmation", "external"),
        "waiting_state": ("wait", "pending", "later"),
    }
    for risk, needles in checks.items():
        if _has(text, *needles):
            risks.append(risk)
            annotations[risk] = f"Detected from goal terms: {', '.join(needles)}"
    if analysis.unknown_information:
        risks.append("missing_information")
        annotations["missing_information"] = ", ".join(analysis.unknown_information)
    if not risks:
        risks.append("low")
        annotations["low"] = "No high-impact mission-level risk detected from the request."
    return RiskAssessment(risks=risks, annotations=annotations)


def _nodes(
    mission_type: MissionType,
    analysis: MissionAnalysis,
    capabilities: CapabilityRequirements,
) -> list[BlueprintNode]:
    if mission_type == MissionType.RESEARCH:
        specs = [
            ("define_research_target", "Define research target and evidence requirements", BlueprintNodeKind.OBJECTIVE, ["Search"]),
            ("discover_sources", "Discover relevant information sources", BlueprintNodeKind.DISCOVERY, ["Search", "Browser"]),
            ("collect_candidates", "Collect candidate source entities", BlueprintNodeKind.COLLECTION, ["Knowledge Extraction"]),
            ("select_sources", "Select sources that satisfy relevance constraints", BlueprintNodeKind.SELECTION, ["Validation"]),
            ("read_sources", "Read selected source content", BlueprintNodeKind.READING, ["Browser", "Knowledge Extraction"]),
            ("extract_information", "Extract required information from source evidence", BlueprintNodeKind.EXTRACTION, ["Knowledge Extraction"]),
            ("validate_coverage", "Validate required information coverage", BlueprintNodeKind.VALIDATION, ["Validation"]),
            ("create_report", "Create user-visible deliverable", BlueprintNodeKind.REPORTING, ["Report Generation"]),
        ]
    elif mission_type == MissionType.DATA_EXTRACTION:
        specs = [
            ("define_schema", "Define extraction schema and source requirements", BlueprintNodeKind.OBJECTIVE, ["Knowledge Extraction"]),
            ("locate_source", "Locate source content", BlueprintNodeKind.DISCOVERY, ["Browser"]),
            ("read_source", "Read source content", BlueprintNodeKind.READING, ["Browser", "Knowledge Extraction"]),
            ("extract_records", "Extract structured records", BlueprintNodeKind.EXTRACTION, ["Knowledge Extraction"]),
            ("validate_records", "Validate extracted records", BlueprintNodeKind.VALIDATION, ["Validation"]),
            ("deliver_artifact", "Deliver structured extraction artifact", BlueprintNodeKind.REPORTING, ["Report Generation"]),
        ]
    elif mission_type == MissionType.FILE_PROCESSING:
        specs = [
            ("define_file_requirement", "Define required file operation and output", BlueprintNodeKind.OBJECTIVE, ["File Processing"]),
            ("access_file", "Access required file artifact", BlueprintNodeKind.ACQUISITION, ["File Processing"]),
            ("process_file", "Process file content", BlueprintNodeKind.EXTRACTION, ["File Processing"]),
            ("validate_file_result", "Validate processed file artifact", BlueprintNodeKind.VALIDATION, ["Validation"]),
            ("deliver_file_result", "Deliver file processing result", BlueprintNodeKind.REPORTING, ["Report Generation"]),
        ]
    else:
        specs = [
            ("define_target_state", "Define target state", BlueprintNodeKind.OBJECTIVE, ["Browser"]),
            ("reach_target_state", "Reach target state", BlueprintNodeKind.DISCOVERY, ["Browser"]),
            ("verify_target_state", "Verify target state", BlueprintNodeKind.VALIDATION, ["Validation"]),
        ]
    return [
        BlueprintNode(
            node_id=node_id,
            objective=objective,
            kind=kind,
            priority=1 if index == 0 else 2 if index < len(specs) - 1 else 3,
            owner_capabilities=[capability for capability in owner_caps if capability in capabilities.capabilities],
            success_criteria=[f"{node_id}_satisfied"],
            evidence_requirements=[
                BlueprintEvidenceRequirement(
                    requirement_id=f"evidence_{node_id}",
                    evidence_kind=_evidence_kind(kind),
                    subject=node_id,
                    validation_policy="validated" if kind in {BlueprintNodeKind.VALIDATION, BlueprintNodeKind.REPORTING} else "raw",
                )
            ],
            expansion_rules=[
                BlueprintExpansionRule(
                    rule_id=f"expand_{node_id}",
                    capability=owner_caps[0],
                    intent_template=node_id,
                    metadata={"wave_2_passive": True},
                )
            ],
            metadata={"critical_path": True, "provider_independent": True},
        )
        for index, (node_id, objective, kind, owner_caps) in enumerate(specs)
    ]


def _dependencies(
    mission_type: MissionType,
    nodes: list[BlueprintNode],
    clarifications: list[ClarificationRequirement],
) -> list[BlueprintDependency]:
    dependencies: list[BlueprintDependency] = []
    for left, right in zip(nodes, nodes[1:]):
        dependencies.append(
            BlueprintDependency(
                dependency_id=f"dep_{left.node_id}_{right.node_id}",
                from_node_id=left.node_id,
                to_node_id=right.node_id,
                kind=BlueprintDependencyKind.PREREQUISITE,
                metadata={"critical_path": True, "mission_type": mission_type.value},
            )
        )
    if clarifications and nodes:
        clarification_node = next((node for node in nodes if node.kind == BlueprintNodeKind.CLARIFICATION), None)
        if clarification_node is None:
            return dependencies
        for blocked in clarifications[0].blocks_node_ids:
            dependencies.append(
                BlueprintDependency(
                    dependency_id=f"dep_{clarification_node.node_id}_{blocked}",
                    from_node_id=clarification_node.node_id,
                    to_node_id=blocked,
                    kind=BlueprintDependencyKind.CLARIFICATION,
                )
            )
    return dependencies


def _clarifications(analysis: MissionAnalysis, nodes: list[BlueprintNode]) -> list[ClarificationRequirement]:
    requirements: list[ClarificationRequirement] = []
    if "account_or_authentication_context" in analysis.unknown_information:
        requirements.append(
            ClarificationRequirement(
                clarification_id="clarify_account_or_authentication_context",
                question="Which account or authenticated session should be used?",
                blocks_node_ids=[nodes[1].node_id] if len(nodes) > 1 else [],
                metadata={"reason": "authentication context is required"},
            )
        )
    if "ranking_or_relevance_policy" in analysis.unknown_information:
        requirements.append(
            ClarificationRequirement(
                clarification_id="clarify_ranking_or_relevance_policy",
                question="How should relevance or ranking be interpreted if page evidence is ambiguous?",
                required=False,
                blocks_node_ids=[],
                metadata={"reason": "reasonable default can use visible/source ranking"},
            )
        )
    return requirements


def _attach_clarifications(nodes: list[BlueprintNode], clarifications: list[ClarificationRequirement]) -> list[BlueprintNode]:
    if not clarifications:
        return nodes
    clarification_node = BlueprintNode(
        node_id="clarify_requirements",
        objective="Record mission clarification requirements",
        kind=BlueprintNodeKind.CLARIFICATION,
        priority=1,
        owner_capabilities=["Human Clarification"],
        clarification_requirements=clarifications,
        success_criteria=["clarification_requirements_recorded"],
        evidence_requirements=[
            BlueprintEvidenceRequirement(
                requirement_id="evidence_clarification_requirements",
                evidence_kind="clarification_requirement",
                subject="mission",
            )
        ],
        expansion_rules=[
            BlueprintExpansionRule(
                rule_id="expand_clarification_requirements",
                capability="Human Clarification",
                intent_template="request_clarification",
                metadata={"wave_2_passive": True},
            )
        ],
    )
    return [clarification_node, *nodes]


def _dependency_analysis(
    nodes: list[BlueprintNode],
    dependencies: list[BlueprintDependency],
    clarifications: list[ClarificationRequirement],
) -> DependencyAnalysis:
    return DependencyAnalysis(
        sequential_dependencies=[
            {
                "from": dependency.from_node_id,
                "to": dependency.to_node_id,
                "kind": dependency.kind.value,
            }
            for dependency in dependencies
            if dependency.kind == BlueprintDependencyKind.PREREQUISITE
        ],
        parallel_opportunities=[
            [node.node_id for node in nodes if not bool(node.metadata.get("critical_path"))]
        ],
        critical_path=[node.node_id for node in nodes if bool(node.metadata.get("critical_path"))],
        evidence_dependencies=[
            {
                "node_id": node.node_id,
                "evidence": requirement.evidence_kind,
                "subject": requirement.subject,
            }
            for node in nodes
            for requirement in node.evidence_requirements
        ],
        clarification_dependencies=[
            {
                "clarification_id": requirement.clarification_id,
                "blocks": ",".join(requirement.blocks_node_ids),
            }
            for requirement in clarifications
        ],
    )


def _constraints(text: str) -> list[str]:
    constraints: list[str] = []
    match = re.search(r"\btop\s+(\d+)\b", text, re.IGNORECASE)
    if match:
        constraints.append(f"top_n:{match.group(1)}")
    if _has(text, "first page"):
        constraints.append("first_page_only")
    if _has(text, "table only"):
        constraints.append("output_table_only")
    if _has(text, "current", "2026", "latest"):
        constraints.append("freshness_required")
    return constraints


def _preferences(text: str) -> list[str]:
    preferences: list[str] = []
    if _has(text, "table only"):
        preferences.append("return_table_only")
    if _has(text, "clean comparison table"):
        preferences.append("clean_comparison_table")
    return preferences


def _requested_fields(text: str) -> list[str]:
    fields = [field for field in ["tool", "product name", "purpose", "pricing", "limitation", "url"] if field in text.lower()]
    return fields


def _evidence_kind(kind: BlueprintNodeKind) -> str:
    return {
        BlueprintNodeKind.OBJECTIVE: "mission_understanding",
        BlueprintNodeKind.DISCOVERY: "candidate_discovery",
        BlueprintNodeKind.COLLECTION: "entity_collection",
        BlueprintNodeKind.SELECTION: "selection_evidence",
        BlueprintNodeKind.READING: "page_read",
        BlueprintNodeKind.EXTRACTION: "field_extraction",
        BlueprintNodeKind.VALIDATION: "validation_result",
        BlueprintNodeKind.REPORTING: "artifact_created",
        BlueprintNodeKind.ACQUISITION: "artifact_available",
    }.get(kind, "mission_evidence")


def _capability_reason(capability: str, mission_type: MissionType) -> str:
    return f"Required for {mission_type.value} mission capability: {capability}."


def _has(text: str, *needles: str) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _in_memory_service() -> MissionBlueprintPersistenceService:
    class _InMemoryRepository(MissionBlueprintRepository):
        def create(self, blueprint: MissionBlueprint, *, reason: str = "initial", created_by: str = "mission_intelligence") -> MissionBlueprint:
            return blueprint

        def get(self, mission_id: str) -> MissionBlueprint | None:
            return None

        def update(self, blueprint: MissionBlueprint, *, reason: str = "update", created_by: str = "mission_intelligence") -> MissionBlueprint:
            return blueprint

        def save_revision(self, blueprint: MissionBlueprint, *, reason: str, created_by: str = "mission_intelligence") -> str:
            return "in_memory_revision"

        def get_revision(self, mission_id: str, revision: int) -> MissionBlueprint | None:
            return None

        def list_revisions(self, mission_id: str) -> list[dict[str, Any]]:
            return []

        def list_nodes(self, mission_id: str, *, revision: int | None = None) -> list[BlueprintNode]:
            return []

        def delete(self, mission_id: str) -> bool:
            return False

        def save_readiness_snapshot(self, snapshot: BlueprintReadinessSnapshot) -> BlueprintReadinessSnapshot:
            return snapshot

        def latest_readiness_snapshot(self, mission_id: str) -> BlueprintReadinessSnapshot | None:
            return None

        def list_readiness_snapshots(self, mission_id: str) -> list[BlueprintReadinessSnapshot]:
            return []

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
            return {
                "expansion_id": "in_memory_expansion",
                "mission_id": mission_id,
                "blueprint_id": blueprint_id,
                "blueprint_node_id": blueprint_node_id,
                "blueprint_revision": blueprint_revision,
                "generated_intent_ids": list(generated_intent_ids),
                "diagnostics": dict(diagnostics),
                "status": status,
            }

        def list_expansions(self, mission_id: str) -> list[dict[str, Any]]:
            return []

        def expansion_for_node(self, mission_id: str, blueprint_node_id: str, blueprint_revision: int) -> dict[str, Any] | None:
            return None

    return MissionBlueprintPersistenceService(_InMemoryRepository())
