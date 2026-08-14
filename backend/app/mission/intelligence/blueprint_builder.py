from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from app.file_upload_broker.policy import build_file_upload_broker_policy
from app.form_workflow.spec import build_form_workflow_spec
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
from app.signup_policy.policy import build_signup_workflow_policy
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
    if _is_file_processing_workflow(text):
        return MissionType.FILE_PROCESSING
    if _explicit_start_url(text) and _has(text, "extract", "scrape", "collect", "directory", "entries", "records"):
        return MissionType.DATA_EXTRACTION
    if _is_safety_sensitive_browser_workflow(text):
        return MissionType.NAVIGATION
    if _is_multi_source_research(text):
        return MissionType.RESEARCH
    if _has(text, "extract", "scrape", "collect fields", "collect entries", "collect records", "directory", "records", "table with columns"):
        return MissionType.DATA_EXTRACTION
    return MissionType.NAVIGATION


def _is_file_processing_workflow(text: str) -> bool:
    return _has(text, "upload", "download", "pdf", "csv", "spreadsheet") or re.search(r"\bfiles?\b", text) is not None


def _is_upload_workflow(text: str) -> bool:
    lowered = str(text or "").lower()
    if _has(lowered, "uploaded") and not _has(lowered, "upload a", "upload the", "upload file", "file upload", "allows file upload"):
        return False
    return _has(lowered, "upload a", "upload the", "upload file", "file upload", "attach file", "choose file", "select file")


def _is_safety_sensitive_browser_workflow(text: str) -> bool:
    if _has(text, "research", "search the web", "google search", "from search results"):
        return False
    return _has(
        text,
        "signup",
        "sign up",
        "free account",
        "free trial",
        "create account",
        "fill the form",
        "submit only",
        "validation errors",
        "test data",
        "publicly accessible",
    )


def _is_multi_source_research(text: str) -> bool:
    if _has(text, "research", "compare", "comparison", "best ", "top ", "summarize"):
        return True
    if _has(text, "google search", "search for:", "search for ", "search the web", "from search results", "first page of results"):
        return True
    if _has(text, "official websites of 3", "pick 3", "pick 3 different", "choose 3", "first 10 relevant", "top 5 relevant"):
        return True
    if _has(text, "official documentation", "documentation page", "product pages") and _has(text, "different tools", "pick 3", "search"):
        return True
    if _has(text, "jobs", "careers", "openings") and _has(text, "search", "collect", "ranked", "first 10", "choose 3"):
        return True
    return False


def _analyze(understanding: MissionUnderstanding, mission_type: MissionType) -> MissionAnalysis:
    text = understanding.normalized_goal
    constraints = _constraints(text)
    if mission_type == MissionType.RESEARCH and not any(item.startswith("top_n:") for item in constraints):
        constraints.append("top_n:5")
    fields = _requested_fields(text)
    deliverables = [understanding.deliverable]
    secondary: list[str]
    success: list[str]
    quality: list[str] = ["use_observed_evidence", "avoid_provider_specific_assumptions"]
    external = ["external_system_availability"] if mission_type in {MissionType.NAVIGATION, MissionType.RESEARCH, MissionType.DATA_EXTRACTION} else []

    if mission_type == MissionType.RESEARCH:
        secondary = ["open_search_engine", "execute_search", "collect_serp_results", "rank_results", "open_top_results", "read_pages", "extract_required_fields", "validate_coverage", "produce_report"]
        success = ["search_engine_opened", "search_executed", "serp_results_collected", "results_ranked", "top_result_pages_read", "required_information_extracted", f"{understanding.deliverable}_delivered"]
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
        if _needs_collection_policy(analysis.primary_objective):
            capabilities.append("Collection")
    elif mission_type == MissionType.FILE_PROCESSING:
        capabilities = ["File Processing", "Validation", "Report Generation"]
        if any("image" in item.lower() or "scan" in item.lower() for item in analysis.constraints):
            capabilities.extend(["OCR", "Vision"])
    else:
        capabilities = ["Browser", "Validation"]
        if _needs_form_workflow(analysis.primary_objective):
            capabilities.extend(["Form Workflow", "Policy"])
    return CapabilityRequirements(
        capabilities=capabilities,
        rationale={capability: _capability_reason(capability, mission_type) for capability in capabilities},
    )


