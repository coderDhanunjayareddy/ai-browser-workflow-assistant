from __future__ import annotations

import re
from typing import Any

from app.mission_completion.models import (
    CriterionEvaluation,
    CriterionKind,
    EvidenceReference,
    ExecutionBudgetPlan,
    MissionPlan,
    MissionSuccessCriterion,
    ObjectiveType,
    ValidationStatus,
)


DEFAULT_FIELD_NAMES = ["tool", "purpose", "pricing", "limitation", "url"]


def build_mission_plan(
    *,
    mission_id: str,
    objective: str,
    phase_state: Any = None,
) -> MissionPlan:
    objective_type = infer_objective_type(objective)
    phases = _ordered_phases(objective_type, phase_state)
    return MissionPlan(
        schema_version="mission_plan.v1",
        mission_id=mission_id,
        objective=objective,
        objective_type=objective_type,
        ordered_phases=phases,
        constraints=[],
        execution_budgets=_execution_budgets(phase_state),
        success_criteria=build_success_criteria(objective=objective, objective_type=objective_type),
        recovery_rules=[
            "replan_on_ambiguity",
            "replan_on_validation_failure",
            "ask_user_when_approval_or_required_input_is_missing",
            "pause_when_external_confirmation_is_pending",
        ],
        termination_rules=[
            "mission_completion_is_the_only_completion_authority",
            "complete_only_when_all_blocking_success_criteria_are_satisfied",
            "do_not_complete_from_report_existence_phase_completion_or_planner_output_alone",
        ],
        approval_policy={
            "require_user_approval_for": [
                "purchase",
                "booking",
                "submission",
                "account_creation",
                "file_upload",
                "external_message",
            ]
        },
    )


def infer_objective_type(objective: str) -> ObjectiveType:
    text = str(objective or "").lower()
    if _has(text, "upload", "attach file", "submit file"):
        return ObjectiveType.UPLOAD
    if _has(text, "download", "export", "save file"):
        return ObjectiveType.DOWNLOAD
    if _has(text, "apply for", "job application", "resume", "cover letter"):
        return ObjectiveType.JOB_APPLICATION
    if _has(text, "sign up", "signup", "create account", "register account"):
        return ObjectiveType.ACCOUNT_CREATION
    if _has(text, "onboard", "setup workspace", "set up workspace"):
        return ObjectiveType.SAAS_ONBOARDING
    if _has(text, "buy", "purchase", "cart", "checkout"):
        return ObjectiveType.SHOPPING
    if _has(text, "book flight", "book hotel", "reservation", "travel"):
        return ObjectiveType.TRAVEL_BOOKING
    if _has(text, "docs", "documentation", "api reference", "extract docs"):
        return ObjectiveType.DOCUMENTATION_EXTRACTION
    if _has(text, "form", "fill"):
        return ObjectiveType.FORM_WORKFLOW
    if _has(text, "dashboard", "admin", "settings"):
        return ObjectiveType.DASHBOARD
    if _has(text, "wait for", "confirmation email", "external confirmation"):
        return ObjectiveType.ASYNC_WORKFLOW
    if _has(text, "research", "compare", "summarize", "report", "top ", "best "):
        return ObjectiveType.RESEARCH
    return ObjectiveType.GENERAL


