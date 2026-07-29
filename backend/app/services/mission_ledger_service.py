from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective, IntentQueueResult
from app.models.db import MissionIntentRecord, WorkflowSession
from app.schemas.intent import IntentDTO, IntentEvidence, IntentNextResponse, IntentUpdateResponse


def ensure_session(db: Session, mission_id: str) -> None:
    if db.get(WorkflowSession, mission_id) is None:
        db.add(WorkflowSession(id=mission_id))
        db.commit()


def record_queue_result(
    db: Session,
    *,
    mission_id: str,
    initial_intent: IntentDispatchDirective | None,
    queue_result: IntentQueueResult | None,
) -> None:
    ensure_session(db, mission_id)
    if initial_intent is not None:
        upsert_intent(db, mission_id=mission_id, directive=initial_intent, status="DISPATCHED")
    if queue_result is None:
        return
    for execution in queue_result.executions:
        record = db.get(MissionIntentRecord, execution.intent_id)
        if record is None and initial_intent is not None and initial_intent.intent_id == execution.intent_id:
            record = upsert_intent(db, mission_id=mission_id, directive=initial_intent, status=_status_from_execution(execution.status))
        if record is not None:
            record.status = _status_from_execution(execution.status)
            record.evidence = [e.model_dump() for e in execution.evidence]
            record.updated_at = datetime.utcnow()
            if record.status in {"COMPLETED", "FAILED", "BLOCKED"}:
                record.completed_at = datetime.utcnow()
    for directive in queue_result.remaining_intents:
        upsert_intent(db, mission_id=mission_id, directive=directive, status="QUEUED")
    for evidence in queue_result.evidence:
        intent_id = str(evidence.payload.get("intent_id") or "")
        if not intent_id and initial_intent is not None:
            intent_id = initial_intent.intent_id
        record = db.get(MissionIntentRecord, intent_id) if intent_id else None
        if record is not None:
            current = list(record.evidence or [])
            current.append(evidence.model_dump())
            record.evidence = current
            record.updated_at = datetime.utcnow()
    db.commit()


def upsert_intent(
    db: Session,
    *,
    mission_id: str,
    directive: IntentDispatchDirective,
    status: str = "QUEUED",
) -> MissionIntentRecord:
    ensure_session(db, mission_id)
    directive.mission_id = directive.mission_id or mission_id
    record = db.get(MissionIntentRecord, directive.intent_id)
    now = datetime.utcnow()
    if record is None:
        record = MissionIntentRecord(
            intent_id=directive.intent_id,
            mission_id=mission_id,
            parent_intent_id=directive.parent_intent_id,
            intent=directive.intent,
            provider=directive.owner,
            capability=directive.capability,
            dispatch_target=directive.dispatch_target,
            execution_owner=directive.owner,
            status=status,
            payload=directive.payload,
            evidence=[],
            provenance={"reason": directive.reason},
            resume_metadata={},
            blueprint_id=_blueprint_ref(directive, "blueprint_id"),
            blueprint_node_id=_blueprint_ref(directive, "blueprint_node_id"),
            blueprint_revision=_blueprint_revision(directive),
            created_at=now,
            updated_at=now,
            dispatched_at=now if status in {"DISPATCHED", "WAITING_BROWSER", "WAITING_PROVIDER"} else None,
        )
        db.add(record)
    else:
        record.status = status
        record.payload = directive.payload
        record.blueprint_id = _blueprint_ref(directive, "blueprint_id")
        record.blueprint_node_id = _blueprint_ref(directive, "blueprint_node_id")
        record.blueprint_revision = _blueprint_revision(directive)
        record.updated_at = now
        if status in {"DISPATCHED", "WAITING_BROWSER", "WAITING_PROVIDER"} and record.dispatched_at is None:
            record.dispatched_at = now
    db.commit()
    db.refresh(record)
    return record


def next_intent(db: Session, *, mission_id: str, provider: str | None = None) -> IntentNextResponse:
    query = db.query(MissionIntentRecord).filter(MissionIntentRecord.mission_id == mission_id)
    if provider:
        query = query.filter(MissionIntentRecord.provider == provider)
    record = (
        query.filter(MissionIntentRecord.status.in_(["WAITING_BROWSER", "WAITING_PROVIDER", "QUEUED", "DISPATCHED", "EXECUTING"]))
        .order_by(MissionIntentRecord.created_at.asc())
        .first()
    )
    if record is None:
        return IntentNextResponse(intent=None, status="idle", reason="No executable intent is waiting.")
    if record.status == "QUEUED":
        record.status = "DISPATCHED"
    elif record.status in {"WAITING_BROWSER", "WAITING_PROVIDER", "DISPATCHED"}:
        record.status = "EXECUTING"
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    return IntentNextResponse(intent=to_dto(record), status="ready", reason="Intent assigned to provider executor.")


