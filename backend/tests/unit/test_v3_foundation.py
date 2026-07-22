from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.capability_platform import default_registry
from app.contracts.ledger_events import LedgerEvent
from app.cost_controller import CostBudget, CostMeter
from app.cost_controller.policy import evaluate_budget
from app.feature_flags import FeatureFlagState, get_flag_state, is_active, is_shadow_or_active
from app.models.db import RunLedgerEventRecord
from app.observability.tracing import TraceEvent, record_trace_event
from app.run_ledger import RunLedgerReader, RunLedgerWriter
from app.run_ledger.projections import planner_trace_projection, prior_steps_projection
from app.run_ledger.replay import replay_events
from app.scheduler import InMemorySchedulerQueue, ScheduledWorkItem


def test_v3_feature_flag_defaults_and_overrides(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_run_ledger", "shadow")
    monkeypatch.setattr(settings, "v3_scheduler", "active")
    monkeypatch.setattr(settings, "v3_trace_parity", "not-a-state")

    assert get_flag_state("V3_RUN_LEDGER") == FeatureFlagState.SHADOW
    assert is_shadow_or_active("V3_RUN_LEDGER") is True
    assert is_active("V3_SCHEDULER") is True
    assert get_flag_state("V3_TRACE_PARITY") == FeatureFlagState.OFF


def test_versioned_contract_serializes_required_fields():
    event = LedgerEvent(run_id="run-1", event_type="planner.responded", payload={"outcome_kind": "act"})

    payload = event.model_dump()

    assert payload["schema_version"] == "run_ledger.event.v1"
    assert payload["producer"] == "backend.v3"
    assert payload["run_id"] == "run-1"
    assert payload["created_at"] is not None


def test_run_ledger_writer_reader_replay_and_projections(sqlite_session_factory, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_run_ledger", "shadow")
    with sqlite_session_factory() as db:
        db.query(RunLedgerEventRecord).delete()
        db.commit()

        writer = RunLedgerWriter(db, strict=True)
        second = writer.append(
            run_id="run-ledger-test",
            event_type="execution.completed",
            payload={"summary": "clicked button"},
            step_index=2,
        )
        first = writer.append(
            run_id="run-ledger-test",
            event_type="planner.responded",
            payload={"outcome_kind": "act"},
            step_index=1,
        )

        assert first is not None
        assert second is not None

        events = RunLedgerReader(db).list_events("run-ledger-test")
        replayed = replay_events(events)

        assert [event.step_index for event in replayed] == [1, 2]
        assert prior_steps_projection(replayed)[0]["event_type"] == "planner.responded"
        assert planner_trace_projection(replayed)[0]["payload"]["outcome_kind"] == "act"


def test_run_ledger_off_does_not_write(sqlite_session_factory, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_run_ledger", "off")
    with sqlite_session_factory() as db:
        db.query(RunLedgerEventRecord).delete()
        db.commit()

        event = RunLedgerWriter(db, strict=True).append(
            run_id="run-off",
            event_type="planner.responded",
        )

        assert event is None
        assert db.query(RunLedgerEventRecord).count() == 0


def test_capability_platform_shadow_manifest_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_capability_platform", "shadow")
    manifest = default_registry("run-cap").compact_manifest()

    assert any(item["id"] == "browser.click" for item in manifest)
    assert any(item["id"] == "browser.open_new_tab" for item in manifest)

    monkeypatch.setattr(settings, "v3_capability_platform", "off")
    assert default_registry("run-cap").compact_manifest() == []


def test_scheduler_is_inactive_until_flag_active(monkeypatch):
    from app.core.config import settings

    queue = InMemorySchedulerQueue()
    due_time = datetime.now(timezone.utc) - timedelta(seconds=1)
    item = ScheduledWorkItem(run_id="run-scheduler", kind="wait", earliest_start_at=due_time)
    queue.enqueue(item)

    monkeypatch.setattr(settings, "v3_scheduler", "off")
    assert queue.due_items() == []

    monkeypatch.setattr(settings, "v3_scheduler", "active")
    assert queue.due_items()[0].id == item.id


def test_cost_controller_tracks_usage_and_remains_advisory():
    meter = CostMeter()
    usage = meter.record("run-cost", tokens=90, latency_ms=10)
    budget = CostBudget(run_id="run-cost", max_tokens=100, max_latency_ms=1000)

    decision = evaluate_budget("run-cost", budget, usage)

    assert decision.status == "near_limit"
    assert decision.hard_stop is False


def test_trace_parity_writes_only_when_active(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "trace_dir", str(tmp_path))
    monkeypatch.setattr(settings, "v3_trace_parity", "off")
    event = TraceEvent(run_id="run-trace", event_type="planner.responded")
    record_trace_event(event)

    assert not (tmp_path / "v3" / "run-trace.jsonl").exists()

    monkeypatch.setattr(settings, "v3_trace_parity", "active")
    record_trace_event(event)

    assert (tmp_path / "v3" / "run-trace.jsonl").exists()
