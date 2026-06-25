"""
validate_v70.py — V7.0 Live Browser Sync Layer validation suite.
Target: 140 checks.  Run: python validate_v70.py
"""
import sys
import uuid

_passed = 0
_failed = 0


def chk(label: str, expr: bool) -> None:
    global _passed, _failed
    if expr:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}")


# ── Imports ───────────────────────────────────────────────────────────────────
print("\n[1] Import checks")
try:
    from app.browser.models import (
        BrowserEventType, REFRESH_TRIGGER_TYPES, BrowserEvent, make_event,
        DecisionSignalType, DecisionSignal, make_signal, BrowserEventPayload,
    )
    chk("browser.models imports", True)
except Exception as e:
    chk(f"browser.models imports ({e})", False)

try:
    import app.browser.registry as bev_reg
    chk("browser.registry imports", True)
except Exception as e:
    chk(f"browser.registry imports ({e})", False)

try:
    import app.browser.analytics as bra
    chk("browser.analytics imports", True)
except Exception as e:
    chk(f"browser.analytics imports ({e})", False)

try:
    import app.browser.timeline as tl
    chk("browser.timeline imports", True)
except Exception as e:
    chk(f"browser.timeline imports ({e})", False)

try:
    from app.browser.persistence import BROWSER_EVENT_PERSISTENCE, BrowserEventPersistence
    chk("browser.persistence imports", True)
except Exception as e:
    chk(f"browser.persistence imports ({e})", False)

try:
    from app.browser.sync_service import LiveSyncService, SyncResult, process_event
    chk("browser.sync_service imports", True)
except Exception as e:
    chk(f"browser.sync_service imports ({e})", False)

try:
    from app.browser.mission_refresh import MissionRefreshEngine, refresh as mr_refresh
    chk("browser.mission_refresh imports", True)
except Exception as e:
    chk(f"browser.mission_refresh imports ({e})", False)

try:
    from app.browser.trust_refresh import TrustRefreshEngine, refresh as tr_refresh
    chk("browser.trust_refresh imports", True)
except Exception as e:
    chk(f"browser.trust_refresh imports ({e})", False)

try:
    from app.browser.recommendation import RecommendationRefreshEngine, refresh as rec_refresh
    chk("browser.recommendation imports", True)
except Exception as e:
    chk(f"browser.recommendation imports ({e})", False)

try:
    from app.browser.inspector import BrowserEventInspector
    chk("browser.inspector imports", True)
except Exception as e:
    chk(f"browser.inspector imports ({e})", False)

try:
    from app.schemas.browser import (
        BrowserEventRequest, BrowserSyncRequest, BrowserEventSchema,
        SyncResultSchema, BrowserAnalyticsSchema, BrowserInspectorSchema,
        BrowserTimelineSchema,
    )
    chk("schemas.browser imports", True)
except Exception as e:
    chk(f"schemas.browser imports ({e})", False)

try:
    from app.api.routes import browser as browser_routes
    chk("api.routes.browser imports", True)
except Exception as e:
    chk(f"api.routes.browser imports ({e})", False)


# ── BrowserEventType ──────────────────────────────────────────────────────────
print("\n[2] BrowserEventType")

chk("8 event types defined", len(list(BrowserEventType)) == 8)
chk("TAB_CREATED defined",   BrowserEventType.tab_created.value == "TAB_CREATED")
chk("TAB_UPDATED defined",   BrowserEventType.tab_updated.value == "TAB_UPDATED")
chk("TAB_ACTIVATED defined", BrowserEventType.tab_activated.value == "TAB_ACTIVATED")
chk("TAB_CLOSED defined",    BrowserEventType.tab_closed.value == "TAB_CLOSED")
chk("URL_CHANGED defined",   BrowserEventType.url_changed.value == "URL_CHANGED")
chk("PAGE_LOADED defined",   BrowserEventType.page_loaded.value == "PAGE_LOADED")
chk("WINDOW_FOCUSED defined",BrowserEventType.window_focused.value == "WINDOW_FOCUSED")
chk("WINDOW_BLURRED defined",BrowserEventType.window_blurred.value == "WINDOW_BLURRED")

