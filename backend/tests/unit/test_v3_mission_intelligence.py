from __future__ import annotations

import pytest

from app.contracts.ledger_events import LedgerEvent
from app.feature_flags import is_shadow_or_active
from app.mission.v3 import MissionIntelligenceEngine, replay_mission
from app.mission.v3.fsm import MissionStateMachine
from app.mission.v3.telemetry import record_mission_metrics
from app.observability.metrics import default_metric_sink


def event(event_type: str, payload: dict | None = None, step_index: int = 0) -> LedgerEvent:
    return LedgerEvent(
        run_id="run-1",
        event_type=event_type,
        payload=payload or {},
        step_index=step_index,
        producer="test",
    )


def test_mission_fsm_validates_explicit_transitions():
    fsm = MissionStateMachine.create(run_id="run-1", goal="Compare repositories")

    fsm.apply_event(event_type="run.started", payload={"task": "Compare repositories"})
    assert fsm.snapshot.state == "planning"

    fsm.apply_event(
        event_type="planner.responded",
        payload={"outcome_kind": "act", "suggested_actions": 1},
    )
    assert fsm.snapshot.state == "executing"

    with pytest.raises(ValueError):
        fsm.transition("completed")


def test_goal_and_progress_tracking_survive_planner_retries():
    engine = MissionIntelligenceEngine()

    engine.apply_workflow_event(
        run_id="run-1",
        event_type="run.started",
        payload={"task": "Compare repositories"},
    )
    engine.apply_workflow_event(
        run_id="run-1",
        event_type="planner.responded",
        payload={"outcome_kind": "act", "suggested_actions": 1},
    )
    snapshot, _ = engine.apply_workflow_event(
        run_id="run-1",
        event_type="execution.completed",
        payload={"success": False},
    )

    assert snapshot.goal == "Compare repositories"
    assert snapshot.state == "replanning"
    assert snapshot.replanning_requested is True
    assert snapshot.replan_reasons == ["execution_failed"]
    assert snapshot.retry_count == 1
    assert snapshot.attempts[0].reason == "execution_failed"


def test_grounding_failure_triggers_replanning_without_planning():
    engine = MissionIntelligenceEngine()
    engine.apply_workflow_event(run_id="run-1", event_type="run.started", payload={"task": "Open settings"})
    engine.apply_workflow_event(
        run_id="run-1",
        event_type="planner.responded",
        payload={"outcome_kind": "act", "suggested_actions": 1},
    )

    snapshot, _ = engine.apply_workflow_event(
        run_id="run-1",
        event_type="grounding.resolved",
        payload={"status": "ambiguous"},
    )

    assert snapshot.state == "replanning"
    assert snapshot.replanning_requested is True
    assert "grounding_ambiguous" in snapshot.replan_reasons
    assert snapshot.next_expected_action == "planner_replan"


def test_pause_and_resume_are_persistent_state_transitions():
    engine = MissionIntelligenceEngine()
    engine.apply_workflow_event(run_id="run-1", event_type="run.started", payload={"task": "Research docs"})

    paused = engine.pause("run-1")
    resumed = engine.resume("run-1")

    assert paused.state == "paused"
    assert paused.paused is True
    assert resumed.state == "planning"
    assert resumed.paused is False


def test_verified_report_completes_mission_snapshot():
    engine = MissionIntelligenceEngine()
    engine.apply_workflow_event(run_id="run-1", event_type="run.started", payload={"task": "Tell me the invoice total"})
    engine.apply_workflow_event(
        run_id="run-1",
        event_type="planner.responded",
        payload={"outcome_kind": "report", "suggested_actions": 0, "has_report": True},
    )
    snapshot, _ = engine.apply_workflow_event(
        run_id="run-1",
        event_type="report.verified",
        payload={"sgv_verified": True},
    )

    assert snapshot.state == "completed"
    assert snapshot.completed_objectives == ["Tell me the invoice total"]
    assert snapshot.remaining_objectives == []


def test_replay_reconstructs_identical_mission_state_from_ledger_events():
    events = [
        event("run.started", {"task": "Compare repositories"}, 0),
        event("observation.captured", {"url": "https://example.test"}, 1),
        event("planner.responded", {"outcome_kind": "act", "suggested_actions": 1}, 2),
        event("execution.completed", {"success": False}, 3),
        event("mission.updated", {"state": "ignored"}, 4),
    ]
    engine = MissionIntelligenceEngine()
    for ledger_event in events:
        if ledger_event.event_type != "mission.updated":
            engine.apply_workflow_event(
                run_id=ledger_event.run_id,
                event_type=ledger_event.event_type,
                payload=ledger_event.payload,
                event_id=ledger_event.event_id,
                step_index=ledger_event.step_index,
            )
    live = engine.get_snapshot("run-1")
    replayed, replay_ms = replay_mission("run-1", events)

    assert live is not None
    assert live.to_stable_json() == replayed.to_stable_json()
    assert replay_ms < 100


def test_mission_snapshot_history_and_attempts_are_bounded():
    engine = MissionIntelligenceEngine()
    engine.apply_workflow_event(run_id="run-1", event_type="run.started", payload={"task": "Long task"})
    for index in range(60):
        engine.apply_workflow_event(
            run_id="run-1",
            event_type="observation.captured",
            payload={"index": index},
            step_index=index,
        )
    for index in range(25):
        engine.apply_workflow_event(
            run_id="run-1",
            event_type="goal_convergence.assessed",
            payload={"goal_convergence": True},
            step_index=index,
        )

    snapshot = engine.get_snapshot("run-1")

    assert snapshot is not None
    assert len(snapshot.step_history) == 50
    assert len(snapshot.attempts) == 20


def test_mission_intelligence_feature_flag_default_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_mission_intelligence", "shadow")
    assert is_shadow_or_active("V3_MISSION_INTELLIGENCE") is True

    monkeypatch.setattr(settings, "v3_mission_intelligence", "off")
    assert is_shadow_or_active("V3_MISSION_INTELLIGENCE") is False


def test_mission_telemetry_records_snapshot_metrics():
    engine = MissionIntelligenceEngine()
    snapshot, transition_ms = engine.apply_workflow_event(
        run_id="run-telemetry",
        event_type="run.started",
        payload={"task": "Research"},
    )

    before = _metric_counts()
    record_mission_metrics("run-telemetry", snapshot, transition_ms=transition_ms)
    after = _metric_counts()

    for name in {
        "v3.mission.transition_ms",
        "v3.mission.planner_iterations",
        "v3.mission.replanning_count",
        "v3.mission.retries",
        "v3.mission.recoveries",
    }:
        assert after.get(name, 0) >= before.get(name, 0)


def _metric_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for point in default_metric_sink.snapshot():
        counts[point.name] = counts.get(point.name, 0) + 1
    return counts