def build_success_criteria(*, objective: str, objective_type: ObjectiveType) -> list[MissionSuccessCriterion]:
    fields = _requested_fields(objective)
    criteria: list[MissionSuccessCriterion] = []

    def add(kind: CriterionKind, subject: str, **kwargs: Any) -> None:
        criteria.append(
            MissionSuccessCriterion(
                criterion_id=f"{kind.value}:{subject}",
                kind=kind,
                subject=subject,
                **kwargs,
            )
        )

    if objective_type in {
        ObjectiveType.RESEARCH,
        ObjectiveType.DOCUMENTATION_EXTRACTION,
        ObjectiveType.GENERAL,
    }:
        add(CriterionKind.PAGE_READ, "source_pages", validation_policy=ValidationStatus.RAW)
        add(CriterionKind.FIELD_EXTRACTED, "required_fields", required_evidence=fields)
        add(CriterionKind.ARTIFACT_CREATED, "knowledge_artifact")
        add(CriterionKind.ARTIFACT_VALIDATED, "extraction_records")
        add(CriterionKind.REPORT_DELIVERED, "user_visible_report", user_visible=True)
        return criteria

    if objective_type in {ObjectiveType.ACCOUNT_CREATION, ObjectiveType.SAAS_ONBOARDING, ObjectiveType.FORM_WORKFLOW}:
        add(CriterionKind.BROWSER_STATE_REACHED, "target_form", validation_policy=ValidationStatus.RAW)
        add(CriterionKind.FORM_COMPLETED, "required_form_fields")
        add(CriterionKind.SUBMISSION_CONFIRMED, "confirmation")
        return criteria

    if objective_type in {ObjectiveType.SHOPPING, ObjectiveType.TRAVEL_BOOKING, ObjectiveType.JOB_APPLICATION}:
        add(CriterionKind.BROWSER_STATE_REACHED, "target_flow", validation_policy=ValidationStatus.RAW)
        add(CriterionKind.FORM_COMPLETED, "required_flow_fields")
        add(CriterionKind.APPROVAL_OBTAINED, "irreversible_submit_or_purchase")
        add(CriterionKind.SUBMISSION_CONFIRMED, "confirmation")
        return criteria

    if objective_type == ObjectiveType.UPLOAD:
        add(CriterionKind.FILE_UPLOADED, "required_file")
        add(CriterionKind.SUBMISSION_CONFIRMED, "upload_confirmation")
        return criteria

    if objective_type == ObjectiveType.DOWNLOAD:
        add(CriterionKind.FILE_DOWNLOADED, "required_file")
        add(CriterionKind.ARTIFACT_VALIDATED, "download_artifact")
        return criteria

    if objective_type == ObjectiveType.DASHBOARD:
        add(CriterionKind.BROWSER_STATE_REACHED, "target_dashboard_state", validation_policy=ValidationStatus.RAW)
        add(CriterionKind.RUNTIME_BINDING_EXISTS, "active_dashboard_resource", validation_policy=ValidationStatus.RAW)
        return criteria

    if objective_type == ObjectiveType.ASYNC_WORKFLOW:
        add(CriterionKind.EXTERNAL_CONFIRMATION_RECEIVED, "external_system")
        return criteria

    add(CriterionKind.BROWSER_STATE_REACHED, "objective_state", validation_policy=ValidationStatus.RAW)
    return criteria


def evaluate_success_criteria(
    *,
    mission_plan: MissionPlan,
    knowledge_snapshot: Any = None,
    runtime_state: Any = None,
    phase_state: Any = None,
) -> list[CriterionEvaluation]:
    return [
        _evaluate_criterion(
            criterion,
            knowledge_snapshot=knowledge_snapshot,
            runtime_state=runtime_state,
            phase_state=phase_state,
        )
        for criterion in mission_plan.success_criteria
    ]