chk("REFRESH_TRIGGER_TYPES is frozenset", isinstance(REFRESH_TRIGGER_TYPES, frozenset))
chk("tab_created triggers refresh",  BrowserEventType.tab_created  in REFRESH_TRIGGER_TYPES)
chk("tab_closed triggers refresh",   BrowserEventType.tab_closed   in REFRESH_TRIGGER_TYPES)
chk("url_changed triggers refresh",  BrowserEventType.url_changed  in REFRESH_TRIGGER_TYPES)
chk("page_loaded triggers refresh",  BrowserEventType.page_loaded  in REFRESH_TRIGGER_TYPES)
chk("tab_activated does NOT trigger",BrowserEventType.tab_activated not in REFRESH_TRIGGER_TYPES)
chk("window_focused does NOT trigger",BrowserEventType.window_focused not in REFRESH_TRIGGER_TYPES)


# ── BrowserEvent ──────────────────────────────────────────────────────────────
print("\n[3] BrowserEvent + make_event")

ev = make_event(BrowserEventType.tab_created, "t1", url="https://x.com", mission_id="m1")
chk("make_event creates BrowserEvent",   isinstance(ev, BrowserEvent))
chk("event_id is string",                isinstance(ev.event_id, str))
chk("event_type set",                    ev.event_type == BrowserEventType.tab_created)
chk("tab_id set",                        ev.tab_id == "t1")
chk("url set",                           ev.url == "https://x.com")
chk("mission_id set",                    ev.mission_id == "m1")
chk("triggers_refresh True for created", ev.triggers_refresh is True)

ev2 = make_event(BrowserEventType.tab_activated, "t2")
chk("triggers_refresh False for activated", ev2.triggers_refresh is False)

d = ev.to_dict()
chk("to_dict has event_id",    "event_id"    in d)
chk("to_dict has event_type",  "event_type"  in d)
chk("to_dict has tab_id",      "tab_id"      in d)
chk("to_dict has timestamp",   "timestamp"   in d)


# ── DecisionSignal ────────────────────────────────────────────────────────────
print("\n[4] DecisionSignal + make_signal")

chk("3 signal types", len(list(DecisionSignalType)) == 3)
chk("WARNING type",        DecisionSignalType.warning.value        == "WARNING")
chk("RECOMMENDATION type", DecisionSignalType.recommendation.value == "RECOMMENDATION")
chk("INFO type",           DecisionSignalType.info.value           == "INFO")

sig = make_signal(DecisionSignalType.warning, "m-target", "High risk", "rule_r1")
chk("make_signal creates DecisionSignal", isinstance(sig, DecisionSignal))
chk("signal_id generated",               bool(sig.signal_id))
chk("signal_type set",                   sig.signal_type == DecisionSignalType.warning)
chk("target_id set",                     sig.target_id   == "m-target")
chk("message set",                       sig.message     == "High risk")
d = sig.to_dict()
chk("to_dict has signal_id",   "signal_id"   in d)
chk("to_dict has signal_type", "signal_type" in d)


# ── BrowserEventPayload ───────────────────────────────────────────────────────
print("\n[5] BrowserEventPayload")

payload = BrowserEventPayload(event_type="TAB_CREATED", tab_id="t-wire",
                               url="https://pay.com", timestamp="2024-01-01T00:00:00")
ev_from_payload = payload.to_browser_event()
chk("payload produces BrowserEvent",     isinstance(ev_from_payload, BrowserEvent))
chk("event_type from payload",           ev_from_payload.event_type == BrowserEventType.tab_created)
chk("url from payload",                  ev_from_payload.url == "https://pay.com")
chk("timestamp parsed",                  ev_from_payload.timestamp is not None)

