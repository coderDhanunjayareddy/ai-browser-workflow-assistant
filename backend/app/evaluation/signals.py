from __future__ import annotations

from app.contracts.ledger_events import LedgerEvent
from app.evaluation.models import EvaluationObject, KnowledgeRecord, LearningSignal


def generate_learning_signals(
    *, evaluation: EvaluationObject, events: list[LedgerEvent]
) -> list[LearningSignal]:
    signals: list[LearningSignal] = []
    validation_summary = evaluation.validation_summary
    governance_summary = evaluation.governance_summary
    execution_metrics = evaluation.execution_metrics

    if evaluation.mission_summary.get("completed"):
        signals.append(
            LearningSignal(
                run_id=evaluation.run_id,
                evaluation_id=evaluation.evaluation_id,
                mission_id=evaluation.mission_id,
                kind="mission_success",
                summary="Mission reached a verified completion condition.",
                evidence_refs=_event_ids(events, {"report.verified", "run.completed"}),
                confidence=evaluation.confidence,
            )
        )

    if int(validation_summary.get("not_satisfied") or 0) > 0:
        signals.append(
            LearningSignal(
                run_id=evaluation.run_id,
                evaluation_id=evaluation.evaluation_id,
                mission_id=evaluation.mission_id,
                kind="validation_failure",
                summary="Validation rejected at least one observed outcome.",
                evidence_refs=_event_ids(events, {"validation.completed"}),
                confidence=float(validation_summary.get("average_confidence") or 0.5),
                metadata={"failure_categories": validation_summary.get("failure_categories", {})},
            )
        )

    if execution_metrics.failed_actions > 0:
        signals.append(
            LearningSignal(
                run_id=evaluation.run_id,
                evaluation_id=evaluation.evaluation_id,
                mission_id=evaluation.mission_id,
                kind="repeated_failure" if execution_metrics.failed_actions > 1 else "common_recovery_path",
                summary="Execution failures were observed during the mission.",
                evidence_refs=_event_ids(events, {"execution.completed"}),
                confidence=0.7,
                metadata={"failed_actions": execution_metrics.failed_actions},
            )
        )

    governance_decisions = governance_summary.get("decisions") or {}
    if any(str(decision) in governance_decisions for decision in {"warn", "allow_with_confirmation", "block"}):
        signals.append(
            LearningSignal(
                run_id=evaluation.run_id,
                evaluation_id=evaluation.evaluation_id,
                mission_id=evaluation.mission_id,
                kind="policy_warning",
                summary="Governance observed a policy warning or restriction.",
                evidence_refs=_event_ids(events, {"governance.evaluated"}),
                confidence=0.8,
                metadata={"decisions": governance_decisions},
            )
        )

    return signals[:20]


def record_knowledge(
    *, evaluation: EvaluationObject, events: list[LedgerEvent]
) -> list[KnowledgeRecord]:
    facts = {
        "planner_turns": evaluation.execution_metrics.planner_turns,
        "browser_actions": evaluation.execution_metrics.browser_actions,
        "successful_actions": evaluation.execution_metrics.successful_actions,
        "failed_actions": evaluation.execution_metrics.failed_actions,
        "overall_score": evaluation.overall_score,
    }
    provenance = [event.event_id for event in events[-10:]]
    return [
        KnowledgeRecord(
            run_id=evaluation.run_id,
            evaluation_id=evaluation.evaluation_id,
            mission_id=evaluation.mission_id,
            category="mission_statistics",
            summary="Deterministic mission score and execution statistics.",
            facts=facts,
            confidence=evaluation.confidence,
            provenance=provenance,
        )
    ]


def _event_ids(events: list[LedgerEvent], event_types: set[str]) -> list[str]:
    return [event.event_id for event in events if event.event_type in event_types][-10:]
