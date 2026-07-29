from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intent_dispatcher.models import IntentDispatchDirective
from app.mission.blueprint.models import BlueprintNode, MissionBlueprint
from app.mission.blueprint.readiness import BlueprintReadinessSnapshot
from app.mission.blueprint.repository import MissionBlueprintRepository
from app.services import mission_ledger_service


@dataclass(frozen=True)
class BlueprintNodeExpansionResult:
    node_id: str
    expanded: bool
    generated_intent_ids: list[str] = field(default_factory=list)
    skipped_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BlueprintExpansionResult:
    mission_id: str
    blueprint_id: str
    blueprint_revision: int
    expanded_nodes: list[str]
    pending_nodes: list[str]
    generated_intent_ids: list[str]
    node_results: list[BlueprintNodeExpansionResult]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


class BlueprintExpansionEngine:
    """Compiles READY Blueprint nodes into queued Mission Ledger intents."""

    def __init__(self, *, db: Session, repository: MissionBlueprintRepository):
        self.db = db
        self.repository = repository

    def expand_ready_nodes(
        self,
        *,
        mission_id: str,
        readiness: BlueprintReadinessSnapshot | None = None,
    ) -> BlueprintExpansionResult:
        blueprint = self.repository.get(mission_id)
        if blueprint is None:
            raise LookupError(f"Mission Blueprint for mission {mission_id!r} not found")
        readiness = readiness or self.repository.latest_readiness_snapshot(mission_id)
        ready_nodes = set(readiness.ready_nodes if readiness is not None else [])
        node_results: list[BlueprintNodeExpansionResult] = []
        generated: list[str] = []

        for node in blueprint.nodes:
            if node.node_id not in ready_nodes:
                node_results.append(
                    BlueprintNodeExpansionResult(
                        node_id=node.node_id,
                        expanded=False,
                        skipped_reason="node_not_ready",
                    )
                )
                continue
            existing = self.repository.expansion_for_node(mission_id, node.node_id, blueprint.revision)
            if existing is not None:
                ids = list(existing.get("generated_intent_ids") or [])
                node_results.append(
                    BlueprintNodeExpansionResult(
                        node_id=node.node_id,
                        expanded=False,
                        generated_intent_ids=ids,
                        skipped_reason="already_expanded",
                        diagnostics=dict(existing.get("diagnostics") or {}),
                    )
                )
                generated.extend(ids)
                continue
            directives = compile_node_to_intents(blueprint, node)
            records = [
                mission_ledger_service.upsert_intent(
                    self.db,
                    mission_id=mission_id,
                    directive=directive,
                    status="QUEUED",
                )
                for directive in directives
            ]
            ids = [record.intent_id for record in records]
            diagnostics = {
                "compiled_intent_count": len(ids),
                "compiled_intents": [directive.intent for directive in directives],
                "expanded_at": datetime.now(UTC).isoformat(),
                "execution_impact": "queued_only_no_dispatch",
            }
            self.repository.record_expansion(
                mission_id=mission_id,
                blueprint_id=blueprint.blueprint_id,
                blueprint_node_id=node.node_id,
                blueprint_revision=blueprint.revision,
                generated_intent_ids=ids,
                diagnostics=diagnostics,
            )
            node_results.append(
                BlueprintNodeExpansionResult(
                    node_id=node.node_id,
                    expanded=True,
                    generated_intent_ids=ids,
                    diagnostics=diagnostics,
                )
            )
            generated.extend(ids)

        return BlueprintExpansionResult(
            mission_id=mission_id,
            blueprint_id=blueprint.blueprint_id,
            blueprint_revision=blueprint.revision,
            expanded_nodes=[result.node_id for result in node_results if result.expanded],
            pending_nodes=[result.node_id for result in node_results if not result.expanded],
            generated_intent_ids=generated,
            node_results=node_results,
        )


def compile_node_to_intents(blueprint: MissionBlueprint, node: BlueprintNode) -> list[IntentDispatchDirective]:
    templates = _templates_for_node(node)
    return [
        IntentDispatchDirective(
            intent_id=f"intent_{uuid.uuid4().hex}",
            mission_id=blueprint.mission_id,
            parent_intent_id=None,
            intent=template["intent"],
            owner=template["owner"],
            capability=template["capability"],
            dispatch_target=template["dispatch_target"],
            browser_executable=template["owner"] == "browser_control",
            reason=f"Compiled from Blueprint node {node.node_id}: {node.objective}",
            payload={
                "action_type": template["intent"],
                "description": template["description"],
                "reasoning": f"Blueprint node objective: {node.objective}",
                "confidence": 0.8,
                "safety_level": "safe",
                "blueprint_id": blueprint.blueprint_id,
                "blueprint_node_id": node.node_id,
                "blueprint_revision": blueprint.revision,
                "blueprint_objective": node.objective,
                "wave_3b_compiled": True,
            },
        )
        for template in templates
    ]


def _templates_for_node(node: BlueprintNode) -> list[dict[str, str]]:
    node_id = node.node_id
    if node_id == "discover_sources":
        return [
            _browser_template("navigate", "Navigate to an appropriate discovery surface"),
            _browser_template("execute_search", "Execute the source discovery query"),
            _knowledge_template("collect_search_results", "Collect discovered result entities"),
        ]
    if node_id in {"collect_candidates", "read_sources", "read_source"}:
        return [_knowledge_template("read_page", node.objective)]
    if node_id in {"extract_information", "extract_records", "process_file"}:
        return [_knowledge_template("extract_fields", node.objective)]
    if node_id in {"validate_coverage", "validate_records", "validate_file_result", "verify_target_state"}:
        return [_validation_template("validate_records", node.objective)]
    if node_id in {"create_report", "deliver_artifact", "deliver_file_result"}:
        return [_report_template("synthesize_report", node.objective)]
    if node_id in {"reach_target_state", "locate_source", "access_file"}:
        owner = "file_processing" if node_id == "access_file" else "browser_control"
        return [_template("navigate" if owner == "browser_control" else "access_file", owner, owner, node.objective)]
    return [_runtime_template("record_blueprint_node_ready", node.objective)]


def _browser_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "browser_control", "browser", description)


def _knowledge_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "knowledge_extraction", "knowledge_extraction", description)


def _validation_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "validation", "validation", description)


def _report_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "mission_completion", "report_generation", description)


def _runtime_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "runtime_state", "runtime_state", description)


def _template(intent: str, owner: str, capability: str, description: str) -> dict[str, str]:
    return {
        "intent": intent,
        "owner": owner,
        "capability": capability,
        "dispatch_target": owner,
        "description": description,
    }
