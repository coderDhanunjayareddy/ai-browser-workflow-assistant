"""
validate_v75.py -- V7.5 Decision Center validation suite.
Target: 250+ checks.  Run: python validate_v75.py
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


# ── [1] Import checks ─────────────────────────────────────────────────────────
print("\n[1] Import checks")

try:
    from app.decisions.models import (
        DecisionType, DecisionStatus, DecisionPriority, DecisionItem,
        make_decision, PRIORITY_ORDER,
    )
    chk("decisions.models imports", True)
except Exception as e:
    chk(f"decisions.models imports ({e})", False)

try:
    import app.decisions.registry as dreg
    chk("decisions.registry imports", True)
except Exception as e:
    chk(f"decisions.registry imports ({e})", False)

try:
    from app.decisions.priority import PriorityEngine, classify, score
    chk("decisions.priority imports", True)
except Exception as e:
    chk(f"decisions.priority imports ({e})", False)

try:
    import app.decisions.analytics as danal
    chk("decisions.analytics imports", True)
except Exception as e:
    chk(f"decisions.analytics imports ({e})", False)

try:
    import app.decisions.timeline as dtl
    chk("decisions.timeline imports", True)
except Exception as e:
    chk(f"decisions.timeline imports ({e})", False)

try:
    import app.decisions.feed as dfeed
    chk("decisions.feed imports", True)
except Exception as e:
    chk(f"decisions.feed imports ({e})", False)

try:
    import app.decisions.aggregator as dagg
    chk("decisions.aggregator imports", True)
except Exception as e:
    chk(f"decisions.aggregator imports ({e})", False)

try:
    import app.decisions.inspector as dinsp
    chk("decisions.inspector imports", True)
except Exception as e:
    chk(f"decisions.inspector imports ({e})", False)

try:
    from app.decisions.persistence import DECISION_PERSISTENCE, DecisionPersistence
    chk("decisions.persistence imports", True)
except Exception as e:
    chk(f"decisions.persistence imports ({e})", False)

try:
    from app.decisions.sources import trust as trust_src
    chk("decisions.sources.trust imports", True)
except Exception as e:
    chk(f"decisions.sources.trust imports ({e})", False)

try:
    from app.decisions.sources import browser as browser_src
    chk("decisions.sources.browser imports", True)
except Exception as e:
    chk(f"decisions.sources.browser imports ({e})", False)

try:
    from app.decisions.sources import mission as mission_src
    chk("decisions.sources.mission imports", True)
except Exception as e:
    chk(f"decisions.sources.mission imports ({e})", False)

try:
    from app.decisions.sources import research as research_src
    chk("decisions.sources.research imports", True)
except Exception as e:
    chk(f"decisions.sources.research imports ({e})", False)

try:
    from app.schemas.decisions import (
        DecisionItemSchema, DecisionAnalyticsSchema,
        DecisionInspectorSchema, DecisionSummarySchema,
    )
    chk("schemas.decisions imports", True)
except Exception as e:
    chk(f"schemas.decisions imports ({e})", False)

try:
    from app.api.routes import decisions as dec_routes
    chk("api.routes.decisions imports", True)
except Exception as e:
    chk(f"api.routes.decisions imports ({e})", False)


# ── [2] DecisionType ──────────────────────────────────────────────────────────
print("\n[2] DecisionType")

chk("5 decision types",                  len(list(DecisionType)) == 5)
chk("TRUST_WARNING value",               DecisionType.trust_warning.value  == "TRUST_WARNING")
chk("RECOMMENDATION value",              DecisionType.recommendation.value == "RECOMMENDATION")
chk("BLOCKER value",                     DecisionType.blocker.value        == "BLOCKER")
chk("OPPORTUNITY value",                 DecisionType.opportunity.value    == "OPPORTUNITY")
chk("INFO value",                        DecisionType.info.value           == "INFO")


# ── [3] DecisionStatus ────────────────────────────────────────────────────────
print("\n[3] DecisionStatus")

chk("4 statuses",         len(list(DecisionStatus)) == 4)
chk("OPEN value",         DecisionStatus.open.value         == "OPEN")
chk("ACKNOWLEDGED value", DecisionStatus.acknowledged.value == "ACKNOWLEDGED")
chk("DISMISSED value",    DecisionStatus.dismissed.value    == "DISMISSED")
chk("RESOLVED value",     DecisionStatus.resolved.value     == "RESOLVED")


# ── [4] DecisionPriority ──────────────────────────────────────────────────────
print("\n[4] DecisionPriority")

chk("4 priorities",        len(list(DecisionPriority)) == 4)
chk("CRITICAL > HIGH",     PRIORITY_ORDER[DecisionPriority.critical] > PRIORITY_ORDER[DecisionPriority.high])
chk("HIGH > MEDIUM",       PRIORITY_ORDER[DecisionPriority.high]     > PRIORITY_ORDER[DecisionPriority.medium])
chk("MEDIUM > LOW",        PRIORITY_ORDER[DecisionPriority.medium]   > PRIORITY_ORDER[DecisionPriority.low])


# ── [5] make_decision ─────────────────────────────────────────────────────────
print("\n[5] make_decision factory")

d = make_decision(DecisionType.blocker, DecisionPriority.high,
                  "Title", "Desc", "src", mission_id="m1")
chk("creates DecisionItem",      isinstance(d, DecisionItem))
chk("decision_id generated",     bool(d.decision_id))
chk("decision_type set",         d.decision_type == DecisionType.blocker)
chk("priority set",              d.priority      == DecisionPriority.high)
chk("title set",                 d.title         == "Title")
chk("description set",           d.description   == "Desc")
chk("source set",                d.source        == "src")
chk("mission_id set",            d.mission_id    == "m1")
chk("default status OPEN",       d.status        == DecisionStatus.open)
chk("is_active True when OPEN",  d.is_active     is True)
chk("resolved_at None",          d.resolved_at   is None)

dd = d.to_dict()
chk("to_dict has decision_id",   "decision_id"   in dd)
chk("to_dict has decision_type", "decision_type" in dd)
chk("to_dict has priority",      "priority"      in dd)
chk("to_dict has status",        "status"        in dd)
chk("to_dict type value",        dd["decision_type"] == "BLOCKER")
chk("to_dict priority value",    dd["priority"]      == "HIGH")

d2 = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "s")
d2.status = DecisionStatus.resolved
chk("is_active False when RESOLVED", d2.is_active is False)

chk("priority_order CRITICAL > HIGH",
    make_decision(DecisionType.info, DecisionPriority.critical, "T", "D", "s").priority_order >
    make_decision(DecisionType.info, DecisionPriority.high,     "T", "D", "s").priority_order)


# ── [6] DecisionRegistry ─────────────────────────────────────────────────────
print("\n[6] DecisionRegistry")
dreg._reset_for_testing()

def _d(priority=DecisionPriority.medium, mission_id=None, dec_type=DecisionType.info):
    return make_decision(dec_type, priority, "T", "D", "src", mission_id=mission_id)

d1 = _d(mission_id="m-reg")
dreg.add(d1)
chk("add and get",               dreg.get(d1.decision_id) is not None)
chk("get unknown returns None",  dreg.get("nope") is None)
chk("count = 1",                 dreg.count() == 1)

d2 = _d(DecisionPriority.critical, mission_id="m-reg")
d3 = _d(DecisionPriority.low,      mission_id="m-other")
dreg.add(d2); dreg.add(d3)
chk("count = 3",                 dreg.count() == 3)

mission_items = dreg.list_for_mission("m-reg")
ids = {x.decision_id for x in mission_items}
chk("list_for_mission returns m-reg items",   d1.decision_id in ids)
chk("list_for_mission excludes m-other",      d3.decision_id not in ids)

all_items = dreg.list_all()
chk("list_all returns 3",        len(all_items) == 3)
chk("list_all priority sorted",  all_items[0].priority == DecisionPriority.critical)

ok = dreg.update_status(d1.decision_id, DecisionStatus.acknowledged)
chk("update_status returns True",     ok is True)
chk("status updated to ACKNOWLEDGED", dreg.get(d1.decision_id).status == DecisionStatus.acknowledged)
chk("acknowledged_at set",            dreg.get(d1.decision_id).acknowledged_at is not None)

dreg.update_status(d2.decision_id, DecisionStatus.resolved)
chk("resolved_at set",                dreg.get(d2.decision_id).resolved_at is not None)

dreg.update_status(d3.decision_id, DecisionStatus.dismissed)
chk("dismissed_at set",               dreg.get(d3.decision_id).dismissed_at is not None)

chk("update_status unknown returns False", dreg.update_status("nope", DecisionStatus.resolved) is False)

active = dreg.list_active()
chk("list_active empty (all resolved/dismissed/acked)", len(active) == 0)

dreg._reset_for_testing()
dreg.add(_d(DecisionPriority.critical))
dreg.add(_d(DecisionPriority.high))
dreg.add(_d(DecisionPriority.critical))
critical = dreg.list_critical()
chk("list_critical returns 2",          len(critical) == 2)
chk("all critical in list_critical",    all(x.priority == DecisionPriority.critical for x in critical))

s = dreg.stats()
chk("stats has cached_items",    "cached_items"  in s)
chk("stats has total_added",     "total_added"   in s)
chk("stats has open_count",      "open_count"    in s)
chk("stats total_added >= 3",    s["total_added"] >= 3)


# ── [7] PriorityEngine ────────────────────────────────────────────────────────
print("\n[7] PriorityEngine")

engine = PriorityEngine()

chk("defaults score low",            engine.score() < 30)
chk("CRITICAL trust high score",     engine.score(trust_risk_level="CRITICAL", confidence=1.0) >= 40)
chk("blocker adds to score",         engine.score(has_blocker=True, confidence=1.0) > engine.score(confidence=1.0))
chk("low readiness adds score",      engine.score(mission_readiness=0.1, confidence=1.0) >
                                     engine.score(mission_readiness=0.9, confidence=1.0))
chk("score capped at 100",           engine.score(trust_risk_level="CRITICAL", has_blocker=True,
                                                   mission_readiness=0.1, confidence=1.0,
                                                   decision_type="BLOCKER") <= 100)
chk("score >= 0",                    engine.score() >= 0)
chk("from_score 90 -> CRITICAL",     engine.priority_from_score(90)  == DecisionPriority.critical)
chk("from_score 60 -> HIGH",         engine.priority_from_score(60)  == DecisionPriority.high)
chk("from_score 30 -> MEDIUM",       engine.priority_from_score(30)  == DecisionPriority.medium)
chk("from_score 0  -> LOW",          engine.priority_from_score(0)   == DecisionPriority.low)
chk("full critical classify",
    engine.classify(trust_risk_level="CRITICAL", has_blocker=True,
                    mission_readiness=0.2, confidence=1.0,
                    decision_type="TRUST_WARNING") == DecisionPriority.critical)
chk("defaults classify LOW",         classify() == DecisionPriority.low)
chk("module score returns int",      isinstance(score(), int))


# ── [8] DecisionAnalytics ─────────────────────────────────────────────────────
print("\n[8] DecisionAnalytics")
danal._reset_for_testing()

chk("initial created = 0",       danal.get_analytics()["created"] == 0)

danal.record_created("CRITICAL")
danal.record_created("HIGH")
danal.record_created("MEDIUM")
danal.record_created("LOW")
a = danal.get_analytics()
chk("created = 4",               a["created"]  == 4)
chk("critical = 1",              a["critical"] == 1)
chk("high = 1",                  a["high"]     == 1)
chk("medium = 1",                a["medium"]   == 1)
chk("low = 1",                   a["low"]      == 1)

danal.record_acknowledged()
chk("acknowledged = 1",          danal.get_analytics()["acknowledged"] == 1)

danal.record_dismissed()
chk("dismissed = 1",             danal.get_analytics()["dismissed"]    == 1)

danal.record_resolved(300.0)
danal.record_resolved(500.0)
a2 = danal.get_analytics()
chk("resolved = 2",              a2["resolved"]           == 2)
chk("avg_resolution_ms = 400",   a2["avg_resolution_ms"]  == 400.0)

danal._reset_for_testing()
chk("reset clears",              danal.get_analytics()["created"] == 0)


# ── [9] DecisionTimeline ──────────────────────────────────────────────────────
print("\n[9] DecisionTimeline")
dtl._reset_for_testing()

dtl.record("d1", "created",      mission_id="m-tl", priority="HIGH",   title="T1", source="s")
dtl.record("d2", "acknowledged", mission_id="m-tl", priority="MEDIUM", title="T2", source="s")

events = dtl.get("m-tl")
chk("get returns 2 events",      len(events) == 2)
chk("newest first (d2)",         events[0]["decision_id"] == "d2")
chk("event has decision_id",     "decision_id" in events[0])
chk("event has event_type",      "event_type"  in events[0])
chk("event has timestamp",       "timestamp"   in events[0])

s = dtl.summary("m-tl")
chk("summary event_count = 2",   s["event_count"] == 2)
chk("summary latest_event set",  s["latest_event"] is not None)
chk("type_counts created = 1",   s["type_counts"].get("created",      0) == 1)
chk("type_counts acked = 1",     s["type_counts"].get("acknowledged", 0) == 1)

recent = dtl.recent_global(limit=10)
chk("global stream has events",  len(recent) >= 2)

dtl.record("d3", "created", mission_id="m-other")
missions = dtl.missions_with_decisions()
chk("missions_with_decisions includes m-tl",    "m-tl"    in missions)
chk("missions_with_decisions includes m-other", "m-other" in missions)

dtl._reset_for_testing()
chk("reset clears",              dtl.get("m-tl") == [])


# ── [10] DecisionFeed ────────────────────────────────────────────────────────
print("\n[10] DecisionFeed")
dreg._reset_for_testing()

def _reg_d(priority=DecisionPriority.medium, mission_id=None, source="src"):
    item = make_decision(DecisionType.info, priority, "T", "D", source, mission_id=mission_id)
    dreg.add(item)
    return item

dc1 = _reg_d(DecisionPriority.critical, "m-feed")
dc2 = _reg_d(DecisionPriority.low,      "m-feed")
dc3 = _reg_d(DecisionPriority.high,     "m-other")

chk("feed.latest returns list",          isinstance(dfeed.latest(limit=10), list))
chk("feed.latest includes dc1",          any(d.decision_id == dc1.decision_id for d in dfeed.latest()))
chk("feed.critical_only returns crits",  all(d.priority == DecisionPriority.critical
                                             for d in dfeed.critical_only()))
chk("feed.for_mission filters",          all(d.mission_id == "m-feed"
                                             for d in dfeed.for_mission("m-feed")))
chk("feed.for_mission count = 2",        len(dfeed.for_mission("m-feed")) == 2)

dreg.update_status(dc2.decision_id, DecisionStatus.resolved)
active = dfeed.active("m-feed")
chk("feed.active excludes resolved",     not any(d.decision_id == dc2.decision_id for d in active))

xsrc = make_decision(DecisionType.trust_warning, DecisionPriority.high, "T", "D", "trust_engine")
dreg.add(xsrc)
chk("feed.for_source trust_engine",      any(d.decision_id == xsrc.decision_id
                                             for d in dfeed.for_source("trust_engine")))

sm = dfeed.summary_for_mission("m-feed")
chk("summary total_decisions >= 2",      sm["total_decisions"]    >= 2)
chk("summary critical_decisions >= 1",   sm["critical_decisions"] >= 1)
chk("summary recent_decisions is list",  isinstance(sm["recent_decisions"], list))


# ── [11] DecisionAggregator ───────────────────────────────────────────────────
print("\n[11] DecisionAggregator")
dreg._reset_for_testing()
danal._reset_for_testing()
dtl._reset_for_testing()

import app.mission.store as ms
from app.mission.models import Mission

def _make_mission():
    m = Mission(mission_id=str(uuid.uuid4()), title="V", objective="test")
    ms.put(m)
    return m.mission_id

mid = _make_mission()
items = dagg.aggregate(mid)
chk("aggregate returns list",            isinstance(items, list))
chk("items are DecisionItems",           all(isinstance(x, DecisionItem) for x in items))
chk("analytics created = len(items)",    danal.get_analytics()["created"] == len(items))
chk("items stored in registry",
    all(dreg.get(x.decision_id) is not None for x in items))
if items:
    chk("timeline has entries",          len(dtl.get(mid)) == len(items))

items2 = dagg.aggregate("unknown-mid")
chk("aggregate unknown mission returns list", isinstance(items2, list))


# ── [12] DecisionInspector ────────────────────────────────────────────────────
print("\n[12] DecisionInspector")
dreg._reset_for_testing()

mid2 = _make_mission()
dreg.add(make_decision(DecisionType.trust_warning, DecisionPriority.critical, "T", "D", "trust_engine", mission_id=mid2))
dreg.add(make_decision(DecisionType.info,           DecisionPriority.low,      "T", "D", "research",      mission_id=mid2))

result = dinsp.inspect(mid2)
chk("inspect returns dict",            isinstance(result, dict))
chk("inspect has active_count",        "active_count"      in result)
chk("inspect has critical_count",      "critical_count"    in result)
chk("inspect has active_decisions",    "active_decisions"  in result)
chk("inspect has source_breakdown",    "source_breakdown"  in result)
chk("inspect has analytics",           "analytics"         in result)
chk("inspect has registry_stats",      "registry_stats"    in result)
chk("inspect has trust_signals",       "trust_signals"     in result)
chk("inspect has blockers",            "blockers"          in result)
chk("inspect has latency_ms",          "latency_ms"        in result)
chk("active_count >= 2",               result["active_count"]   >= 2)
chk("critical_count >= 1",             result["critical_count"] >= 1)
chk("trust_engine in source_breakdown",
    "trust_engine" in result.get("source_breakdown", {}))

global_result = dinsp.inspect()
chk("global inspect (no mission_id)", isinstance(global_result, dict))
chk("global inspect mission_id None", global_result.get("mission_id") is None)


# ── [13] Persistence stub ────────────────────────────────────────────────────
print("\n[13] Persistence")

chk("DECISION_PERSISTENCE is False",     DECISION_PERSISTENCE is False)
p = DecisionPersistence()
test_d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "s")
p.save(test_d)   # no-op when disabled — must not raise
chk("save() no-op when disabled",        True)
chk("load_for_mission() returns []",     p.load_for_mission("m") == [])
chk("delete_for_mission() returns 0",    p.delete_for_mission("m") == 0)


# ── [14] Sources (integration) ───────────────────────────────────────────────
print("\n[14] Source adapters")

mid3 = _make_mission()

trust_items = trust_src.decisions_for_mission(mid3)
chk("trust source returns list",         isinstance(trust_items, list))
chk("trust items are DecisionItems",     all(isinstance(x, DecisionItem) for x in trust_items))

browser_items = browser_src.decisions_for_mission(mid3)
chk("browser source returns list",       isinstance(browser_items, list))

mission_items_list = mission_src.decisions_for_mission(mid3)
chk("mission source returns list",       isinstance(mission_items_list, list))

research_items = research_src.decisions_for_mission(mid3)
chk("research source returns list",      isinstance(research_items, list))


# ── [15] REST API ─────────────────────────────────────────────────────────────
print("\n[15] REST API")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

dreg._reset_for_testing()
danal._reset_for_testing()
dtl._reset_for_testing()

mid_api = _make_mission()

r = client.get("/decisions")
chk("GET /decisions 200",                r.status_code == 200)
chk("GET /decisions returns list",       isinstance(r.json(), list))

r_crit = client.get("/decisions/critical")
chk("GET /decisions/critical 200",       r_crit.status_code == 200)

r_anal = client.get("/decisions/analytics")
chk("GET /decisions/analytics 200",      r_anal.status_code == 200)
chk("analytics has created field",       "created" in r_anal.json())

r_insp = client.get("/decisions/inspect")
chk("GET /decisions/inspect 200",        r_insp.status_code == 200)

r_agg = client.post(f"/decisions/aggregate/{mid_api}")
chk("POST /decisions/aggregate 200",     r_agg.status_code == 200)
chk("aggregate has decisions key",       "decisions" in r_agg.json())
chk("aggregate has mission_id",          r_agg.json()["mission_id"] == mid_api)

r_agg_404 = client.post("/decisions/aggregate/nonexistent-xyz")
chk("POST /decisions/aggregate/bad 404", r_agg_404.status_code == 404)

# Add a decision via registry for CRUD tests
test_d2 = make_decision(DecisionType.blocker, DecisionPriority.high, "CRUD Test", "D", "src",
                         mission_id=mid_api)
dreg.add(test_d2)

r_get = client.get(f"/decisions/{test_d2.decision_id}")
chk("GET /decisions/{id} 200",           r_get.status_code == 200)
chk("GET /decisions/{id} correct id",    r_get.json()["decision_id"] == test_d2.decision_id)

r_get404 = client.get("/decisions/nonexistent-xyz")
chk("GET /decisions/bad 404",            r_get404.status_code == 404)

r_miss = client.get(f"/decisions/mission/{mid_api}")
chk("GET /decisions/mission/{id} 200",   r_miss.status_code == 200)

r_ack = client.post(f"/decisions/{test_d2.decision_id}/acknowledge")
chk("POST /acknowledge 200",             r_ack.status_code == 200)
chk("POST /acknowledge returns status",  r_ack.json()["status"] == "ACKNOWLEDGED")
chk("acknowledged in registry",         dreg.get(test_d2.decision_id).status == DecisionStatus.acknowledged)

test_d3 = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "s")
dreg.add(test_d3)
r_dis = client.post(f"/decisions/{test_d3.decision_id}/dismiss")
chk("POST /dismiss 200",                 r_dis.status_code == 200)
chk("dismissed in registry",            dreg.get(test_d3.decision_id).status == DecisionStatus.dismissed)

test_d4 = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "s")
dreg.add(test_d4)
r_res = client.post(f"/decisions/{test_d4.decision_id}/resolve")
chk("POST /resolve 200",                 r_res.status_code == 200)
chk("resolved in registry",             dreg.get(test_d4.decision_id).status == DecisionStatus.resolved)

r_ack404 = client.post("/decisions/nope/acknowledge")
chk("POST /acknowledge bad 404",         r_ack404.status_code == 404)

r_dis404 = client.post("/decisions/nope/dismiss")
chk("POST /dismiss bad 404",             r_dis404.status_code == 404)

r_res404 = client.post("/decisions/nope/resolve")
chk("POST /resolve bad 404",             r_res404.status_code == 404)


# ── [16] Mission inspect decisions field ─────────────────────────────────────
print("\n[16] Mission inspect integration")

mid_mi = _make_mission()
r_mi = client.get(f"/mission/{mid_mi}/inspect")
chk("mission inspect 200",               r_mi.status_code == 200)
chk("mission inspect has decisions",     "decisions" in r_mi.json())


# ── [17] Safety constraints ──────────────────────────────────────────────────
print("\n[17] Safety constraints (static checks)")

import pathlib

dec_files = list(pathlib.Path("app/decisions").rglob("*.py"))
forbidden = [
    "requests.get", "httpx.get", "urllib.request", "subprocess",
    "os.system", "webbrowser.open", "playwright", "selenium",
    "workflow_dispatch", "execute_action", "auto_approve",
    "bypass_approval", "run_workflow", "dispatch_action",
]

for p in dec_files:
    src = p.read_text(encoding="utf-8")
    for f in forbidden:
        chk(f"no '{f}' in {p.name}", f not in src)

chk("DECISION_PERSISTENCE disabled",    DECISION_PERSISTENCE is False)


# ── Summary ───────────────────────────────────────────────────────────────────
total = _passed + _failed
print(f"\n{'='*55}")
print(f"V7.5 Validation: {_passed}/{total} passed", end="")
if _failed:
    print(f"  ({_failed} FAILED)")
    sys.exit(1)
else:
    print("  -- ALL PASS")
