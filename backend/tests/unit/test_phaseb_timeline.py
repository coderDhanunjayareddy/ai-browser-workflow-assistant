"""Phase B Execution Gateway — Unit tests: timeline.py."""
import pytest
from app.execution_gateway import timeline as tl
from app.execution_gateway.timeline import VALID_EVENTS


@pytest.fixture(autouse=True)
def clean():
    tl._reset_for_testing()
    yield
    tl._reset_for_testing()


class TestRecord:
    def test_record_and_get(self):
        tl.record("exec-1", "started", mission_id="m-1")
        assert len(tl.get("m-1")) == 1

    def test_event_type(self):
        tl.record("exec-1", "completed", mission_id="m-1")
        assert tl.get("m-1")[0]["event_type"] == "completed"

    def test_newest_first(self):
        tl.record("exec-1", "started", mission_id="m-1")
        tl.record("exec-1", "completed", mission_id="m-1")
        assert tl.get("m-1")[0]["event_type"] == "completed"

    def test_all_event_types(self):
        for et in ["started", "completed", "failed", "paused", "resumed", "aborted", "rolled_back"]:
            tl.record("exec-1", et, mission_id="m-ev")
        types = {e["event_type"] for e in tl.get("m-ev")}
        for et in ["started", "completed", "failed", "paused", "resumed", "aborted", "rolled_back"]:
            assert et in types

    def test_seven_valid_events(self):
        assert len(VALID_EVENTS) == 7

    def test_event_fields(self):
        tl.record("exec-1", "started", mission_id="m-1", plan_id="plan-1", state="RUNNING")
        e = tl.get("m-1")[0]
        for k in ["execution_id", "event_type", "mission_id", "plan_id", "state", "timestamp"]:
            assert k in e


class TestQueries:
    def test_recent_global(self):
        tl.record("exec-1", "started", mission_id="m-1")
        assert len(tl.recent_global()) >= 1

    def test_get_empty(self):
        assert tl.get("absent") == []

    def test_summary(self):
        tl.record("exec-1", "started", mission_id="m-s")
        tl.record("exec-1", "completed", mission_id="m-s")
        s = tl.summary("m-s")
        assert s["event_count"] == 2
        assert s["latest_event"] is not None

    def test_missions_with_executions(self):
        tl.record("exec-1", "started", mission_id="m-mwe")
        assert "m-mwe" in tl.missions_with_executions()

    def test_reset(self):
        tl.record("exec-1", "started", mission_id="m-1")
        tl._reset_for_testing()
        assert tl.get("m-1") == []