unknown_payload = BrowserEventPayload(event_type="UNKNOWN_TYPE", tab_id="t-unk")
ev_unk = unknown_payload.to_browser_event()
chk("unknown type fallback tab_updated", ev_unk.event_type == BrowserEventType.tab_updated)


# ── BrowserEventRegistry ──────────────────────────────────────────────────────
print("\n[6] BrowserEventRegistry")
bev_reg._reset_for_testing()

e1 = make_event(BrowserEventType.tab_created, "t1", mission_id="m-r")
bev_reg.register(e1)
chk("register increments count",      bev_reg.count() == 1)
chk("get by event_id returns event",  bev_reg.get(e1.event_id) is not None)
chk("get unknown returns None",       bev_reg.get("nope") is None)

e2 = make_event(BrowserEventType.url_changed, "t2", mission_id="m-r")
bev_reg.register(e2)
mission_events = bev_reg.events_for_mission("m-r")
chk("events_for_mission returns 2",   len(mission_events) == 2)

tab_events = bev_reg.events_for_tab("t1")
chk("events_for_tab returns 1 for t1", len(tab_events) == 1)

recent = bev_reg.recent_events(limit=5)
chk("recent_events returns list",     isinstance(recent, list))
chk("recent_events count <= limit",    len(recent) <= 5)

s = bev_reg.stats()
chk("stats has cached_events",        "cached_events"    in s)
chk("stats has total_registered",     "total_registered" in s)
chk("stats total_registered >= 2",    s["total_registered"] >= 2)


# ── BrowserEventAnalytics ─────────────────────────────────────────────────────
print("\n[7] BrowserEventAnalytics")
bra._reset_for_testing()

bra.record_event(BrowserEventType.tab_created)
bra.record_event(BrowserEventType.url_changed)
bra.record_event(BrowserEventType.tab_closed)
a = bra.get_analytics()

chk("events_received = 3",           a["events_received"] == 3)
chk("tab_created = 1",               a["tab_created"]     == 1)
chk("url_changed = 1",               a["url_changed"]     == 1)
chk("tab_closed = 1",                a["tab_closed"]      == 1)

bra.record_mission_refresh()
bra.record_trust_refresh()
bra.record_recommendation_refresh()
a2 = bra.get_analytics()
chk("mission_refreshes = 1",         a2["mission_refreshes"]        == 1)
chk("trust_refreshes = 1",           a2["trust_refreshes"]          == 1)
chk("recommendation_refreshes = 1",  a2["recommendation_refreshes"] == 1)


# ── BrowserActivityTimeline ───────────────────────────────────────────────────
print("\n[8] BrowserActivityTimeline")
tl._reset_for_testing()

te1 = make_event(BrowserEventType.tab_created, "t1")
te2 = make_event(BrowserEventType.url_changed,  "t2")
tl.append("m-tl", te1)
tl.append("m-tl", te2)

events = tl.get("m-tl")
chk("get returns 2 events",          len(events) == 2)
chk("newest first",                  events[0]["event_id"] == te2.event_id)
chk("get with limit=1",              len(tl.get("m-tl", limit=1)) == 1)
chk("empty mission returns []",      tl.get("nobody") == [])

s = tl.summary("m-tl")
chk("summary event_count = 2",       s["event_count"]  == 2)
chk("summary latest_event set",      s["latest_event"] is not None)
chk("type_counts TAB_CREATED = 1",   s["type_counts"].get("TAB_CREATED", 0) == 1)

global_ev = make_event(BrowserEventType.window_focused, "t-global")
tl.append_global(global_ev)
recent_g = tl.recent_global(limit=5)
chk("global stream has event",       any(e["event_id"] == global_ev.event_id for e in recent_g))

active = tl.missions_with_activity()
chk("missions_with_activity includes m-tl", "m-tl" in active)


# ── Persistence stub ──────────────────────────────────────────────────────────
print("\n[9] Persistence")