def _evaluate_criterion(
    criterion: MissionSuccessCriterion,
    *,
    knowledge_snapshot: Any,
    runtime_state: Any,
    phase_state: Any,
) -> CriterionEvaluation:
    refs: list[EvidenceReference] = []
    missing: list[str] = []
    confidence = 0.0
    validation = ValidationStatus.MISSING

    if criterion.kind == CriterionKind.PAGE_READ:
        reads = list(getattr(knowledge_snapshot, "read_artifacts", []) or [])
        refs = [_ref("knowledge_extraction", read.id, "page_read", getattr(read, "timestamp_ms", None), ValidationStatus.RAW) for read in reads]
        satisfied = len(refs) >= criterion.cardinality
        missing = [] if satisfied else ["page_read_artifact"]
        confidence = 0.85 if satisfied else 0.0
        validation = ValidationStatus.RAW if satisfied else ValidationStatus.MISSING
    elif criterion.kind == CriterionKind.FIELD_EXTRACTED:
        valid_records = _valid_records(knowledge_snapshot)
        available_fields = {field.lower() for record in valid_records for field, value in record.fields.items() if str(value or "").strip()}
        required_fields = [field.lower() for field in (criterion.required_evidence or DEFAULT_FIELD_NAMES)]
        missing = [field for field in required_fields if field not in available_fields]
        refs = [_ref("knowledge_extraction", record.id, "extraction_record", getattr(record, "timestamp_ms", None), ValidationStatus.VALIDATED) for record in valid_records]
        satisfied = not missing and bool(refs)
        confidence = _average([float(record.confidence) for record in valid_records]) if satisfied else 0.0
        validation = ValidationStatus.VALIDATED if satisfied else ValidationStatus.MISSING
    elif criterion.kind == CriterionKind.ARTIFACT_CREATED:
        artifact = getattr(knowledge_snapshot, "knowledge_artifact", None)
        refs = [_ref("knowledge_extraction", artifact.id, "knowledge_artifact", getattr(artifact, "timestamp_ms", None), ValidationStatus.VALIDATED)] if artifact else []
        satisfied = bool(refs)
        missing = [] if satisfied else ["knowledge_artifact"]
        confidence = 0.9 if satisfied else 0.0
        validation = ValidationStatus.VALIDATED if satisfied else ValidationStatus.MISSING
    elif criterion.kind == CriterionKind.ARTIFACT_VALIDATED:
        valid_records = _valid_records(knowledge_snapshot)
        artifact = getattr(knowledge_snapshot, "knowledge_artifact", None)
        if artifact is not None:
            refs.append(_ref("knowledge_extraction", artifact.id, "knowledge_artifact", getattr(artifact, "timestamp_ms", None), ValidationStatus.VALIDATED))
        refs.extend(_ref("knowledge_extraction", record.id, "validated_record", getattr(record, "timestamp_ms", None), ValidationStatus.VALIDATED) for record in valid_records)
        satisfied = bool(refs) and bool(valid_records)
        missing = [] if satisfied else ["validated_artifact_evidence"]
        confidence = 0.9 if satisfied else 0.0
        validation = ValidationStatus.VALIDATED if satisfied else ValidationStatus.MISSING
    elif criterion.kind == CriterionKind.REPORT_DELIVERED:
        report = getattr(knowledge_snapshot, "report_artifact", None)
        complete = bool(report and getattr(report, "completion_status", "") == "complete")
        refs = [_ref("knowledge_extraction", report.id, "report_artifact", getattr(report, "timestamp_ms", None), ValidationStatus.VALIDATED)] if report else []
        satisfied = complete
        missing = [] if satisfied else ["report_artifact"]
        confidence = 0.95 if satisfied else 0.0
        validation = ValidationStatus.VALIDATED if satisfied else ValidationStatus.MISSING
    elif criterion.kind == CriterionKind.RUNTIME_BINDING_EXISTS:
        resources = list(getattr(runtime_state, "logical_resources", []) or [])
        refs = [_ref("runtime_state_manager", getattr(resource, "logical_id", str(index)), "runtime_resource", None, ValidationStatus.RAW) for index, resource in enumerate(resources)]
        satisfied = bool(refs)
        missing = [] if satisfied else ["runtime_binding"]
        confidence = 0.8 if satisfied else 0.0
        validation = ValidationStatus.RAW if satisfied else ValidationStatus.MISSING
    elif criterion.kind == CriterionKind.BROWSER_STATE_REACHED:
        active_phase = getattr(phase_state, "active_phase", None)
        page_url = getattr(runtime_state, "focused_tab_id", None)
        if active_phase is not None:
            refs.append(_ref("execution_orchestrator", getattr(active_phase, "name", "phase"), "phase_state", None, ValidationStatus.RAW))
        if page_url:
            refs.append(_ref("runtime_state_manager", str(page_url), "focused_tab", None, ValidationStatus.RAW))
        satisfied = bool(refs)
        missing = [] if satisfied else ["browser_state"]
        confidence = 0.7 if satisfied else 0.0
        validation = ValidationStatus.RAW if satisfied else ValidationStatus.MISSING
    else:
        missing = [criterion.kind.value]
        satisfied = False

    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        kind=criterion.kind,
        satisfied=satisfied,
        missing_evidence=missing,
        blocking_reason=None if satisfied or not criterion.blocking else f"Missing evidence: {', '.join(missing)}",
        supporting_evidence=refs,
        confidence=confidence,
        freshness="fresh" if refs else "unknown",
        validation_status=validation,
    )


