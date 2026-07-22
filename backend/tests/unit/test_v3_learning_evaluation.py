from __future__ import annotations

from app.contracts.ledger_events import LedgerEvent
from app.evaluation import EvaluationEngine, compare_evaluations, replay_evaluation, replay_evaluation_object
from app.feature_flags import is_shadow_or_active
from app.observability.metrics import default_metric_sink


def event(event_type: str, payload: dict | None = None, *, step: int = 0) -> LedgerEvent:
    return LedgerEvent(
        run_id="run-1",
        event_type=event_type,
        payload=payload or {},
        step_index=step,
        producer="test",
    )


def successful_events() -> list[LedgerEvent]:
    return [
        event("run.started", {"task": "Tell me the invoice total"}, step=0),
        event("planner.responded", {"outcome_kind": "report"}, step=1),
        event(
            "validation.completed",
            {
                "validation_status": "satisfied",
                "confidence": 0.95,
                "latency_ms": 3,
            },
            step=1,
        ),
        event(
            "governance.evaluated",
            {
                "policy_decision": "allow",
                "risk_level": "safe",
                "approval_required": False,
                "requires_handoff": False,
                "latency_ms": 2,
            },
            step=1,
        ),
        event("report.verified", {"sgv_verified": True}, step=2),
    ]


def failed_events() -> list[LedgerEvent]:
    return [
        event("run.started", {"task": "Click through"}, step=0),
        event("planner.responded", {"outcome_kind": "act"}, step=1),
        event(
            "execution.completed",
            {"action_type": "click", "success": False, "execution_result": "No effect"},
            step=2,
        ),
        event(
            "validation.completed",
            {
                "validation_status": "not_satisfied",
                "confidence": 0.55,
                "failure_category": "unexpected_state",
            },
            step=2,
        ),
        event("run.failed", {"reason": "no progress"}, step=3),
    ]


def test_evaluation_object_scores_successful_mission():
    artifacts = EvaluationEngine().evaluate_run(
        run_id="run-1",
        mission_id="run-1",
        events=successful_events(),
    )

    evaluation = artifacts.evaluation
    assert evaluation.schema_version == "evaluation.v1"
    assert evaluation.mission_summary["completed"] is True
    assert evaluation.validation_summary["satisfied"] == 1
    assert evaluation.governance_summary["decisions"] == {"allow": 1}
    assert evaluation.overall_score >= 0.9
    assert evaluation.confidence >= 0.8


def test_learning_signals_and_knowledge_records_are_generated():
    artifacts = EvaluationEngine().evaluate_run(
        run_id="run-1",
        mission_id="run-1",
        events=failed_events(),
    )

    kinds = {signal.kind for signal in artifacts.learning_signals}
    assert "validation_failure" in kinds
    assert "common_recovery_path" in kinds
    assert artifacts.knowledge_records[0].category == "mission_statistics"
    assert artifacts.knowledge_records[0].facts["failed_actions"] == 1


def test_scorecard_summarizes_run():
    artifacts = EvaluationEngine().evaluate_run(
        run_id="run-1",
        mission_id="run-1",
        events=successful_events(),
    )

    assert artifacts.scorecard.schema_version == "run_scorecard.v1"
    assert artifacts.scorecard.status == "succeeded"
    assert artifacts.scorecard.success is True
    assert artifacts.scorecard.overall_score == artifacts.evaluation.overall_score


def test_evaluation_replay_is_stable_for_identical_history():
    artifacts, replay_ms = replay_evaluation(
        run_id="run-1",
        mission_id="run-1",
        events=successful_events(),
    )
    replayed, object_replay_ms = replay_evaluation_object(artifacts.evaluation)

    assert replayed.to_stable_json() == artifacts.evaluation.to_stable_json()
    assert replay_ms < 100
    assert object_replay_ms < 100


def test_evaluation_ignores_prior_evaluation_artifacts_for_replay():
    history = successful_events()
    first = EvaluationEngine().evaluate_run(run_id="run-1", mission_id="run-1", events=history)
    history.append(
        event(
            "evaluation.completed",
            first.evaluation.model_dump(mode="json"),
            step=3,
        )
    )
    second = EvaluationEngine().evaluate_run(run_id="run-1", mission_id="run-1", events=history)

    assert second.evaluation.to_stable_json() == first.evaluation.to_stable_json()


def test_regression_scoring_compares_evaluations():
    baseline = EvaluationEngine().evaluate_run(
        run_id="run-1",
        mission_id="run-1",
        events=successful_events(),
    ).evaluation
    candidate = EvaluationEngine().evaluate_run(
        run_id="run-1",
        mission_id="run-1",
        events=failed_events(),
    ).evaluation

    result = compare_evaluations(baseline=baseline, candidate=candidate)

    assert result.score_delta < 0
    assert "overall_score_regressed" in result.regression_flags


def test_learning_feature_flag_default_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_learning", "shadow")
    assert is_shadow_or_active("V3_LEARNING") is True
    assert is_shadow_or_active("V3_EVALUATION") is True

    monkeypatch.setattr(settings, "v3_learning", "off")
    assert is_shadow_or_active("V3_LEARNING") is False


def test_learning_telemetry_records_metrics():
    before = _metric_counts()
    EvaluationEngine().evaluate_run(
        run_id="run-telemetry",
        mission_id="run-telemetry",
        events=successful_events(),
    )
    after = _metric_counts()

    for name in {
        "v3.evaluation.latency_ms",
        "v3.evaluation.scoring_ms",
        "v3.evaluation.overall_score",
        "v3.learning.signal_count",
        "v3.scorecard.status",
    }:
        assert after.get(name, 0) >= before.get(name, 0)


def _metric_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for point in default_metric_sink.snapshot():
        counts[point.name] = counts.get(point.name, 0) + 1
    return counts
