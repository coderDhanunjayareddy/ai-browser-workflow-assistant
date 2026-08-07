from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import re
from typing import Any

from sqlalchemy.orm import Session

from app.browser_url_policy import is_openable_browser_url
from app.intent_dispatcher.models import IntentDispatchDirective
from app.mission.blueprint.models import BlueprintNode, BlueprintNodeKind, MissionBlueprint
from app.mission.blueprint.readiness import BlueprintReadinessSnapshot
from app.mission.blueprint.repository import MissionBlueprintRepository
from app.models.db import MissionIntentRecord
from app.services import mission_ledger_service


KNOWLEDGE_EXTRACTION_DISPATCH_TARGET = "knowledge_extraction_pipeline"


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
        ranked_results = _ranked_results_from_ledger(self.db, mission_id=mission_id)

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
            directives = compile_node_to_intents(blueprint, node, ranked_results=ranked_results)
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


def compile_node_to_intents(
    blueprint: MissionBlueprint,
    node: BlueprintNode,
    *,
    ranked_results: list[dict[str, Any]] | None = None,
) -> list[IntentDispatchDirective]:
    if node.expansion_template:
        provider = str(node.expansion_template.get("provider") or "").strip()
        action = str(node.expansion_template.get("action") or "").strip()
        if node.kind == BlueprintNodeKind.OBJECTIVE and provider == "mission_blueprint" and action in {"record_objective", "record_node_ready"}:
            return []
    templates = _templates_for_node(node)
    open_result_payload = _open_result_payload(node, ranked_results or [])
    if node.node_id.startswith("open_result_") and not open_result_payload.get("value"):
        return []
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
                **dict(node.metadata.get("action_payload") or {}),
                **open_result_payload,
            },
        )
        for template in templates
    ]


def _open_result_payload(node: BlueprintNode, ranked_results: list[dict[str, Any]]) -> dict[str, Any]:
    match = re.match(r"^open_result_(\d+)$", node.node_id)
    if not match:
        return {}
    index = int(match.group(1)) - 1
    if index < 0 or index >= len(ranked_results):
        return {}
    result = ranked_results[index]
    url = str(_read(result, "url") or _read(result, "href") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {}
    title = str(_read(result, "title") or _read(result, "text") or "").strip()
    payload = {
        "value": url,
        "url": url,
        "rank": _read(result, "rank") or index + 1,
    }
    if title:
        payload["title"] = title
    return payload


def _ranked_results_from_ledger(db: Session, *, mission_id: str) -> list[dict[str, Any]]:
    records = (
        db.query(MissionIntentRecord)
        .filter(MissionIntentRecord.mission_id == mission_id)
        .filter(MissionIntentRecord.status == "COMPLETED")
        .filter(MissionIntentRecord.blueprint_node_id == "rank_results")
        .order_by(MissionIntentRecord.updated_at.desc())
        .all()
    )
    for record in records:
        for item in reversed(list(record.evidence or [])):
            payload = _read(item, "payload") or {}
            ranked_results = _read(payload, "ranked_results")
            if ranked_results:
                return [
                    dict(result)
                    for result in ranked_results
                    if isinstance(result, dict)
                    and is_openable_browser_url(str(_read(result, "url") or _read(result, "href") or ""))
                ]
    return []


def _read(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _templates_for_node(node: BlueprintNode) -> list[dict[str, str]]:
    if node.expansion_template:
        provider = str(node.expansion_template.get("provider") or "").strip()
        action = str(node.expansion_template.get("action") or "").strip()
        if provider and action and (provider, action) != ("mission_blueprint", "record_node_ready"):
            return [_template(action, provider, node.required_capability, node.objective)]
    node_id = node.node_id
    if node_id == "open_search_engine":
        return [_browser_template("navigate", node.objective)]
    if node_id == "execute_search":
        return [_browser_template("submit_search", node.objective)]
    if node_id == "collect_serp_results":
        return [_template("collect_search_results", "browser_intelligence", "Browser Intelligence", node.objective)]
    if node_id == "rank_results":
        return [_validation_template("rank_records", node.objective)]
    if node_id.startswith("open_result_"):
        return [_browser_template("open_new_tab", node.objective)]
    if node_id.startswith("read_page_"):
        return [_knowledge_template("read_page", node.objective)]
    if node_id.startswith("extract_fields_"):
        return [_knowledge_template("extract_fields", node.objective)]
    if node_id == "generate_report":
        return [_knowledge_template("generate_report", node.objective)]
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
    return [_template("record_node_ready", "mission_blueprint", "Mission Blueprint", node.objective)]


def _browser_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "browser_control", "browser", description)


def _knowledge_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "knowledge_extraction", "knowledge_extraction", description)


def _validation_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "validation", "validation", description)


def _report_template(intent: str, description: str) -> dict[str, str]:
    return _template(intent, "mission_completion", "report_generation", description)


def _template(intent: str, owner: str, capability: str, description: str) -> dict[str, str]:
    return {
        "intent": intent,
        "owner": owner,
        "capability": capability,
        "dispatch_target": _dispatch_target_for_owner(owner),
        "description": description,
    }


def _dispatch_target_for_owner(owner: str) -> str:
    if owner == "knowledge_extraction":
        return KNOWLEDGE_EXTRACTION_DISPATCH_TARGET
    return owner
