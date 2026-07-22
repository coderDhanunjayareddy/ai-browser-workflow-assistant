from __future__ import annotations

import time

from app.contracts.ledger_events import LedgerEvent
from app.evaluation.engine import EvaluationEngine
from app.evaluation.models import EvaluationArtifacts, EvaluationObject


def replay_evaluation(
    *,
    run_id: str,
    mission_id: str | None = None,
    events: list[LedgerEvent],
) -> tuple[EvaluationArtifacts, int]:
    started = time.perf_counter()
    artifacts = EvaluationEngine().evaluate_run(
        run_id=run_id,
        mission_id=mission_id,
        events=events,
    )
    replay_ms = int((time.perf_counter() - started) * 1000)
    return artifacts, replay_ms


def replay_evaluation_object(evaluation: EvaluationObject) -> tuple[EvaluationObject, int]:
    started = time.perf_counter()
    replayed = EvaluationObject.model_validate(evaluation.model_dump(mode="json"))
    replay_ms = int((time.perf_counter() - started) * 1000)
    return replayed, replay_ms

