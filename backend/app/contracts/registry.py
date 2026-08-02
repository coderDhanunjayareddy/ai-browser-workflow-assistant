from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.intent_dispatcher.models import IntentDispatchDirective, IntentExecutionEvidence, IntentQueueResult
from app.knowledge_extraction.models import KnowledgeArtifact, PageReadArtifact, ReportArtifact
from app.mission.blueprint.models import BlueprintNode
from app.mission_result.models import MissionResult
from app.schemas.intent import IntentDTO, IntentEvidence, IntentUpdateResponse
from app.schemas.request import PageContext
from app.schemas.response import AnalyzeResponse


@dataclass(frozen=True)
class ContractDescriptor:
    name: str
    version: str
    target: Any
    owner: str


CONTRACTS: list[ContractDescriptor] = [
    ContractDescriptor("mission_blueprint.node", "mission_blueprint.node.v1", BlueprintNode, "Mission Blueprint"),
    ContractDescriptor("mission_ledger.intent_dto", "mission_ledger.intent_dto.v1", IntentDTO, "Mission Ledger"),
    ContractDescriptor("intent_runtime.directive", "intent_runtime.directive.v1", IntentDispatchDirective, "Intent Runtime"),
    ContractDescriptor("intent_runtime.queue_result", "intent_runtime.queue_result.v1", IntentQueueResult, "Intent Runtime"),
    ContractDescriptor("browser_runtime.page_context", "browser_runtime.page_context.v1", PageContext, "Browser Runtime"),
    ContractDescriptor("knowledge_extraction.read_artifact", "knowledge_extraction.read_artifact.v1", PageReadArtifact, "Knowledge Extraction"),
    ContractDescriptor("knowledge_extraction.knowledge_artifact", "knowledge_extraction.knowledge_artifact.v1", KnowledgeArtifact, "Knowledge Extraction"),
    ContractDescriptor("knowledge_extraction.report_artifact", "knowledge_extraction.report_artifact.v1", ReportArtifact, "Knowledge Extraction"),
    ContractDescriptor("mission_result.result", "mission_result.result.v1", MissionResult, "Mission Result"),
    ContractDescriptor("extension_api.analyze_response", "extension_api.analyze_response.v1", AnalyzeResponse, "Extension API"),
    ContractDescriptor("extension_api.intent_evidence", "extension_api.intent_evidence.v1", IntentEvidence, "Extension API"),
    ContractDescriptor("extension_api.intent_update_response", "extension_api.intent_update_response.v1", IntentUpdateResponse, "Extension API"),
    ContractDescriptor("provider_registry.execution_evidence", "provider_registry.execution_evidence.v1", IntentExecutionEvidence, "Provider Registry"),
]


def schema_for(target: Any) -> dict[str, Any]:
    if isinstance(target, type) and issubclass(target, BaseModel):
        return target.model_json_schema()
    annotations = getattr(target, "__annotations__", {})
    return {
        "title": getattr(target, "__name__", str(target)),
        "type": "dataclass",
        "fields": {name: str(value) for name, value in annotations.items()},
    }


def schema_hash(schema: dict[str, Any]) -> str:
    payload = json.dumps(schema, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
