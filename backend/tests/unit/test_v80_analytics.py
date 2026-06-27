"""
V8.0 Unit Tests — ApprovalAnalytics + ApprovalTimeline (22 tests).
"""
import pytest

from app.approvals import analytics as anal
from app.approvals import timeline as tl


@pytest.fixture(autouse=True)
def reset():
    anal._reset_for_testing()
    tl._reset_for_testing()
    yield
    anal._reset_for_testing()
    tl._reset_for_testing()


class TestApprovalAnalytics:
    def test_initial_all_zero(self):
        a = anal.get_analytics()
        assert a["created"]   == 0
        assert a["approved"]  == 0
        assert a["rejected"]  == 0
        assert a["expired"]   == 0
        assert a["cancelled"] == 0

    def test_record_created_critical(self):
        anal.record_created("CRITICAL")
        a = anal.get_analytics()
        assert a["created"]  == 1
        assert a["critical"] == 1

    def test_record_created_high(self):
        anal.record_created("HIGH")
        assert anal.get_analytics()["high"] == 1

    def test_record_created_medium(self):
        anal.record_created("MEDIUM")
        assert anal.get_analytics()["medium"] == 1

    def test_record_created_low(self):
        anal.record_created("LOW")
        assert anal.get_analytics()["low"] == 1

    def test_record_approved_increments(self):
        anal.record_approved(100.0)
        assert anal.get_analytics()["approved"] == 1

    def test_record_rejected_increments(self):
        anal.record_rejected(200.0)
        assert anal.get_analytics()["rejected"] == 1

    def test_record_expired_increments(self):
        anal.record_expired()
        assert anal.get_analytics()["expired"] == 1

    def test_record_cancelled_increments(self):
        anal.record_cancelled()
        assert anal.get_analytics()["cancelled"] == 1

    def test_avg_approval_ms_single(self):
        anal.record_approved(500.0)
        assert anal.get_analytics()["avg_approval_ms"] == 500.0

    def test_avg_approval_ms_multiple(self):
        anal.record_approved(200.0)
        anal.record_rejected(400.0)
        assert anal.get_analytics()["avg_approval_ms"] == 300.0

    def test_avg_approval_ms_zero_when_none(self):
        assert anal.get_analytics()["avg_approval_ms"] == 0.0

    def test_reset_clears_all(self):
        anal.record_created("HIGH")
        anal.record_approved(100.0)
        anal._reset_for_testing()
        a = anal.get_analytics()
        assert a["created"]  == 0
        assert a["approved"] == 0


class TestApprovalTimeline:
    def test_record_stores_event(self):
        tl.record("a1", "created", mission_id="m1", risk_level="HIGH", title="T", source="s")
        events = tl.get("m1")
        assert len(events) == 1

    def test_newest_first(self):
        tl.record("a1", "created",  mission_id="m1")
        tl.record("a2", "approved", mission_id="m1")
        events = tl.get("m1")
        assert events[0]["approval_id"] == "a2"

    def test_event_has_required_keys(self):
        tl.record("a1", "created", mission_id="m1")
        e = tl.get("m1")[0]
        for key in ("approval_id", "event_type", "mission_id", "risk_level", "timestamp"):
            assert key in e

    def test_global_stream(self):
        tl.record("a1", "created", mission_id="m1")
        tl.record("a2", "created", mission_id="m2")
        recent = tl.recent_global(limit=10)
        assert len(recent) >= 2

    def test_summary_event_count(self):
        tl.record("a1", "created",  mission_id="m-sum")
        tl.record("a1", "approved", mission_id="m-sum")
        s = tl.summary("m-sum")
        assert s["event_count"] == 2

    def test_summary_type_counts(self):
        tl.record("a1", "created",  mission_id="m-tc")
        tl.record("a2", "rejected", mission_id="m-tc")
        s = tl.summary("m-tc")
        assert s["type_counts"].get("created",  0) == 1
        assert s["type_counts"].get("rejected", 0) == 1

    def test_summary_latest_event(self):
        tl.record("a1", "created",  mission_id="m-le")
        tl.record("a2", "approved", mission_id="m-le")
        s = tl.summary("m-le")
        assert s["latest_event"] is not None

    def test_missions_with_approvals(self):
        tl.record("a1", "created", mission_id="m-with")
        missions = tl.missions_with_approvals()
        assert "m-with" in missions

    def test_reset_clears(self):
        tl.record("a1", "created", mission_id="m1")
        tl._reset_for_testing()
        assert tl.get("m1") == []
