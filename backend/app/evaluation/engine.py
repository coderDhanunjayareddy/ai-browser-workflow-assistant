from __future__ import annotations

import time

from app.contracts.base import utc_now
from app.contracts.ledger_events import LedgerEvent
from app.evaluation.models import EvaluationArtifacts, EvaluationObject
from app.evaluation.scoring import (
    calculate_execution_metrics,
    score_dimensions,
    summarize_governance,
    summarize_mission,
    summarize_validation,
)
from app.evaluation.scorecards import build_scorecard
from app.evaluation.signals import generate_learning_signals, record_knowledge
from app.evaluation.telemetry import record_evaluation_metrics
from app.run_ledger.replay import replay_events


class EvaluationEngine:
    """Deterministic V3.6 evaluation pipeline.

    The engine consumes completed run evidence and produces evaluation
    artifacts. It never mutates planner output, workflow state, browser
    execution, governance, or validation.
    """

    def evaluate_run(
        self,
        *,
        run_id: str,
        mission_id: str | None = None,
        events: list[LedgerEvent],
    ) -> EvaluationArtifacts:
        started = time.perf_counter()
        replayed = replay_events(_without_evaluation_events(events))
        validation_summary = summarize_validation(replayed)
        governance_summary = summarize_governance(replayed)
        mission_summary = summarize_mission(replayed)
        execution_metrics = calculate_execution_metrics(replayed)
        scoring_started = time.perf_counter()
        dimensions = score_dimensions(
            validation_summary=validation_summary,
            governance_summary=governance_summary,
            mission_summary=mission_summary,
            execution_metrics=execution_metrics,
            events=replayed,
        )
        scoring_ms = int((time.perf_counter() - scoring_started) * 1000)
        overall = dimensions.overall()
        confidence = _confidence(
            event_count=len(replayed),
            validation_summary=validation_summary,
            governance_summary=governance_summary,
        )
        evaluation = EvaluationObject(
            run_id=run_id,
            mission_id=mission_id or run_id,
            validation_summary=validation_summary,
            governance_summary=governance_summary,
            mission_summary=mission_summary,
            execution_metrics=execution_metrics,
            score_dimensions=dimensions,
            overall_score=overall,
            confidence=confidence,
            timestamp=utc_now().isoformat(),
            replay_metadata={
                "event_count": len(replayed),
                "first_event_id": replayed[0].event_id if replayed else None,
                "last_event_id": replayed[-1].event_id if replayed else None,
                "scoring_ms": scoring_ms,
            },
        )
        scorecard = build_scorecard(evaluation)
        signals = generate_learning_signals(evaluation=evaluation, events=replayed)
        knowledge = record_knowledge(evaluation=evaluation, events=replayed)
        latency_ms = int((time.perf_counter() - started) * 1000)
        record_evaluation_metrics(
            run_id,
            evaluation=evaluation,
            scorecard=scorecard,
            learning_signal_count=len(signals),
            latency_ms=latency_ms,
            scoring_ms=scoring_ms,
        )
        return EvaluationArtifacts(
            evaluation=evaluation,
            scorecard=scorecard,
            learning_signals=signals,
            knowledge_records=knowledge,
            latency_ms=latency_ms,
        )


def _without_evaluation_events(events: list[LedgerEvent]) -> list[LedgerEvent]:
    return [
        event
        for event in events
        if event.event_type
        not in {"evaluation.completed", "learning.signal_recorded", "knowledge.recorded"}
    ]


def _confidence(
    *,
    event_count: int,
    validation_summary: dict[str, object],
    governance_summary: dict[str, object],
) -> float:
    if event_count == 0:
        return 0.0
    confidence = 0.5
    if int(validation_summary.get("total") or 0) > 0:
        confidence += 0.25
    if int(governance_summary.get("total") or 0) > 0:
        confidence += 0.15
    if event_count >= 3:
        confidence += 0.1
    return round(min(confidence, 1.0), 4)

