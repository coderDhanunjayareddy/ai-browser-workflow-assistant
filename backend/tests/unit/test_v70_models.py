"""
V7.0 Unit Tests — Browser Event Models + Decision Signals (22 tests).
"""
import pytest
from datetime import datetime

from app.browser.models import (
    BrowserEvent, BrowserEventType, REFRESH_TRIGGER_TYPES,
    DecisionSignal, DecisionSignalType, BrowserEventPayload,
    make_event, make_signal,
)


class TestBrowserEventType:
    def test_eight_values(self):
        assert len(BrowserEventType) == 8

    def test_value_strings(self):
        assert BrowserEventType.tab_created.value    == "TAB_CREATED"
        assert BrowserEventType.tab_closed.value     == "TAB_CLOSED"
        assert BrowserEventType.url_changed.value    == "URL_CHANGED"
        assert BrowserEventType.page_loaded.value    == "PAGE_LOADED"
        assert BrowserEventType.window_focused.value == "WINDOW_FOCUSED"

    def test_str_enum(self):
        assert BrowserEventType.tab_created == "TAB_CREATED"

    def test_refresh_triggers(self):
        assert BrowserEventType.tab_created   in REFRESH_TRIGGER_TYPES
        assert BrowserEventType.tab_closed    in REFRESH_TRIGGER_TYPES
        assert BrowserEventType.url_changed   in REFRESH_TRIGGER_TYPES
        assert BrowserEventType.page_loaded   in REFRESH_TRIGGER_TYPES
        assert BrowserEventType.tab_activated not in REFRESH_TRIGGER_TYPES
        assert BrowserEventType.tab_updated   not in REFRESH_TRIGGER_TYPES
        assert BrowserEventType.window_focused not in REFRESH_TRIGGER_TYPES


class TestMakeEvent:
    def test_creates_event(self):
        ev = make_event(BrowserEventType.tab_created, "t1", url="https://x.com")
        assert isinstance(ev, BrowserEvent)
        assert ev.event_type == BrowserEventType.tab_created
        assert ev.tab_id     == "t1"
        assert ev.url        == "https://x.com"

    def test_event_id_generated(self):
        ev = make_event(BrowserEventType.page_loaded, "t1")
        assert ev.event_id is not None and len(ev.event_id) > 0

    def test_timestamp_is_datetime(self):
        ev = make_event(BrowserEventType.tab_updated, "t1")
        assert isinstance(ev.timestamp, datetime)

    def test_triggers_refresh_true(self):
        for et in REFRESH_TRIGGER_TYPES:
            ev = make_event(et, "t1")
            assert ev.triggers_refresh is True

    def test_triggers_refresh_false(self):
        ev = make_event(BrowserEventType.tab_activated, "t1")
        assert ev.triggers_refresh is False

    def test_to_dict_complete(self):
        ev = make_event(BrowserEventType.url_changed, "t2",
                        url="https://b.com", mission_id="m1")
        d = ev.to_dict()
        assert d["event_type"] == "URL_CHANGED"
        assert d["tab_id"]     == "t2"
        assert d["url"]        == "https://b.com"
        assert d["mission_id"] == "m1"

    def test_optional_fields_default_none(self):
        ev = make_event(BrowserEventType.tab_closed, "t1")
        assert ev.url is None
        assert ev.title is None
        assert ev.mission_id is None


class TestDecisionSignalType:
    def test_three_values(self):
        assert len(DecisionSignalType) == 3
        assert DecisionSignalType.warning.value        == "WARNING"
        assert DecisionSignalType.recommendation.value == "RECOMMENDATION"
        assert DecisionSignalType.info.value           == "INFO"


class TestMakeSignal:
    def test_creates_signal(self):
        sig = make_signal(DecisionSignalType.warning, "m1", "Low trust.", "Engine")
        assert isinstance(sig, DecisionSignal)
        assert sig.signal_type == DecisionSignalType.warning
        assert sig.target_id   == "m1"
        assert sig.message     == "Low trust."
        assert sig.source      == "Engine"

    def test_signal_id_generated(self):
        sig = make_signal(DecisionSignalType.info, "m1", "x", "src")
        assert sig.signal_id is not None and len(sig.signal_id) > 0

    def test_to_dict_complete(self):
        sig = make_signal(DecisionSignalType.recommendation, "m2", "Open tab.", "Rec")
        d = sig.to_dict()
        expected = {"signal_id", "signal_type", "target_id", "message", "source", "created_at", "metadata"}
        assert expected == set(d.keys())
        assert d["signal_type"] == "RECOMMENDATION"


class TestBrowserEventPayload:
    def test_to_browser_event_minimal(self):
        p = BrowserEventPayload(event_type="TAB_CREATED", tab_id="t1")
        ev = p.to_browser_event()
        assert ev.event_type == BrowserEventType.tab_created
        assert ev.tab_id     == "t1"

    def test_unknown_event_type_defaults_tab_updated(self):
        p = BrowserEventPayload(event_type="INVALID_TYPE", tab_id="t1")
        ev = p.to_browser_event()
        assert ev.event_type == BrowserEventType.tab_updated

    def test_timestamp_parsed(self):
        p = BrowserEventPayload(event_type="PAGE_LOADED", tab_id="t1",
                                timestamp="2026-06-24T10:00:00")
        ev = p.to_browser_event()
        assert isinstance(ev.timestamp, datetime)

    def test_missing_timestamp_uses_now(self):
        p = BrowserEventPayload(event_type="TAB_CLOSED", tab_id="t1")
        ev = p.to_browser_event()
        assert isinstance(ev.timestamp, datetime)

    def test_optional_fields_passed_through(self):
        p = BrowserEventPayload(
            event_type="URL_CHANGED", tab_id="t1",
            url="https://z.com", mission_id="m9",
        )
        ev = p.to_browser_event()
        assert ev.url        == "https://z.com"
        assert ev.mission_id == "m9"
