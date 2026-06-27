"""V9.0 Execution Planning Layer — Unit tests: timeline.py."""
import pytest
from app.execution_planning import timeline as tl
from app.execution_planning.timeline import VALID_EVENTS


@pytest.fixture(autouse=True)
def clean():
    tl._reset_for_testing()
    yield
    tl._reset_for_testing()


class TestRecord:
    def test_record_and_get(self):
        tl.record("plan-1", "created", mission_id="m-1")
        assert len(tl.get("m-1")) == 1

    def test_event_type_stored(self):
        tl.record("plan-1", "validated", mission_id="m-1")
        assert tl.get("m-1")[0]["event_type"] == "validated"

    def test_newest_first(self):
        tl.record("plan-1", "created", mission_id="m-1")
        tl.record("plan-1", "ready", mission_id="m-1")
        assert tl.get("m-1")[0]["event_type"] == "ready"

    def test_all_event_types(self):
        for et in ["created", "validated", "ready", "cancelled", "superseded", "archived"]:
            tl.record("plan-1", et, mission_id="m-ev")
        types = {e["event_type"] for e in tl.get("m-ev")}
        for et in ["created", "validated", "ready", "cancelled", "superseded", "archived"]:
            assert et in types

    def test_valid_events_constant(self):
        assert len(VALID_EVENTS) == 6

    def test_event_fields(self):
        tl.record("plan-1", "created", mission_id="m-1",
                  authorization_id="auth-1", status="DRAFT")
        e = tl.get("m-1")[0]
        for k in ["plan_id", "event_type", "mission_id", "authorization_id", "status", "timestamp"]:
            assert k in e


class TestQueries:
    def test_recent_global(self):
        tl.record("plan-1", "created", mission_id="m-1")
        assert len(tl.recent_global()) >= 1

    def test_get_empty(self):
        assert tl.get("absent") == []

    def test_limit(self):
        for i in range(5):
            tl.record(f"plan-{i}", "created", mission_id="m-lim")
        assert len(tl.get("m-lim", limit=2)) == 2

    def test_summary(self):
        tl.record("plan-1", "created", mission_id="m-s")
        tl.record("plan-1", "validated", mission_id="m-s")
        s = tl.summary("m-s")
        assert s["event_count"] == 2
        assert "type_counts" in s
        assert s["latest_event"] is not None

    def test_missions_with_plans(self):
        tl.record("plan-1", "created", mission_id="m-mwp")
        assert "m-mwp" in tl.missions_with_plans()


class TestReset:
    def test_reset_clears(self):
        tl.record("plan-1", "created", mission_id="m-1")
        tl._reset_for_testing()
        assert tl.get("m-1") == []
