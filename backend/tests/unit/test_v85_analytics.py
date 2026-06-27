"""V8.5 Governance Layer — Unit tests: analytics.py + timeline.py (24 tests)."""
import pytest
from app.governance import analytics as anal
from app.governance import timeline as tl


@pytest.fixture(autouse=True)
def clean():
    anal._reset_for_testing()
    tl._reset_for_testing()
    yield
    anal._reset_for_testing()
    tl._reset_for_testing()


class TestGovernanceAnalytics:

    def test_initial_all_zero(self):
        a = anal.get_analytics()
        for k in ["contracts_created", "contracts_consumed",
                  "contracts_revoked", "contracts_expired"]:
            assert a[k] == 0

    def test_record_created(self):
        anal.record_created()
        a = anal.get_analytics()
        assert a["contracts_created"] == 1

    def test_record_created_multiple(self):
        for _ in range(5):
            anal.record_created()
        assert anal.get_analytics()["contracts_created"] == 5

    def test_record_consumed(self):
        anal.record_consumed(age_ms=150.0)
        a = anal.get_analytics()
        assert a["contracts_consumed"] == 1

    def test_record_revoked(self):
        anal.record_revoked(age_ms=200.0)
        a = anal.get_analytics()
        assert a["contracts_revoked"] == 1

    def test_record_expired(self):
        anal.record_expired(age_ms=50.0)
        a = anal.get_analytics()
        assert a["contracts_expired"] == 1

    def test_avg_contract_age_ms(self):
        anal.record_consumed(100.0)
        anal.record_consumed(200.0)
        a = anal.get_analytics()
        assert a["avg_contract_age_ms"] == 150.0

    def test_avg_contract_age_zero_when_no_events(self):
        a = anal.get_analytics()
        assert a["avg_contract_age_ms"] == 0.0

    def test_get_analytics_has_contracts_active(self):
        a = anal.get_analytics()
        assert "contracts_active" in a

    def test_reset_clears_counts(self):
        anal.record_created()
        anal.record_created()
        anal._reset_for_testing()
        a = anal.get_analytics()
        assert a["contracts_created"] == 0


class TestGovernanceTimeline:

    def test_empty_get(self):
        assert tl.get("no-mission") == []

    def test_record_and_get(self):
        tl.record("cid-1", "created", mission_id="m-tl")
        events = tl.get("m-tl")
        assert len(events) == 1

    def test_record_event_type(self):
        tl.record("cid-2", "revoked", mission_id="m-tl2")
        events = tl.get("m-tl2")
        assert events[0]["event_type"] == "revoked"

    def test_record_multiple_newest_first(self):
        tl.record("cid-a", "created", mission_id="m-order")
        tl.record("cid-b", "consumed", mission_id="m-order")
        events = tl.get("m-order")
        assert events[0]["event_type"] == "consumed"

    def test_recent_global(self):
        tl.record("cid-g", "created")
        g = tl.recent_global()
        assert len(g) >= 1

    def test_summary_returns_dict(self):
        tl.record("cid-s", "created", mission_id="m-sum")
        s = tl.summary("m-sum")
        assert "event_count" in s and "type_counts" in s

    def test_summary_event_count(self):
        tl.record("cid-s1", "created",  mission_id="m-sum2")
        tl.record("cid-s2", "revoked",  mission_id="m-sum2")
        s = tl.summary("m-sum2")
        assert s["event_count"] == 2

    def test_summary_has_latest_event(self):
        tl.record("cid-s3", "consumed", mission_id="m-sum3")
        s = tl.summary("m-sum3")
        assert s["latest_event"] is not None

    def test_missions_with_contracts(self):
        tl.record("cid-mwc", "created", mission_id="m-mwc")
        missions = tl.missions_with_contracts()
        assert "m-mwc" in missions

    def test_reset_clears(self):
        tl.record("cid-r", "created", mission_id="m-reset")
        tl._reset_for_testing()
        assert tl.get("m-reset") == []

    def test_event_has_timestamp(self):
        tl.record("cid-ts", "created", mission_id="m-ts")
        events = tl.get("m-ts")
        assert "timestamp" in events[0]

    def test_approved_field_stored(self):
        tl.record("cid-ap", "created", mission_id="m-ap", approved=True)
        events = tl.get("m-ap")
        assert events[0]["approved"] is True

    def test_limit_observed(self):
        for i in range(10):
            tl.record(f"cid-{i}", "created", mission_id="m-lim")
        events = tl.get("m-lim", limit=3)
        assert len(events) == 3