def update_intent(
    db: Session,
    *,
    mission_id: str,
    intent_id: str,
    outcome: str,
    evidence: IntentEvidence,
) -> IntentUpdateResponse:
    record = db.get(MissionIntentRecord, intent_id)
    if record is None or record.mission_id != mission_id:
        raise LookupError(f"Intent {intent_id} not found for mission {mission_id}")
    current = list(record.evidence or [])
    current.append(evidence.model_dump())
    record.evidence = current
    record.status = {
        "success": "COMPLETED",
        "failure": "FAILED",
        "blocked": "BLOCKED",
        "cancelled": "CANCELLED",
        "partial": "PARTIAL",
    }.get(outcome, "FAILED")
    record.completed_at = datetime.utcnow() if record.status in {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED"} else None
    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)
    _resume_backend_work(db, mission_id=mission_id, evidence=evidence)
    next_response = next_intent(db, mission_id=mission_id, provider="browser_control")
    return IntentUpdateResponse(
        updated=True,
        intent=to_dto(record),
        next_intent=next_response.intent,
        status=next_response.status if next_response.intent is not None else record.status,
        reason=next_response.reason if next_response.intent is not None else "Intent evidence attached to durable mission ledger.",
    )


def mark_waiting_provider(db: Session, *, mission_id: str, directive: IntentDispatchDirective, status: str) -> None:
    upsert_intent(db, mission_id=mission_id, directive=directive, status=status)


def to_dto(record: MissionIntentRecord) -> IntentDTO:
    return IntentDTO(
        intent_id=record.intent_id,
        mission_id=record.mission_id,
        parent_intent_id=record.parent_intent_id,
        intent=record.intent,
        provider=record.provider,
        capability=record.capability,
        status=record.status,
        payload=dict(record.payload or {}),
        evidence=list(record.evidence or []),
        blueprint_id=record.blueprint_id,
        blueprint_node_id=record.blueprint_node_id,
        blueprint_revision=record.blueprint_revision,
    )


def _resume_backend_work(db: Session, *, mission_id: str, evidence: IntentEvidence) -> None:
    context = _execution_context_from_evidence(mission_id, evidence)
    while True:
        record = _next_backend_record(db, mission_id)
        if record is None:
            return
        directive = _directive_from_record(record)
        record.status = "EXECUTING"
        record.updated_at = datetime.utcnow()
        db.commit()

        from app.intent_runtime import execute_intent_queue

        queue_result = execute_intent_queue(
            mission_id=mission_id,
            initial_intents=[directive],
            context=context,
        )
        record_queue_result(
            db,
            mission_id=mission_id,
            initial_intent=directive,
            queue_result=queue_result,
        )
        if queue_result.status in {
            "waiting_browser",
            "browser_action_required",
            "user_interaction_required",
            "waiting_external",
            "failed",
            "blocked",
            "mission_completed",
        }:
            return


def _next_backend_record(db: Session, mission_id: str) -> MissionIntentRecord | None:
    return (
        db.query(MissionIntentRecord)
        .filter(MissionIntentRecord.mission_id == mission_id)
        .filter(MissionIntentRecord.provider != "browser_control")
        .filter(MissionIntentRecord.status.in_(["QUEUED", "DISPATCHED", "EXECUTING", "WAITING_PROVIDER"]))
        .order_by(MissionIntentRecord.created_at.asc())
        .first()
    )


def _directive_from_record(record: MissionIntentRecord) -> IntentDispatchDirective:
    payload = dict(record.payload or {})
    if record.blueprint_id:
        payload.setdefault("blueprint_id", record.blueprint_id)
    if record.blueprint_node_id:
        payload.setdefault("blueprint_node_id", record.blueprint_node_id)
    if record.blueprint_revision is not None:
        payload.setdefault("blueprint_revision", record.blueprint_revision)
    return IntentDispatchDirective(
        intent_id=record.intent_id,
        mission_id=record.mission_id,
        parent_intent_id=record.parent_intent_id,
        intent=record.intent,
        owner=record.provider,
        capability=record.capability,
        dispatch_target=record.dispatch_target,
        browser_executable=record.provider == "browser_control",
        reason=str((record.provenance or {}).get("reason") or "Resumed from durable mission ledger."),
        payload=payload,
        handled=False,
    )


def _execution_context_from_evidence(mission_id: str, evidence: IntentEvidence) -> ExecutionContext:
    payload = dict(evidence.payload or {})
    return ExecutionContext(
        mission_id=mission_id,
        task=str(payload.get("task") or ""),
        page_context=payload.get("page_context"),
        prior_steps=[],
        metadata={
            "resume_source": "mission_ledger",
            "browser_metadata": dict(evidence.browser_metadata or {}),
            "provider_metadata": dict(evidence.provider_metadata or {}),
        },
    )


def _status_from_execution(status: str) -> str:
    return {
        "succeeded": "COMPLETED",
        "mission_completed": "COMPLETED",
        "waiting_browser": "WAITING_BROWSER",
        "browser_action_required": "WAITING_BROWSER",
        "user_interaction_required": "WAITING_USER",
        "waiting_external": "WAITING_EXTERNAL",
        "failed": "FAILED",
        "blocked": "BLOCKED",
    }.get(str(status), "DISPATCHED")


def _blueprint_ref(directive: IntentDispatchDirective, key: str) -> str | None:
    value = directive.payload.get(key)
    return str(value) if value else None


def _blueprint_revision(directive: IntentDispatchDirective) -> int | None:
    value = directive.payload.get("blueprint_revision")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