chk("BROWSER_EVENT_PERSISTENCE is False", BROWSER_EVENT_PERSISTENCE is False)
p = BrowserEventPersistence()
ev_p = make_event(BrowserEventType.tab_created, "t-p")
p.save(ev_p)   # must not raise
chk("save() no-ops when disabled", True)
out = p.load_for_mission("m-none")
chk("load_for_mission() returns [] when disabled", out == [])


# ── LiveSyncService ───────────────────────────────────────────────────────────
print("\n[10] LiveSyncService")
from app.tabs import registry as tab_reg
from app.tabs.models import BrowserTabState, BrowserTabRole
tab_reg._reset_for_testing()

svc = LiveSyncService()

se1 = make_event(BrowserEventType.tab_created, "t-svc", url="https://sync.com")
r1 = svc.process_event(se1)
chk("tab_created: success",          r1.success is True)
chk("tab_created: tab_updated",      r1.tab_updated is True)
chk("tab_created: triggers_refresh", r1.triggers_refresh is True)

tab = tab_reg.get("t-svc")
chk("tab registered after created",  tab is not None)
chk("tab url set",                   tab.url == "https://sync.com")

se2 = make_event(BrowserEventType.tab_activated, "t-svc")
r2 = svc.process_event(se2)
chk("tab_activated: success",        r2.success is True)
chk("tab_activated: no refresh",     r2.triggers_refresh is False)
chk("tab state = active after activate", tab_reg.get("t-svc").state == BrowserTabState.active)

se3 = make_event(BrowserEventType.url_changed, "t-svc", url="https://new.com")
r3 = svc.process_event(se3)
chk("url_changed: triggers_refresh", r3.triggers_refresh is True)
chk("url updated",                   tab_reg.get("t-svc").url == "https://new.com")

se4 = make_event(BrowserEventType.page_loaded, "t-svc", url="https://loaded.com", title="Loaded")
r4 = svc.process_event(se4)
chk("page_loaded: triggers_refresh", r4.triggers_refresh is True)
chk("page_loaded updates title",     tab_reg.get("t-svc").title == "Loaded")

se5 = make_event(BrowserEventType.tab_closed, "t-svc")
r5 = svc.process_event(se5)
chk("tab_closed: triggers_refresh",  r5.triggers_refresh is True)
chk("tab state = closed",            tab_reg.get("t-svc").state == BrowserTabState.closed)

se6 = make_event(BrowserEventType.window_focused, "t-wind")
r6 = svc.process_event(se6)
chk("window_focused: no tab update", r6.tab_updated is False)
chk("window_focused: no refresh",    r6.triggers_refresh is False)

d = r1.to_dict()
chk("SyncResult to_dict has success",        "success"         in d)
chk("SyncResult to_dict has triggers_refresh","triggers_refresh" in d)
chk("SyncResult to_dict has latency_ms",     "latency_ms"      in d)


# ── MissionRefreshEngine ──────────────────────────────────────────────────────
print("\n[11] MissionRefreshEngine")
from app.browser.mission_refresh import MissionRefreshEngine, _reset_for_testing as mr_reset
import app.mission.store as ms
from app.mission.models import Mission

mr_reset()

def _mkmission():
    m = Mission(mission_id=str(uuid.uuid4()), title="V", objective="test")
    ms.put(m)
    return m

engine = MissionRefreshEngine(cooldown_s=0)
m = _mkmission()

rr = engine.refresh(m.mission_id)
chk("refresh returns result",        rr is not None)
chk("refresh mission_id correct",    rr.mission_id == m.mission_id)
chk("refresh refreshed=True",        rr.refreshed  is True)
chk("refresh latency_ms >= 0",       rr.latency_ms >= 0)

engine60 = MissionRefreshEngine(cooldown_s=60)
m2 = _mkmission()
rr2a = engine60.refresh(m2.mission_id)
rr2b = engine60.refresh(m2.mission_id)
chk("second refresh skipped (cooldown)", rr2b.refreshed is False)
chk("skipped_reason = cooldown",         rr2b.skipped_reason == "cooldown")