def _node_spec(
    node_id: str,
    objective: str,
    kind: BlueprintNodeKind,
    required_capability: str,
    provider: str,
    action: str,
    *,
    branch: str | None = None,
    action_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parallelizable = kind in {BlueprintNodeKind.OPEN_RESULT, BlueprintNodeKind.PAGE_READ, BlueprintNodeKind.FIELD_EXTRACTION}
    return {
        "node_id": node_id,
        "objective": objective,
        "kind": kind,
        "required_capability": required_capability,
        "provider": provider,
        "action": action,
        "expected_evidence": _evidence_kind(kind),
        "repeat_policy": _repeat_policy(kind),
        "parallel_policy": {
            "mode": "parallel_branch" if parallelizable else "sequential",
            "parallelizable": parallelizable,
            **({"group": "result_pages"} if parallelizable else {}),
        },
        "critical_path": not parallelizable,
        "branch": branch,
        "action_payload": dict(action_payload or {}),
    }


def _repeat_policy(kind: BlueprintNodeKind) -> dict[str, Any]:
    if kind == BlueprintNodeKind.COLLECTION:
        return {"mode": "until_collection_policy_stop", "max_repeats": 10}
    if kind == BlueprintNodeKind.OPEN_RESULT:
        return {"mode": "per_selected_result", "max_repeats": 1}
    if kind in {BlueprintNodeKind.PAGE_READ, BlueprintNodeKind.FIELD_EXTRACTION}:
        return {"mode": "per_open_result", "max_repeats": 1}
    if kind == BlueprintNodeKind.RESULT_SELECTION:
        return {"mode": "until_top_n_selected", "max_repeats": 1}
    return {"mode": "single", "max_repeats": 1}


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
        top_n = _top_n(analysis.constraints)
        specs = [
            _node_spec("research_mission", "Represent the research mission objective", BlueprintNodeKind.OBJECTIVE, "Mission Blueprint", "mission_blueprint", "record_objective"),
            _node_spec(
                "open_search_engine",
                "Open a search engine entry point",
                BlueprintNodeKind.SEARCH_ENGINE_ENTRY,
                "Browser",
                "browser_control",
                "navigate",
                action_payload={"action_type": "navigate", "value": _search_engine_url(analysis.primary_objective)},
            ),
            _node_spec(
                "execute_search",
                "Execute the research search query",
                BlueprintNodeKind.SEARCH_QUERY,
                "Search",
                "browser_control",
                "submit_search",
                action_payload={"action_type": "navigate", "value": _search_url(analysis.primary_objective)},
            ),
            _node_spec("collect_serp_results", "Collect search result candidates from the SERP", BlueprintNodeKind.SERP_COLLECTION, "Knowledge Extraction", "browser_intelligence", "collect_search_results"),
            _node_spec("rank_results", "Rank collected results for relevance and coverage", BlueprintNodeKind.RESULT_SELECTION, "Validation", "validation", "rank_records"),
        ]
        for index in range(1, top_n + 1):
            specs.extend(
                [
                    _node_spec(
                        f"open_result_{index}",
                        f"Open ranked result {index}",
                        BlueprintNodeKind.OPEN_RESULT,
                        "Browser",
                        "browser_control",
                        "open_new_tab",
                        branch=f"result_{index}",
                    ),
                    _node_spec(
                        f"read_page_{index}",
                        f"Read ranked result page {index}",
                        BlueprintNodeKind.PAGE_READ,
                        "Knowledge Extraction",
                        "knowledge_extraction",
                        "read_page",
                        branch=f"result_{index}",
                    ),
                    _node_spec(
                        f"extract_fields_{index}",
                        f"Extract required fields from result page {index}",
                        BlueprintNodeKind.FIELD_EXTRACTION,
                        "Knowledge Extraction",
                        "knowledge_extraction",
                        "extract_fields",
                        branch=f"result_{index}",
                    ),
                ]
            )
        specs.extend(
            [
                _node_spec("validate_coverage", "Validate required information coverage across extracted pages", BlueprintNodeKind.VALIDATION, "Validation", "validation", "validate_records"),
                _node_spec("generate_report", "Generate the user-visible research report", BlueprintNodeKind.REPORTING, "Report Generation", "knowledge_extraction", "generate_report"),
            ]
        )
    elif mission_type == MissionType.DATA_EXTRACTION:
        start_url = _explicit_start_url(analysis.primary_objective)
        specs = [
            _node_spec(
                "locate_source",
                "Locate source content",
                BlueprintNodeKind.DISCOVERY,
                "Browser",
                "browser_control",
                "navigate",
                action_payload={"action_type": "navigate", "value": start_url} if start_url else None,
            ),
            _node_spec("read_source", "Read source content", BlueprintNodeKind.READING, "Knowledge Extraction", "knowledge_extraction", "read_page"),
        ]
        if _needs_collection_policy(analysis.primary_objective):
            specs.extend(
                [
                    _node_spec(
                        "collect_page_items",
                        "Collect item candidates from the current result/list page",
                        BlueprintNodeKind.COLLECTION,
                        "Collection",
                        "knowledge_extraction",
                        "collect_page_items",
                        action_payload={"policy": "collection_policy.v1"},
                    ),
                    _node_spec(
                        "advance_pagination",
                        "Advance to the next page until collection policy stop conditions are reached",
                        BlueprintNodeKind.COLLECTION,
                        "Browser",
                        "browser_control",
                        "navigate_next_page",
                        action_payload={"stop_conditions": ["requested_count_reached", "max_pages_reached", "no_new_items", "no_next_page"]},
                    ),
                ]
            )
        specs.extend(
            [
                _node_spec("extract_records", "Extract structured records", BlueprintNodeKind.EXTRACTION, "Knowledge Extraction", "knowledge_extraction", "extract_fields"),
                _node_spec("validate_records", "Validate extracted records", BlueprintNodeKind.VALIDATION, "Validation", "validation", "validate_records"),
                _node_spec("deliver_artifact", "Deliver structured extraction artifact", BlueprintNodeKind.REPORTING, "Report Generation", "knowledge_extraction", "generate_report"),
            ]
        )
    elif mission_type == MissionType.FILE_PROCESSING:
        if _is_upload_workflow(analysis.primary_objective):
            upload_policy = build_file_upload_broker_policy(analysis.primary_objective)
            specs = [
                _node_spec("define_file_requirement", "Define required upload file and result evidence", BlueprintNodeKind.OBJECTIVE, "File Processing", "file_processing", "define_file_requirement", action_payload=upload_policy.to_dict()),
                _node_spec("locate_upload_target", "Locate a safe upload target on the page", BlueprintNodeKind.DISCOVERY, "Browser", "browser_control", "navigate"),
                _node_spec("access_file", "Require user-approved selected file handle", BlueprintNodeKind.ACQUISITION, "File Processing", "file_processing", "access_file", action_payload={"requires_user_selected_file": True}),
                _node_spec("activate_upload_control", "Activate the visible file upload control", BlueprintNodeKind.ACQUISITION, "Browser", "browser_control", "click", action_payload={"action_type": "click", "file_upload_broker": upload_policy.to_dict()}),
                _node_spec("validate_file_result", "Validate upload acceptance and result location", BlueprintNodeKind.VALIDATION, "Validation", "validation", "validate_records"),
                _node_spec("deliver_file_result", "Deliver file upload result", BlueprintNodeKind.REPORTING, "Report Generation", "knowledge_extraction", "generate_report"),
            ]
        else:
            specs = [
                _node_spec("define_file_requirement", "Define required file operation and output", BlueprintNodeKind.OBJECTIVE, "File Processing", "file_processing", "define_file_requirement"),
                _node_spec("access_file", "Access required file artifact", BlueprintNodeKind.ACQUISITION, "File Processing", "file_processing", "access_file"),
                _node_spec("process_file", "Process file content", BlueprintNodeKind.EXTRACTION, "File Processing", "file_processing", "process_file"),
                _node_spec("validate_file_result", "Validate processed file artifact", BlueprintNodeKind.VALIDATION, "Validation", "validation", "validate_records"),
                _node_spec("deliver_file_result", "Deliver file processing result", BlueprintNodeKind.REPORTING, "Report Generation", "knowledge_extraction", "generate_report"),
            ]
    elif _needs_form_workflow(analysis.primary_objective):
        form_spec = build_form_workflow_spec(analysis.primary_objective)
        signup_policy = build_signup_workflow_policy(analysis.primary_objective) if form_spec.workflow_type == "signup_workflow" else None
        workflow_payload = {
            **form_spec.to_dict(),
            **({"signup_policy": signup_policy.to_dict()} if signup_policy else {}),
        }
        specs = [
            _node_spec("define_form_workflow", "Define safe form workflow policy and target fields", BlueprintNodeKind.OBJECTIVE, "Form Workflow", "form_workflow", "define_form_workflow", action_payload=workflow_payload),
            _node_spec("locate_form", "Locate the target form or signup flow", BlueprintNodeKind.DISCOVERY, "Browser", "browser_control", "navigate"),
            _node_spec("map_form_fields", "Map visible form controls to requested fields", BlueprintNodeKind.EXTRACTION, "Form Workflow", "form_workflow", "map_form_fields", action_payload={"requires_fake_data": form_spec.requires_fake_data}),
            _node_spec("fill_form_fields", "Fill mapped fields with safe test data", BlueprintNodeKind.EXTRACTION, "Browser", "browser_control", "fill", action_payload={"action_type": "fill", "form_workflow": workflow_payload}),
            _node_spec("validate_form_state", "Validate browser-reported form constraints and visible errors", BlueprintNodeKind.VALIDATION, "Validation", "validation", "validate_records", action_payload={"requires_validation_pass": form_spec.requires_validation_pass}),
        ]
        if form_spec.submit_policy != "never_submit":
            specs.append(
                _node_spec(
                    "submit_if_policy_allows",
                    "Submit only when sandbox policy or explicit approval allows it",
                    BlueprintNodeKind.APPROVAL if form_spec.submit_policy == "approval_required" else BlueprintNodeKind.VALIDATION,
                    "Policy",
                    "policy",
                    "click",
                    action_payload={"action_type": "click", "submit_policy": form_spec.submit_policy, "blocked_submit_reasons": form_spec.blocked_submit_reasons},
                )
            )
        specs.append(_node_spec("report_form_result", "Report validation and submission result", BlueprintNodeKind.REPORTING, "Report Generation", "knowledge_extraction", "generate_report"))
    else:
        target_url = _navigation_target_url(analysis.primary_objective)
        specs = [
            _node_spec("define_target_state", "Define target state", BlueprintNodeKind.OBJECTIVE, "Browser", "mission_blueprint", "record_objective"),
            _node_spec(
                "reach_target_state",
                "Reach target state",
                BlueprintNodeKind.DISCOVERY,
                "Browser",
                "browser_control",
                "navigate",
                action_payload={"action_type": "navigate", "value": target_url} if target_url else None,
            ),
            _node_spec("verify_target_state", "Verify target state", BlueprintNodeKind.VALIDATION, "Validation", "validation", "validate_records"),
        ]
    return [
        BlueprintNode(
            node_id=spec["node_id"],
            objective=spec["objective"],
            kind=spec["kind"],
            execution_type="intent_template",
            required_capability=spec["required_capability"],
            expected_evidence=[spec["expected_evidence"]],
            expansion_template={"provider": spec["provider"], "action": spec["action"], "passive": True},
            repeat_policy=spec["repeat_policy"],
            parallel_policy=spec["parallel_policy"],
            priority=1 if index == 0 else 2 if index < len(specs) - 1 else 3,
            owner_capabilities=[spec["required_capability"]] if spec["required_capability"] in capabilities.capabilities or spec["required_capability"] in {"Mission Blueprint"} else [],
            success_criteria=[f"{spec['node_id']}_satisfied"],
            evidence_requirements=[
                BlueprintEvidenceRequirement(
                    requirement_id=f"evidence_{spec['node_id']}",
                    evidence_kind=spec["expected_evidence"],
                    subject=spec["node_id"],
                    validation_policy="validated" if spec["kind"] in {BlueprintNodeKind.VALIDATION, BlueprintNodeKind.REPORTING} else "raw",
                )
            ],
            expansion_rules=[
                BlueprintExpansionRule(
                    rule_id=f"expand_{spec['node_id']}",
                    capability=spec["required_capability"],
                    intent_template=spec["action"],
                    metadata={"provider": spec["provider"], "action": spec["action"], "passive": True},
                )
            ],
            metadata={
                "critical_path": bool(spec["critical_path"]),
                "provider_independent": True,
                "executable_category": spec["kind"].name,
                **({"action_payload": spec["action_payload"]} if spec.get("action_payload") else {}),
                **({"branch": spec["branch"]} if spec.get("branch") else {}),
            },
        )
        for index, spec in enumerate(specs)
    ]


def _dependencies(
    mission_type: MissionType,
    nodes: list[BlueprintNode],
    clarifications: list[ClarificationRequirement],
) -> list[BlueprintDependency]:
    dependencies: list[BlueprintDependency] = []
    if mission_type == MissionType.RESEARCH:
        node_ids = {node.node_id for node in nodes}
        linear = ["research_mission", "open_search_engine", "execute_search", "collect_serp_results", "rank_results"]
        for left, right in zip(linear, linear[1:]):
            if left in node_ids and right in node_ids:
                dependencies.append(_dependency(left, right, mission_type))
        result_indexes = sorted(
            int(match.group(1))
            for node in nodes
            if (match := re.match(r"open_result_(\d+)$", node.node_id))
        )
        for index in result_indexes:
            dependencies.extend(
                [
                    _dependency("rank_results", f"open_result_{index}", mission_type, critical_path=False, parallel_group="result_pages"),
                    _dependency(f"open_result_{index}", f"read_page_{index}", mission_type, critical_path=False, parallel_group="result_pages"),
                    _dependency(f"read_page_{index}", f"extract_fields_{index}", mission_type, critical_path=False, parallel_group="result_pages"),
                    _dependency(f"extract_fields_{index}", "validate_coverage", mission_type, critical_path=False, parallel_group="result_pages"),
                ]
            )
        dependencies.append(_dependency("validate_coverage", "generate_report", mission_type))
    else:
        for left, right in zip(nodes, nodes[1:]):
            if left.kind == BlueprintNodeKind.CLARIFICATION and not any(item.required for item in clarifications):
                continue
            dependencies.append(_dependency(left.node_id, right.node_id, mission_type))
    if clarifications and nodes:
        clarification_node = next((node for node in nodes if node.kind in {BlueprintNodeKind.CLARIFICATION, BlueprintNodeKind.USER_CLARIFICATION}), None)
        if clarification_node is None:
            return dependencies
        for clarification in clarifications:
            if not clarification.required:
                continue
            for blocked in clarification.blocks_node_ids:
                dependencies.append(
                    BlueprintDependency(
                        dependency_id=f"dep_{clarification_node.node_id}_{blocked}",
                        from_node_id=clarification_node.node_id,
                        to_node_id=blocked,
                        kind=BlueprintDependencyKind.CLARIFICATION,
                        required=True,
                    )
                )
    return dependencies


def _dependency(
    from_node_id: str,
    to_node_id: str,
    mission_type: MissionType,
    *,
    critical_path: bool = True,
    parallel_group: str | None = None,
) -> BlueprintDependency:
    metadata = {"critical_path": critical_path, "mission_type": mission_type.value}
    if parallel_group:
        metadata["parallel_group"] = parallel_group
    return BlueprintDependency(
        dependency_id=f"dep_{from_node_id}_{to_node_id}",
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        kind=BlueprintDependencyKind.PREREQUISITE,
        metadata=metadata,
    )


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
    required_clarifications = [clarification for clarification in clarifications if clarification.required]
    if not required_clarifications:
        return nodes
    clarification_node = BlueprintNode(
        node_id="clarify_requirements",
        objective="Record mission clarification requirements",
        kind=BlueprintNodeKind.USER_CLARIFICATION,
        execution_type="human_input_template",
        required_capability="Human Clarification",
        expected_evidence=["clarification_obtained"],
        expansion_template={"provider": "human_clarification", "action": "request_clarification", "passive": True},
        repeat_policy={"mode": "until_required_clarifications_satisfied", "max_repeats": 1},
        parallel_policy={"mode": "sequential", "parallelizable": False},
        priority=1,
        owner_capabilities=["Human Clarification"],
        clarification_requirements=required_clarifications,
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
                metadata={"provider": "human_clarification", "action": "request_clarification", "passive": True},
            )
        ],
        metadata={"critical_path": True, "provider_independent": True, "executable_category": BlueprintNodeKind.USER_CLARIFICATION.name},
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


