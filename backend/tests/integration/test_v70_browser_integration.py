"""
V7.0 Integration Tests — Live Browser Sync Layer REST API (35 tests).
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.browser import analytics as bra
import app.browser.registry as ev_reg
from app.browser import timeline as tl
from app.tabs import registry as tab_reg
import app.mission.store as ms
from app.mission.models import Mission
from app.trust import analytics as trust_analytics
import app.trust.registry as trust_reg

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset():
    bra._reset_for_testing()
    ev_reg._reset_for_testing()
    tl._reset_for_testing()
    tab_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()
    yield
    bra._reset_for_testing()
    ev_reg._reset_for_testing()
    tl._reset_for_testing()
    tab_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()


def _make_mission(title="Test Mission") -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title=title, objective="test")
    ms.put(m)
    return m.mission_id


def _event_body(et="TAB_CREATED", tab_id="t-test", mission_id=None, **kw):
    body = {"event_type": et, "tab_id": tab_id, **kw}
    if mission_id:
        body["mission_id"] = mission_id
    return body


# ── POST /browser/events ──────────────────────────────────────────────────────

class TestIngestEvent:
    def test_tab_created_200(self):
        r = client.post("/browser/events", json=_event_body("TAB_CREATED", url="https://a.com"))
        assert r.status_code == 200

    def test_returns_sync_result(self):
        r = client.post("/browser/events", json=_event_body("TAB_CREATED"))
        body = r.json()
        assert "success"    in body
        assert "event_id"   in body
        assert "event_type" in body
        assert body["success"] is True

    def test_page_loaded_triggers_refresh_flag(self):
        r = client.post("/browser/events", json=_event_body("PAGE_LOADED", url="https://final.com"))
        assert r.json()["triggers_refresh"] is True

    def test_window_focused_no_refresh(self):
        r = client.post("/browser/events", json=_event_body("WINDOW_FOCUSED"))
        assert r.json()["triggers_refresh"] is False

    def test_analytics_incremented(self):
        client.post("/browser/events", json=_event_body("TAB_CREATED"))
        r = client.get("/browser/analytics")
        assert r.json()["events_received"] >= 1
        assert r.json()["tab_created"]     >= 1

    def test_tab_registered_in_registry(self):
        client.post("/browser/events", json=_event_body("TAB_CREATED", tab_id="t-reg",
                                                         url="https://new.com"))
        tab = tab_reg.get("t-reg")
        assert tab is not None
        assert tab.url == "https://new.com"

    def test_missing_required_field_422(self):
        r = client.post("/browser/events", json={"event_type": "TAB_CREATED"})
        assert r.status_code == 422

    def test_event_stored_in_registry(self):
        r = client.post("/browser/events", json=_event_body("URL_CHANGED", url="https://b.com"))
        event_id = r.json()["event_id"]
        ev = ev_reg.get(event_id)
        assert ev is not None
        assert ev.url == "https://b.com"

    def test_timeline_updated_with_mission(self):
        mid = _make_mission()
        client.post("/browser/events", json=_event_body("PAGE_LOADED", mission_id=mid))
        events = tl.get(mid)
        assert len(events) >= 1


# ── POST /browser/sync ────────────────────────────────────────────────────────

class TestSyncEvent:
    def test_sync_200(self):
        mid = _make_mission()
        r = client.post("/browser/sync", json=_event_body("PAGE_LOADED", mission_id=mid))
        assert r.status_code == 200

    def test_sync_triggers_refreshes(self):
        mid = _make_mission()
        r = client.post("/browser/sync", json=_event_body("TAB_CREATED",
                                                           mission_id=mid,
                                                           url="https://x.com"))
        body = r.json()
        assert body["success"] is True
        assert body["triggers_refresh"] is True

    def test_sync_includes_mission_refresh(self):
        mid = _make_mission()
        r = client.post("/browser/sync", json=_event_body("PAGE_LOADED", mission_id=mid))
        body = r.json()
        assert "mission_refresh" in body

    def test_sync_includes_trust_refresh(self):
        mid = _make_mission()
        r = client.post("/browser/sync", json=_event_body("TAB_CREATED", mission_id=mid))
        body = r.json()
        assert "trust_refresh" in body

    def test_sync_includes_recommendations(self):
        mid = _make_mission()
        r = client.post("/browser/sync", json=_event_body("TAB_CLOSED", mission_id=mid))
        body = r.json()
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)

    def test_analytics_mission_refresh_counted(self):
        mid = _make_mission()
        from app.browser.mission_refresh import _reset_for_testing
        _reset_for_testing()
        client.post("/browser/sync", json=_event_body("TAB_CREATED", mission_id=mid))
        r = client.get("/browser/analytics")
        assert r.json()["mission_refreshes"] >= 1

    def test_window_blur_no_mission_refresh(self):
        mid = _make_mission()
        client.post("/browser/sync", json=_event_body("WINDOW_BLURRED", mission_id=mid))
        r = client.get("/browser/analytics")
        assert r.json()["mission_refreshes"] == 0


# ── GET /browser/events ───────────────────────────────────────────────────────

class TestListEvents:
    def test_list_all_200(self):
        client.post("/browser/events", json=_event_body("TAB_CREATED"))
        r = client.get("/browser/events")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_filter_by_mission(self):
        mid = _make_mission()
        client.post("/browser/events", json=_event_body("TAB_CREATED", mission_id=mid))
        client.post("/browser/events", json=_event_body("TAB_CREATED", tab_id="t-other"))
        r = client.get(f"/browser/events?mission_id={mid}")
        assert r.status_code == 200
        events = r.json()
        assert all(e["mission_id"] == mid for e in events)

    def test_filter_by_tab(self):
        client.post("/browser/events", json=_event_body("TAB_CREATED", tab_id="t-specific"))
        r = client.get("/browser/events?tab_id=t-specific")
        assert r.status_code == 200
        events = r.json()
        assert all(e["tab_id"] == "t-specific" for e in events)

    def test_limit_respected(self):
        for i in range(10):
            client.post("/browser/events", json=_event_body("TAB_CREATED", tab_id=f"t{i}"))
        r = client.get("/browser/events?limit=3")
        assert len(r.json()) <= 3

    def test_empty_when_no_events(self):
        r = client.get("/browser/events?mission_id=nonexistent")
        assert r.json() == []


# ── GET /browser/events/{id} ──────────────────────────────────────────────────

class TestGetSingleEvent:
    def test_get_existing_event(self):
        r = client.post("/browser/events", json=_event_body("URL_CHANGED",
                                                              url="https://detail.com"))
        event_id = r.json()["event_id"]
        r2 = client.get(f"/browser/events/{event_id}")
        assert r2.status_code == 200
        assert r2.json()["event_id"] == event_id

    def test_get_unknown_event_404(self):
        r = client.get("/browser/events/nonexistent-event-xyz")
        assert r.status_code == 404


# ── GET /browser/analytics ────────────────────────────────────────────────────

class TestBrowserAnalytics:
    def test_analytics_200(self):
        r = client.get("/browser/analytics")
        assert r.status_code == 200

    def test_analytics_has_all_fields(self):
        r = client.get("/browser/analytics")
        body = r.json()
        for field in ("events_received", "tab_created", "tab_closed", "url_changed",
                      "mission_refreshes", "trust_refreshes", "recommendation_refreshes"):
            assert field in body

    def test_counters_accumulate(self):
        client.post("/browser/events", json=_event_body("TAB_CREATED", tab_id="a"))
        client.post("/browser/events", json=_event_body("TAB_CREATED", tab_id="b"))
        r = client.get("/browser/analytics")
        assert r.json()["events_received"] >= 2
        assert r.json()["tab_created"]     >= 2


# ── GET /browser/inspect/{mission_id} ─────────────────────────────────────────

class TestBrowserInspect:
    def test_inspect_existing_mission_200(self):
        mid = _make_mission()
        r = client.get(f"/browser/inspect/{mid}")
        assert r.status_code == 200

    def test_inspect_has_expected_keys(self):
        mid = _make_mission()
        r = client.get(f"/browser/inspect/{mid}")
        body = r.json()
        for key in ("mission_id", "recent_events", "tab_context",
                    "trust", "intelligence", "recommendations", "timeline"):
            assert key in body

    def test_inspect_unknown_404(self):
        r = client.get("/browser/inspect/nonexistent-xyz")
        assert r.status_code == 404

    def test_inspect_after_event(self):
        mid = _make_mission()
        client.post("/browser/events", json=_event_body("TAB_CREATED", mission_id=mid))
        r = client.get(f"/browser/inspect/{mid}")
        body = r.json()
        assert len(body["recent_events"]) >= 1


# ── GET /browser/timeline/{mission_id} ───────────────────────────────────────

class TestBrowserTimeline:
    def test_timeline_200(self):
        mid = _make_mission()
        r = client.get(f"/browser/timeline/{mid}")
        assert r.status_code == 200

    def test_timeline_has_fields(self):
        mid = _make_mission()
        r = client.get(f"/browser/timeline/{mid}")
        body = r.json()
        assert "mission_id"  in body
        assert "event_count" in body
        assert "events"      in body

    def test_timeline_after_events(self):
        mid = _make_mission()
        client.post("/browser/events", json=_event_body("TAB_CREATED", mission_id=mid))
        client.post("/browser/events", json=_event_body("URL_CHANGED", mission_id=mid))
        r = client.get(f"/browser/timeline/{mid}")
        body = r.json()
        assert body["event_count"] >= 2
        assert len(body["events"])  >= 2

    def test_timeline_type_counts(self):
        mid = _make_mission()
        client.post("/browser/events", json=_event_body("TAB_CREATED", mission_id=mid))
        client.post("/browser/events", json=_event_body("TAB_CREATED",
                                                         tab_id="t2", mission_id=mid))
        r = client.get(f"/browser/timeline/{mid}")
        body = r.json()
        assert body["type_counts"].get("TAB_CREATED", 0) >= 2