engine60.reset_cooldown(m2.mission_id)
rr2c = engine60.refresh(m2.mission_id)
chk("after reset_cooldown refreshed=True", rr2c.refreshed is True)


# ── TrustRefreshEngine ────────────────────────────────────────────────────────
print("\n[12] TrustRefreshEngine")
from app.browser.trust_refresh import TrustRefreshEngine
import app.trust.registry as trust_reg
trust_reg._reset_for_testing()

te = TrustRefreshEngine()
tm = _mkmission()
tr = te.refresh(tm.mission_id)
chk("trust refresh returns result",   tr is not None)
chk("trust refresh mission_id",       tr.mission_id == tm.mission_id)
chk("trust refresh refreshed=True",   tr.refreshed  is True)
chk("trust_score 0-1",                tr.trust_score is not None and 0.0 <= tr.trust_score <= 1.0)
chk("risk_level present",             tr.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
chk("tab_trust_score present",        tr.tab_trust_score is not None)


# ── RecommendationRefreshEngine ───────────────────────────────────────────────
print("\n[13] RecommendationRefreshEngine")
from app.browser.recommendation import RecommendationRefreshEngine
from app.trust.models import RiskLevel, TargetType, make_evaluation

re = RecommendationRefreshEngine()
rm = _mkmission()

# R1 / R2: high risk + approval_required
high_trust = make_evaluation(TargetType.mission, rm.mission_id, 0.45,
                              RiskLevel.high, True, 0.8, "High risk")
sigs = re.refresh(rm.mission_id, trust_ev=high_trust)
types = [s.signal_type for s in sigs]
chk("R1: WARNING for HIGH risk",            DecisionSignalType.warning        in types)
chk("R2: RECOMMENDATION for approval",      DecisionSignalType.recommendation in types)

# R3: MISSING_COMPARISON_TAB
sigs3 = re.refresh("m-r3", tab_findings=[{"code": "MISSING_COMPARISON_TAB"}])
types3 = [s.signal_type for s in sigs3]
chk("R3: RECOMMENDATION for missing tab",   DecisionSignalType.recommendation in types3)

# R4: ORPHAN_TABS
sigs4 = re.refresh("m-r4", tab_findings=[{"code": "ORPHAN_TABS"}])
types4 = [s.signal_type for s in sigs4]
chk("R4: WARNING for orphan tabs",          DecisionSignalType.warning in types4)

# R7: STALE_TABS
sigs7 = re.refresh("m-r7", tab_findings=[{"code": "STALE_TABS"}])
types7 = [s.signal_type for s in sigs7]
chk("R7: INFO for stale tabs",              DecisionSignalType.info in types7)

# Healthy: no warnings
healthy_trust = make_evaluation(TargetType.mission, "m-h", 0.90,
                                 RiskLevel.low, False, 0.95, "Low risk")
sigs_h = re.refresh("m-h", trust_ev=healthy_trust,
                    tab_ctx={"tab_count": 3, "tab_summaries": []},
                    tab_findings=[])
warnings_h = [s for s in sigs_h if s.signal_type == DecisionSignalType.warning]
chk("No warnings for healthy mission",      len(warnings_h) == 0)


# ── BrowserEventInspector ────────────────────────────────────────────────────
print("\n[14] BrowserEventInspector")
bev_reg._reset_for_testing()
tl._reset_for_testing()
tab_reg._reset_for_testing()

im = _mkmission()
ev_i = make_event(BrowserEventType.tab_created, "t-insp", mission_id=im.mission_id)
bev_reg.register(ev_i)
tl.append(im.mission_id, ev_i)

insp = BrowserEventInspector()
rep = insp.inspect(im.mission_id)
chk("inspect returns dict",           isinstance(rep, dict))
chk("inspect has mission_id",         "mission_id"    in rep)
chk("inspect has recent_events",      "recent_events" in rep)
chk("inspect has tab_context",        "tab_context"   in rep)
chk("inspect has trust",              "trust"         in rep)
chk("inspect has intelligence",       "intelligence"  in rep)
chk("inspect has recommendations",    "recommendations" in rep)
chk("inspect has timeline",           "timeline"      in rep)
chk("recent_events includes ev_i",
    any(e.get("event_id") == ev_i.event_id for e in rep["recent_events"]))


# ── REST API endpoints ────────────────────────────────────────────────────────
print("\n[15] REST API")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

bev_reg._reset_for_testing()
bra._reset_for_testing()
tl._reset_for_testing()
tab_reg._reset_for_testing()

r = client.post("/browser/events", json={"event_type": "TAB_CREATED",
                                          "tab_id": "t-api",
                                          "url": "https://api.com"})
chk("POST /browser/events 200",       r.status_code == 200)
chk("response has success=True",      r.json()["success"] is True)
chk("response has event_id",          "event_id" in r.json())

api_mid = _mkmission().mission_id

r_sync = client.post("/browser/sync", json={"event_type": "TAB_CREATED",
                                              "tab_id": "t-sync-api",
                                              "mission_id": api_mid,
                                              "url": "https://x.com"})
chk("POST /browser/sync 200",         r_sync.status_code == 200)
chk("sync has mission_refresh",        "mission_refresh"  in r_sync.json())
chk("sync has trust_refresh",          "trust_refresh"    in r_sync.json())
chk("sync has recommendations",        "recommendations"  in r_sync.json())

r_list = client.get("/browser/events")
chk("GET /browser/events 200",         r_list.status_code == 200)
chk("events is list",                  isinstance(r_list.json(), list))

ev_id = r.json()["event_id"]
r_single = client.get(f"/browser/events/{ev_id}")
chk("GET /browser/events/{id} 200",    r_single.status_code == 200)
chk("single event has event_id",       r_single.json()["event_id"] == ev_id)

r_404 = client.get("/browser/events/nonexistent-xyz")
chk("GET /browser/events/bad 404",     r_404.status_code == 404)

r_anal = client.get("/browser/analytics")
chk("GET /browser/analytics 200",      r_anal.status_code == 200)
chk("analytics has events_received",   "events_received" in r_anal.json())

r_insp = client.get(f"/browser/inspect/{api_mid}")
chk("GET /browser/inspect/{id} 200",   r_insp.status_code == 200)
chk("inspect has mission_id",          "mission_id" in r_insp.json())

r_insp_404 = client.get("/browser/inspect/not-a-mission")
chk("GET /browser/inspect/bad 404",    r_insp_404.status_code == 404)

r_timeline = client.get(f"/browser/timeline/{api_mid}")
chk("GET /browser/timeline/{id} 200",  r_timeline.status_code == 200)
chk("timeline has event_count",        "event_count" in r_timeline.json())
chk("timeline has events list",        "events"      in r_timeline.json())


# ── Safety constraints ────────────────────────────────────────────────────────
print("\n[16] Safety constraints (static checks)")
import ast, pathlib

browser_files = list(pathlib.Path("app/browser").glob("*.py"))
forbidden = ["requests.get", "httpx.get", "urllib.request", "subprocess",
             "os.system", "webbrowser.open", "playwright", "selenium",
             "tab_reg.close_all", "workflow_dispatch", "execute_action"]

for p in browser_files:
    src = p.read_text()
    for f in forbidden:
        chk(f"no '{f}' in {p.name}", f not in src)

chk("BROWSER_EVENT_PERSISTENCE disabled", BROWSER_EVENT_PERSISTENCE is False)


# ── Summary ───────────────────────────────────────────────────────────────────
total = _passed + _failed
print(f"\n{'='*50}")
print(f"V7.0 Validation: {_passed}/{total} passed", end="")
if _failed:
    print(f"  ({_failed} FAILED)")
    sys.exit(1)
else:
    print("  — ALL PASS")
