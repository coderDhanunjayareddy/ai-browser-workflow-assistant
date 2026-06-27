"""V8.8 Execution Authorization Framework — Unit tests: analytics.py + timeline.py (26 tests)."""
import pytest
from app.authorization import analytics as anal
from app.authorization import timeline as tl


@pytest.fixture(autouse=True)
def clean():
    anal._reset_for_testing()
    tl._reset_for_testing()
    yield
    anal._reset_for_testing()
    tl._reset_for_testing()


class TestAuthorizationAnalytics:

    def test_initial_zeros(self):
        a = anal.get_analytics()
        for k in ["authorizations_created", "authorized", "denied",
                  "expired", "revoked", "consumed"]:
            assert a[k] == 0

    def test_initial_avg_zero(self):
        assert anal.get_analytics()["avg_evaluation_time_ms"] == 0.0

    def test_record_created_authorized(self):
        anal.record_created(True, eval_ms=0.5)
        a = anal.get_analytics()
        assert a["authorizations_created"] == 1
        assert a["authorized"] == 1
        assert a["denied"] == 0

    def test_record_created_denied(self):
        anal.record_created(False, eval_ms=0.3)
        a = anal.get_analytics()
        assert a["authorizations_created"] == 1
        assert a["denied"] == 1
        assert a["authorized"] == 0

    def test_avg_eval_time(self):
        anal.record_created(True, eval_ms=1.0)
        anal.record_created(True, eval_ms=3.0)
        a = anal.get_analytics()
        assert a["avg_evaluation_time_ms"] == 2.0

    def test_record_expired(self):
        anal.record_expired()
        assert anal.get_analytics()["expired"] == 1

    def test_record_revoked(self):
        anal.record_revoked()
        assert anal.get_analytics()["revoked"] == 1

    def test_record_consumed(self):
        anal.record_consumed()
        assert anal.get_analytics()["consumed"] == 1

    def test_reset_clears(self):
        anal.record_created(True, eval_ms=1.0)
        anal._reset_for_testing()
        a = anal.get_analytics()
        assert a["authorizations_created"] == 0
        assert a["avg_evaluation_time_ms"] == 0.0

    def test_multiple_events(self):
        for _ in range(5): anal.record_created(True)
        for _ in range(3): anal.record_created(False)
        a = anal.get_analytics()
        assert a["authorizations_created"] == 8
        assert a["authorized"] == 5
        assert a["denied"] == 3


class TestAuthorizationTimeline:

    def test_empty_get(self):
        assert tl.get("no-mission") == []

    def test_record_and_get(self):
        tl.record("auth-1", "created", mission_id="m-tl")
        events = tl.get("m-tl")
        assert len(events) == 1

    def test_event_type_stored(self):
        tl.record("auth-2", "denied", mission_id="m-tl2")
        events = tl.get("m-tl2")
        assert events[0]["event_type"] == "denied"

    def test_event_types_coverage(self):
        for et in ["created", "approved", "denied", "expired", "revoked", "consumed"]:
            tl.record(f"auth-{et}", et, mission_id="m-all")
        events = tl.get("m-all")
        types = {e["event_type"] for e in events}
        for et in ["created", "approved", "denied", "expired", "revoked", "consumed"]:
            assert et in types

    def test_newest_first(self):
        tl.record("auth-old", "created", mission_id="m-ord")
        tl.record("auth-new", "approved", mission_id="m-ord")
        events = tl.get("m-ord")
        assert events[0]["event_type"] == "approved"

    def test_recent_global(self):
        tl.record("auth-g", "created")
        assert len(tl.recent_global()) >= 1

    def test_summary(self):
        tl.record("auth-s1", "created",  mission_id="m-sum")
        tl.record("auth-s2", "approved", mission_id="m-sum")
        s = tl.summary("m-sum")
        assert s["event_count"] == 2
        assert "type_counts" in s

    def test_summary_latest_event(self):
        tl.record("auth-lt", "consumed", mission_id="m-lt")
        s = tl.summary("m-lt")
        assert s["latest_event"] is not None

    def test_missions_with_authorizations(self):
        tl.record("auth-mwa", "created", mission_id="m-mwa")
        assert "m-mwa" in tl.missions_with_authorizations()

    def test_limit_observed(self):
        for i in range(10): tl.record(f"auth-{i}", "created", mission_id="m-lim")
        events = tl.get("m-lim", limit=3)
        assert len(events) == 3

    def test_has_timestamp(self):
        tl.record("auth-ts", "created", mission_id="m-ts")
        events = tl.get("m-ts")
        assert "timestamp" in events[0]

    def test_authorized_field(self):
        tl.record("auth-ap", "approved", mission_id="m-ap", authorized=True)
        events = tl.get("m-ap")
        assert events[0]["authorized"] is True

    def test_contract_id_field(self):
        tl.record("auth-ct", "created", mission_id="m-ct", contract_id="ctr-1")
        events = tl.get("m-ct")
        assert events[0]["contract_id"] == "ctr-1"

    def test_reset_clears(self):
        tl.record("auth-r", "created", mission_id="m-rst")
        tl._reset_for_testing()
        assert tl.get("m-rst") == []