def _top_n(constraints: list[str]) -> int:
    for constraint in constraints:
        if constraint.startswith("top_n:"):
            try:
                return max(1, int(constraint.split(":", 1)[1]))
            except ValueError:
                return 5
    return 5


def _search_engine_url(text: str) -> str:
    return "https://www.google.com" if _has(text, "google") else "https://www.google.com"


def _search_url(text: str) -> str:
    from urllib.parse import quote_plus

    return f"{_search_engine_url(text)}/search?q={quote_plus(_search_query(text))}"


def _search_query(text: str) -> str:
    normalized = " ".join(str(text or "").split())
    boundary = r"(?:\bfrom\s+the\s+first\s+page\b|\bfrom\s+first\s+page\b|\bopen\s+top\b|\bopen\s+the\s+top\b|\bread\b|\bextract\b|\breport\b|$)"
    match = re.search(rf"\bsearch\s+for\s*:?\s*(.+?){boundary}", normalized, re.IGNORECASE)
    if not match:
        match = re.search(rf"\bsearch\s*:?\s*(.+?){boundary}", normalized, re.IGNORECASE)
    if match:
        return match.group(1).strip(" .,:;") or normalized
    return normalized


def _explicit_start_url(text: str) -> str:
    match = re.search(r"https?://[^\s<>'\"`]+", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(0).rstrip(".,);]")


def _navigation_target_url(text: str) -> str:
    explicit = _explicit_start_url(text)
    if explicit:
        return explicit
    lowered = str(text or "").lower()
    known_apps = {
        "whatsapp web": "https://web.whatsapp.com/",
        "whatsapp": "https://web.whatsapp.com/",
        "gmail": "https://mail.google.com/",
        "linkedin jobs": "https://www.linkedin.com/jobs/",
        "linkedin": "https://www.linkedin.com/",
    }
    for name, url in known_apps.items():
        if name in lowered:
            return url
    return ""


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


def _needs_collection_policy(text: str) -> bool:
    lowered = str(text or "").lower()
    explicit_collection = any(term in lowered for term in ("collect entries", "collect records", "collect ", "listings", "pagination", "next page", "infinite scroll"))
    paginated_source = any(term in lowered for term in ("multi-page", "multiple pages", "page directory", "directory entries"))
    return explicit_collection or paginated_source


def _needs_form_workflow(text: str) -> bool:
    return _has(
        text,
        "form",
        "fill",
        "validation errors",
        "test data",
        "fake data",
        "signup",
        "sign up",
        "create account",
        "free account",
        "free trial",
    )


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
        BlueprintNodeKind.SEARCH_ENGINE_ENTRY: "search_engine_entry_opened",
        BlueprintNodeKind.SEARCH_QUERY: "search_query_executed",
        BlueprintNodeKind.SERP_COLLECTION: "serp_results_collected",
        BlueprintNodeKind.RESULT_SELECTION: "ranked_result_selection",
        BlueprintNodeKind.OPEN_RESULT: "result_page_opened",
        BlueprintNodeKind.PAGE_READ: "page_read",
        BlueprintNodeKind.FIELD_EXTRACTION: "field_extraction",
        BlueprintNodeKind.USER_CLARIFICATION: "clarification_obtained",
        BlueprintNodeKind.WAIT: "wait_completed",
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