def _ordered_phases(objective_type: ObjectiveType, phase_state: Any) -> list[str]:
    phases = [getattr(phase, "name", "") for phase in list(getattr(phase_state, "phases", []) or [])]
    phases = [str(phase) for phase in phases if phase]
    if phases:
        return phases
    if objective_type in {ObjectiveType.RESEARCH, ObjectiveType.DOCUMENTATION_EXTRACTION, ObjectiveType.GENERAL}:
        return ["DISCOVER", "OPEN", "READ", "EXTRACT", "SYNTHESIZE", "REPORT"]
    if objective_type == ObjectiveType.UPLOAD:
        return ["DISCOVER", "OPEN", "FILL", "UPLOAD", "VERIFY"]
    if objective_type == ObjectiveType.DOWNLOAD:
        return ["DISCOVER", "OPEN", "DOWNLOAD", "VERIFY"]
    if objective_type == ObjectiveType.ASYNC_WORKFLOW:
        return ["DISCOVER", "OPEN", "WAIT_EXTERNAL", "VERIFY"]
    return ["DISCOVER", "OPEN", "READ", "VERIFY"]


def _execution_budgets(phase_state: Any) -> ExecutionBudgetPlan:
    budgets = getattr(phase_state, "budgets", None)
    if budgets is None:
        return ExecutionBudgetPlan()
    return ExecutionBudgetPlan(
        max_tabs=getattr(budgets, "max_tabs", 12),
        max_pages=getattr(budgets, "max_pages", 30),
        max_results=getattr(budgets, "max_results", 10),
        max_extractions=getattr(budgets, "max_extractions", 50),
        max_planner_turns=getattr(budgets, "max_planner_turns", 40),
        max_retries=getattr(budgets, "max_retries", 3),
        max_tokens=getattr(budgets, "max_tokens", 120000),
        max_runtime_seconds=getattr(budgets, "max_runtime_seconds", 900),
    )


def _requested_fields(objective: str) -> list[str]:
    text = str(objective or "")
    if re.search(r"\b(tool|purpose|pricing|limitation|url)\b", text, re.IGNORECASE):
        fields = [field for field in DEFAULT_FIELD_NAMES if re.search(rf"\b{re.escape(field)}\b", text, re.IGNORECASE)]
        return fields or DEFAULT_FIELD_NAMES
    return DEFAULT_FIELD_NAMES


def _valid_records(snapshot: Any) -> list[Any]:
    return [
        record
        for record in list(getattr(snapshot, "extraction_records", []) or [])
        if bool(getattr(record, "validation", {}).get("valid"))
    ]


def _ref(source: str, evidence_id: str, evidence_type: str, timestamp_ms: int | None, validation: ValidationStatus) -> EvidenceReference:
    return EvidenceReference(
        source=source,
        evidence_id=str(evidence_id),
        evidence_type=evidence_type,
        timestamp_ms=timestamp_ms,
        validation_status=validation,
    )


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _has(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)
