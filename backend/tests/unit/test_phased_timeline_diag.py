"""Phase D — Unit tests: exec_timeline.py + diagnostics.py."""
import pytest
from app.execution_gateway.browser import exec_timeline as etl
from app.execution_gateway.browser import diagnostics as diag
from app.execution_gateway.browser import monitor as mon
from app.execution_gateway.browser import metrics as met
from app.execution_gateway.browser.exec_timeline import VALID_EVENTS


@pytest.fixture(autouse=True)
def clean():
    etl._reset_for_testing(); mon._reset_for_testing(); met._reset_for_testing()
    yield
    etl._reset_for_testing(); mon._reset_for_testing(); met._reset_for_testing()


class TestTimeline:
    def test_record_and_query(self):
        etl.record("e1", "s1", "planned", order=1)
        etl.record("e1", "s1", "started", order=1)
        assert len(etl.events_for("e1")) == 2

    def test_chronological(self):
        etl.record("e1", "s1", "planned", order=1)
        etl.record("e1", "s1", "completed", order=1)
        events = etl.events_for("e1")
        assert events[0]["event_type"] == "planned"
        assert events[1]["event_type"] == "completed"

    def test_all_event_types_valid(self):
        for et in ["planned", "started", "retried", "recovered", "validated",
                   "completed", "failed", "rollback"]:
            assert et in VALID_EVENTS
        assert len(VALID_EVENTS) == 8

    def test_events_for_step(self):
        etl.record("e1", "s1", "started", order=1)
        etl.record("e1", "s2", "started", order=2)
        assert len(etl.events_for_step("e1", "s1")) == 1

    def test_summary(self):
        etl.record("e1", "s1", "planned")
        etl.record("e1", "s1", "started")
        etl.record("e1", "s1", "completed")
        s = etl.summary("e1")
        assert s["event_count"] == 3
        assert s["type_counts"]["planned"] == 1

    def test_empty(self):
        assert etl.events_for("absent") == []
        assert etl.summary("absent")["event_count"] == 0

    def test_detail_recorded(self):
        etl.record("e1", "s1", "recovered", detail={"actions": ["WAIT"]})
        assert etl.events_for("e1")[0]["detail"]["actions"] == ["WAIT"]

    def test_reset(self):
        etl.record("e1", "s1", "started")
        etl._reset_for_testing()
        assert etl.events_for("e1") == []


class TestDiagnostics:
    def test_keys(self):
        # seed a monitor record so diagnostics has data
        rec = mon.start_step("e-diag", "s1", 1, "click", 0.0)
        mon.finish_step(rec, finished_at=0.1, attempts=2, outcome="completed",
                        validation_result=True, locator_strategy="testid", recovery_used=["WAIT"])
        d = diag.diagnostics("e-diag")
        for k in ["execution_id", "page_url", "title", "active_frame", "active_tab",
                  "locator_strategy_used", "recovery_history", "validation_history",
                  "retry_history", "last_screenshot", "monitor_summary", "timeline_summary",
                  "metrics"]:
            assert k in d

    def test_active_frame_main(self):
        mon.start_step("e-diag2", "s1", 1, "click", 0.0)
        assert diag.diagnostics("e-diag2")["active_frame"] == "main"

    def test_recovery_history(self):
        rec = mon.start_step("e-diag3", "s1", 1, "click", 0.0)
        mon.finish_step(rec, finished_at=0.1, attempts=2, outcome="completed",
                        recovery_used=["WAIT", "REFRESH_LOCATOR"])
        d = diag.diagnostics("e-diag3")
        assert len(d["recovery_history"]) == 1
        assert d["recovery_history"][0]["recovery_used"] == ["WAIT", "REFRESH_LOCATOR"]

    def test_validation_history(self):
        rec = mon.start_step("e-diag4", "s1", 1, "validate", 0.0)
        mon.finish_step(rec, finished_at=0.1, attempts=1, outcome="completed", validation_result=True)
        d = diag.diagnostics("e-diag4")
        assert len(d["validation_history"]) == 1
        assert d["validation_history"][0]["validation_result"] is True

    def test_retry_history(self):
        rec = mon.start_step("e-diag5", "s1", 1, "click", 0.0)
        mon.finish_step(rec, finished_at=0.1, attempts=3, outcome="completed")
        d = diag.diagnostics("e-diag5")
        assert len(d["retry_history"]) == 1
        assert d["retry_history"][0]["retries"] == 2

    def test_locator_strategy_used(self):
        rec = mon.start_step("e-diag6", "s1", 1, "click", 0.0)
        mon.finish_step(rec, finished_at=0.1, attempts=1, outcome="completed", locator_strategy="testid")
        assert diag.diagnostics("e-diag6")["locator_strategy_used"] == "testid"

    def test_no_image_bytes(self):
        rec = mon.start_step("e-diag7", "s1", 1, "click", 0.0)
        mon.finish_step(rec, finished_at=0.1, attempts=1, outcome="completed")
        d = diag.diagnostics("e-diag7")
        # last_screenshot is metadata-only (path/filename) or None — never bytes
        assert d["last_screenshot"] is None or isinstance(d["last_screenshot"], dict)
