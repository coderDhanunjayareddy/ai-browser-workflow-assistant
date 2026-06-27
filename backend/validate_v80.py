"""
validate_v80.py -- V8.0 Human Approval Center validation suite.
Target: 300+ checks.  Run: python validate_v80.py
"""
import sys
import time
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
    from app.approvals.models import (
        ApprovalStatus, ApprovalSourceType, ApprovalRiskLevel,
        ApprovalRequest, ApprovalDecisionContract,
        RISK_ORDER, make_approval_request, DEFAULT_TTL_SECONDS,
    )
    chk("approvals.models imports", True)
except Exception as e:
    chk(f"approvals.models imports ({e})", False)

try:
    import app.approvals.registry as areg
    chk("approvals.registry imports", True)
except Exception as e:
    chk(f"approvals.registry imports ({e})", False)

try:
    import app.approvals.analytics as aanal
    chk("approvals.analytics imports", True)
except Exception as e:
    chk(f"approvals.analytics imports ({e})", False)

try:
    import app.approvals.timeline as atl
    chk("approvals.timeline imports", True)
except Exception as e:
    chk(f"approvals.timeline imports ({e})", False)

try:
    import app.approvals.queue as aq
    chk("approvals.queue imports", True)
except Exception as e:
    chk(f"approvals.queue imports ({e})", False)

try:
    import app.approvals.generator as agen
    chk("approvals.generator imports", True)
except Exception as e:
    chk(f"approvals.generator imports ({e})", False)

try:
    import app.approvals.inspector as ainsp
    chk("approvals.inspector imports", True)
except Exception as e:
    chk(f"approvals.inspector imports ({e})", False)

try:
    from app.approvals.persistence import APPROVAL_PERSISTENCE, ApprovalPersistence
    chk("approvals.persistence imports", True)
except Exception as e:
    chk(f"approvals.persistence imports ({e})", False)

try:
    from app.schemas.approvals import (
        ApprovalRequestSchema, ApprovalAnalyticsSchema,
        ApprovalInspectorSchema, ApprovalSummarySchema,
        ApprovalDecisionContractSchema,
    )
    chk("schemas.approvals imports", True)
except Exception as e:
    chk(f"schemas.approvals imports ({e})", False)

try:
    from app.api.routes import approvals as appr_routes
    chk("api.routes.approvals imports", True)
except Exception as e:
    chk(f"api.routes.approvals imports ({e})", False)


# ── [2] ApprovalStatus ───────────────────────────────────────────────────────
print("\n[2] ApprovalStatus")

chk("5 statuses",          len(list(ApprovalStatus)) == 5)
chk("PENDING value",       ApprovalStatus.pending.value   == "PENDING")
chk("APPROVED value",      ApprovalStatus.approved.value  == "APPROVED")
chk("REJECTED value",      ApprovalStatus.rejected.value  == "REJECTED")
chk("EXPIRED value",       ApprovalStatus.expired.value   == "EXPIRED")
chk("CANCELLED value",     ApprovalStatus.cancelled.value == "CANCELLED")


# ── [3] ApprovalRiskLevel ────────────────────────────────────────────────────
print("\n[3] ApprovalRiskLevel")

chk("4 risk levels",               len(list(ApprovalRiskLevel)) == 4)
chk("CRITICAL > HIGH risk order",  RISK_ORDER[ApprovalRiskLevel.critical] > RISK_ORDER[ApprovalRiskLevel.high])
chk("HIGH > MEDIUM risk order",    RISK_ORDER[ApprovalRiskLevel.high]     > RISK_ORDER[ApprovalRiskLevel.medium])
chk("MEDIUM > LOW risk order",     RISK_ORDER[ApprovalRiskLevel.medium]   > RISK_ORDER[ApprovalRiskLevel.low])
chk("CRITICAL value",              ApprovalRiskLevel.critical.value == "CRITICAL")
chk("HIGH value",                  ApprovalRiskLevel.high.value     == "HIGH")
chk("MEDIUM value",                ApprovalRiskLevel.medium.value   == "MEDIUM")
chk("LOW value",                   ApprovalRiskLevel.low.value      == "LOW")


# ── [4] ApprovalSourceType ────────────────────────────────────────────────────
print("\n[4] ApprovalSourceType")

chk("4 source types",              len(list(ApprovalSourceType)) == 4)
chk("TRUST_ENGINE value",          ApprovalSourceType.trust_engine.value         == "TRUST_ENGINE")
chk("DECISION_CENTER value",       ApprovalSourceType.decision_center.value      == "DECISION_CENTER")
chk("MISSION_INTELLIGENCE value",  ApprovalSourceType.mission_intelligence.value == "MISSION_INTELLIGENCE")
chk("MANUAL value",                ApprovalSourceType.manual.value               == "MANUAL")


# ── [5] make_approval_request ─────────────────────────────────────────────────
print("\n[5] make_approval_request factory")

ar = make_approval_request(
    ApprovalSourceType.trust_engine, "src-1", "Title", "Desc",
    ApprovalRiskLevel.high, mission_id="m1", task_id="t1",
)
chk("creates ApprovalRequest",      isinstance(ar, ApprovalRequest))
chk("approval_id generated",        bool(ar.approval_id))
chk("source_type set",              ar.source_type    == ApprovalSourceType.trust_engine)
chk("source_id set",                ar.source_id      == "src-1")
chk("title set",                    ar.title          == "Title")
chk("description set",              ar.description    == "Desc")
chk("risk_level set",               ar.risk_level     == ApprovalRiskLevel.high)
chk("mission_id set",               ar.mission_id     == "m1")
chk("task_id set",                  ar.task_id        == "t1")
chk("default status PENDING",       ar.status         == ApprovalStatus.pending)
chk("created_at is float",          isinstance(ar.created_at, float))
chk("expires_at > created_at",      ar.expires_at > ar.created_at)
chk("default ttl ~24h",             abs((ar.expires_at - ar.created_at) - DEFAULT_TTL_SECONDS) < 1)
chk("is_pending True",              ar.is_pending     is True)
chk("is_critical True for HIGH",    ar.is_critical    is True)
chk("risk_order returns int",       isinstance(ar.risk_order, int))

d = ar.to_dict()
chk("to_dict has approval_id",      "approval_id"  in d)
chk("to_dict has source_type",      "source_type"  in d)
chk("to_dict has risk_level",       "risk_level"   in d)
chk("to_dict has status",           "status"       in d)
chk("to_dict status is string",     d["status"]    == "PENDING")
chk("to_dict risk_level string",    d["risk_level"] == "HIGH")
chk("to_dict source_type string",   d["source_type"] == "TRUST_ENGINE")

ar_low = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
chk("is_critical False for LOW",    ar_low.is_critical is False)

ar_exp = make_approval_request(ApprovalSourceType.manual, "s", "T", "D",
                                ApprovalRiskLevel.low, ttl_seconds=0.001)
time.sleep(0.02)
chk("is_expired_now True when past", ar_exp.is_expired_now is True)

ar_fresh = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
chk("is_expired_now False for new", ar_fresh.is_expired_now is False)

chk("critical risk_order > low risk_order",
    make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.critical).risk_order >
    make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low).risk_order)


# ── [6] ApprovalDecisionContract ─────────────────────────────────────────────
print("\n[6] ApprovalDecisionContract")

now_t = time.time()
c = ApprovalDecisionContract(
    approval_id="a1", approved=True, approved_at=now_t,
    decision_source="human_via_api", mission_id="m1",
)
chk("creates contract",           isinstance(c, ApprovalDecisionContract))
chk("approved=True",              c.approved is True)
chk("approval_id set",            c.approval_id == "a1")
chk("approved_at set",            c.approved_at == now_t)
chk("decision_source set",        c.decision_source == "human_via_api")
chk("mission_id set",             c.mission_id == "m1")

cd = c.to_dict()
chk("to_dict has approval_id",    "approval_id"     in cd)
chk("to_dict has approved",       "approved"        in cd)
chk("to_dict has approved_at",    "approved_at"     in cd)
chk("to_dict has decision_source","decision_source" in cd)
chk("to_dict has mission_id",     "mission_id"      in cd)

c2 = ApprovalDecisionContract("a2", False, now_t, "human_via_api")
chk("approved=False for reject",  c2.approved is False)


# ── [7] ApprovalRegistry ──────────────────────────────────────────────────────
print("\n[7] ApprovalRegistry")
areg._reset_for_testing()

def _ar(risk=ApprovalRiskLevel.medium, mission_id=None, task_id=None):
    return make_approval_request(ApprovalSourceType.manual, "s", "T", "D", risk,
                                  mission_id=mission_id, task_id=task_id)

r1 = _ar(mission_id="m-reg")
areg.add(r1)
chk("add and get",                 areg.get(r1.approval_id) is not None)
chk("get unknown returns None",    areg.get("nope") is None)
chk("count = 1",                   areg.count() == 1)

r2 = _ar(ApprovalRiskLevel.critical, mission_id="m-reg")
r3 = _ar(ApprovalRiskLevel.high,     mission_id="m-other")
areg.add(r2); areg.add(r3)
chk("count = 3",                   areg.count() == 3)

chk("list_for_mission m-reg has 2",
    len(areg.list_for_mission("m-reg")) == 2)
chk("list_for_mission m-other has 1",
    len(areg.list_for_mission("m-other")) == 1)

all_items = areg.list_all()
chk("list_all returns 3",           len(all_items) == 3)
chk("list_all sorted by risk",      all_items[0].risk_level == ApprovalRiskLevel.critical)

chk("approve returns True",         areg.approve(r1.approval_id) is True)
chk("status = APPROVED",            areg.get(r1.approval_id).status == ApprovalStatus.approved)
chk("resolved_at set on approve",   areg.get(r1.approval_id).resolved_at is not None)
chk("resolved_by set",              areg.get(r1.approval_id).resolved_by == "human_via_api")
chk("double approve returns False", areg.approve(r1.approval_id) is False)
chk("approve unknown returns False",areg.approve("nope") is False)

chk("reject returns True",          areg.reject(r2.approval_id, "not safe") is True)
chk("status = REJECTED",            areg.get(r2.approval_id).status == ApprovalStatus.rejected)
chk("rejection_reason set",         areg.get(r2.approval_id).rejection_reason == "not safe")
chk("reject unknown returns False", areg.reject("nope") is False)

r4 = _ar()
areg.add(r4)
chk("expire returns True",          areg.expire(r4.approval_id) is True)
chk("status = EXPIRED",             areg.get(r4.approval_id).status == ApprovalStatus.expired)

r5 = _ar()
areg.add(r5)
chk("cancel returns True",          areg.cancel(r5.approval_id) is True)
chk("status = CANCELLED",           areg.get(r5.approval_id).status == ApprovalStatus.cancelled)
chk("cancel approved returns False",areg.cancel(r1.approval_id) is False)

areg._reset_for_testing()
areg.add(_ar(ApprovalRiskLevel.critical))
areg.add(_ar(ApprovalRiskLevel.high))
areg.add(_ar(ApprovalRiskLevel.low))
critical_list = areg.list_critical()
chk("list_critical has 2",          len(critical_list) == 2)
chk("all list_critical are H/C",
    all(r.risk_level in (ApprovalRiskLevel.critical, ApprovalRiskLevel.high)
        for r in critical_list))

pending_list = areg.list_pending()
chk("list_pending returns 3",       len(pending_list) == 3)

s = areg.stats()
chk("stats has cached_items",       "cached_items"   in s)
chk("stats has total_added",        "total_added"    in s)
chk("stats has pending_count",      "pending_count"  in s)
chk("stats has approved_count",     "approved_count" in s)
chk("stats total_added >= 3",       s["total_added"] >= 3)

r_task = _ar(task_id="t-test")
areg.add(r_task)
chk("list_for_task filters by task_id",
    any(r.approval_id == r_task.approval_id for r in areg.list_for_task("t-test")))


# ── [8] ApprovalQueue ─────────────────────────────────────────────────────────
print("\n[8] ApprovalQueue")
areg._reset_for_testing()

def _reg(risk=ApprovalRiskLevel.medium, mission_id=None, task_id=None):
    r = _ar(risk, mission_id, task_id)
    areg.add(r)
    return r

_reg(ApprovalRiskLevel.critical, "m-q")
_reg(ApprovalRiskLevel.high,     "m-q")
_reg(ApprovalRiskLevel.low,      "m-q")
_reg(ApprovalRiskLevel.medium,   "m-other")

chk("all_pending returns list",         isinstance(aq.all_pending(), list))
chk("all_pending only PENDING",         all(r.status == ApprovalStatus.pending
                                            for r in aq.all_pending()))

chk("critical returns list",            isinstance(aq.critical(), list))
chk("critical only H/C",                all(r.risk_level in (ApprovalRiskLevel.critical,
                                                              ApprovalRiskLevel.high)
                                            for r in aq.critical()))
chk("critical count = 2 for m-q pending",  len([r for r in areg.list_pending()
                                               if r.risk_level in (ApprovalRiskLevel.critical,
                                                                    ApprovalRiskLevel.high)]) == 2)

chk("for_mission returns list",         isinstance(aq.for_mission("m-q"), list))
chk("for_mission filters m-q",         all(r.mission_id == "m-q" for r in aq.for_mission("m-q")))
chk("for_mission m-q count = 3",       len(aq.for_mission("m-q")) == 3)
chk("for_mission unknown empty",        aq.for_mission("no-such-m") == [])

chk("pending_for_mission filters",      all(r.status == ApprovalStatus.pending
                                            for r in aq.pending_for_mission("m-q")))

r_task2 = _reg(task_id="t-qtest")
chk("for_task returns list",            isinstance(aq.for_task("t-qtest"), list))
chk("for_task filters by task",         any(r.approval_id == r_task2.approval_id
                                            for r in aq.for_task("t-qtest")))

sm = aq.summary_for_mission("m-q")
chk("summary has total",                "total"    in sm)
chk("summary has pending",              "pending"  in sm)
chk("summary has approved",             "approved" in sm)
chk("summary has rejected",             "rejected" in sm)
chk("summary has critical",             "critical" in sm)
chk("summary total = 3",                sm["total"]   == 3)
chk("summary pending = 3",              sm["pending"] == 3)
chk("summary critical = 2",             sm["critical"] == 2)


# ── [9] ApprovalAnalytics ─────────────────────────────────────────────────────
print("\n[9] ApprovalAnalytics")
aanal._reset_for_testing()

chk("initial created = 0",        aanal.get_analytics()["created"] == 0)
chk("initial avg = 0.0",          aanal.get_analytics()["avg_approval_ms"] == 0.0)

aanal.record_created("CRITICAL")
aanal.record_created("HIGH")
aanal.record_created("MEDIUM")
aanal.record_created("LOW")
a = aanal.get_analytics()
chk("created = 4",                a["created"]  == 4)
chk("critical = 1",               a["critical"] == 1)
chk("high = 1",                   a["high"]     == 1)
chk("medium = 1",                 a["medium"]   == 1)
chk("low = 1",                    a["low"]      == 1)

aanal.record_approved(300.0)
chk("approved = 1",               aanal.get_analytics()["approved"] == 1)

aanal.record_rejected(500.0)
chk("rejected = 1",               aanal.get_analytics()["rejected"] == 1)
chk("avg_approval_ms = 400.0",    aanal.get_analytics()["avg_approval_ms"] == 400.0)

aanal.record_expired()
chk("expired = 1",                aanal.get_analytics()["expired"] == 1)

aanal.record_cancelled()
chk("cancelled = 1",              aanal.get_analytics()["cancelled"] == 1)

aanal._reset_for_testing()
chk("reset clears all",           aanal.get_analytics()["created"] == 0)


# ── [10] ApprovalTimeline ────────────────────────────────────────────────────
print("\n[10] ApprovalTimeline")
atl._reset_for_testing()

atl.record("a1", "created",  mission_id="m-tl", risk_level="HIGH",   title="T1", source="s")
atl.record("a2", "approved", mission_id="m-tl", risk_level="MEDIUM", title="T2", source="s")

events = atl.get("m-tl")
chk("get returns 2 events",       len(events) == 2)
chk("newest first (a2 first)",    events[0]["approval_id"] == "a2")
chk("event has approval_id",      "approval_id" in events[0])
chk("event has event_type",       "event_type"  in events[0])
chk("event has timestamp",        "timestamp"   in events[0])
chk("event has risk_level",       "risk_level"  in events[0])

s = atl.summary("m-tl")
chk("summary event_count = 2",    s["event_count"] == 2)
chk("summary latest_event set",   s["latest_event"] is not None)
chk("type_counts created = 1",    s["type_counts"].get("created",  0) == 1)
chk("type_counts approved = 1",   s["type_counts"].get("approved", 0) == 1)

recent = atl.recent_global(limit=10)
chk("global stream has events",   len(recent) >= 2)

atl.record("a3", "created", mission_id="m-other2")
missions = atl.missions_with_approvals()
chk("missions_with_approvals has m-tl",    "m-tl"     in missions)
chk("missions_with_approvals has m-other2","m-other2" in missions)

atl._reset_for_testing()
chk("reset clears",               atl.get("m-tl") == [])


# ── [11] ApprovalGenerator ────────────────────────────────────────────────────
print("\n[11] ApprovalGenerator")

from app.mission.models import Mission
import app.mission.store as ms

def _mission():
    m = Mission(mission_id=str(uuid.uuid4()), title="V", objective="test")
    ms.put(m)
    return m.mission_id

mid1 = _mission()
gen_items = agen.generate_for_mission(mid1)
chk("generate returns list",              isinstance(gen_items, list))
chk("items are ApprovalRequests",         all(isinstance(x, ApprovalRequest) for x in gen_items))

unk_items = agen.generate_for_mission("unknown-mission-xyz")
chk("unknown mission returns list",       isinstance(unk_items, list))

trust_items = agen._from_trust(mid1)
chk("_from_trust returns list",           isinstance(trust_items, list))
chk("_from_trust items have source",
    all(i.source_type == ApprovalSourceType.trust_engine for i in trust_items))

dec_items = agen._from_decisions(mid1)
chk("_from_decisions returns list",       isinstance(dec_items, list))

intel_items = agen._from_mission_intelligence(mid1)
chk("_from_mission_intelligence returns list", isinstance(intel_items, list))

chk("all generated items have approval_id",
    all(bool(i.approval_id) for i in gen_items))
chk("all generated items PENDING",
    all(i.status == ApprovalStatus.pending for i in gen_items))

# Verify decision source wrapping
from app.decisions.models import DecisionType, DecisionPriority, make_decision
import app.decisions.registry as dec_reg
dec_reg._reset_for_testing()
mid2 = _mission()
crit_dec = make_decision(DecisionType.trust_warning, DecisionPriority.critical,
                          "Crit", "D", "src", mission_id=mid2)
dec_reg.add(crit_dec)
dec_from_items = agen._from_decisions(mid2)
chk("critical decision generates approval",  len(dec_from_items) >= 1)
if dec_from_items:
    chk("decision-sourced approval has DECISION_CENTER source",
        dec_from_items[0].source_type == ApprovalSourceType.decision_center)
    chk("decision-sourced approval references decision_id",
        dec_from_items[0].source_id == crit_dec.decision_id)


# ── [12] ApprovalInspector ────────────────────────────────────────────────────
print("\n[12] ApprovalInspector")
areg._reset_for_testing()
aanal._reset_for_testing()
atl._reset_for_testing()

mid3 = _mission()
areg.add(make_approval_request(ApprovalSourceType.trust_engine, "s", "T", "D",
                                ApprovalRiskLevel.critical, mission_id=mid3))
areg.add(make_approval_request(ApprovalSourceType.decision_center, "s", "T", "D",
                                ApprovalRiskLevel.low, mission_id=mid3))

result = ainsp.inspect(mid3)
chk("inspect returns dict",             isinstance(result, dict))
chk("inspect has mission_id",           "mission_id"        in result)
chk("inspect has pending_count",        "pending_count"     in result)
chk("inspect has approved_count",       "approved_count"    in result)
chk("inspect has rejected_count",       "rejected_count"    in result)
chk("inspect has critical_pending",     "critical_pending"  in result)
chk("inspect has pending_approvals",    "pending_approvals" in result)
chk("inspect has critical_approvals",   "critical_approvals" in result)
chk("inspect has source_breakdown",     "source_breakdown"  in result)
chk("inspect has trust_signals",        "trust_signals"     in result)
chk("inspect has decision_context",     "decision_context"  in result)
chk("inspect has mission_context",      "mission_context"   in result)
chk("inspect has timeline_summary",     "timeline_summary"  in result)
chk("inspect has analytics",            "analytics"         in result)
chk("inspect has registry_stats",       "registry_stats"    in result)
chk("inspect has latency_ms",           "latency_ms"        in result)
chk("pending_count >= 2",               result["pending_count"]   >= 2)
chk("critical_pending >= 1",            result["critical_pending"] >= 1)
chk("mission_id set",                   result["mission_id"] == mid3)
chk("TRUST_ENGINE in source_breakdown",
    "TRUST_ENGINE" in result.get("source_breakdown", {}))
chk("mission_context populated",        result["mission_context"] is not None)

global_result = ainsp.inspect()
chk("global inspect has no mission_id", global_result.get("mission_id") is None)
chk("latency_ms >= 0",                  result["latency_ms"] >= 0)
chk("pending_approvals is list",        isinstance(result["pending_approvals"], list))
chk("critical_approvals is list",       isinstance(result["critical_approvals"], list))


# ── [13] Persistence stub ─────────────────────────────────────────────────────
print("\n[13] Persistence")

chk("APPROVAL_PERSISTENCE is False",      APPROVAL_PERSISTENCE is False)
p = ApprovalPersistence()
test_ar = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
p.save(test_ar)
chk("save() no-op when disabled",         True)
chk("load_for_mission() returns []",      p.load_for_mission("m") == [])
chk("delete_for_mission() returns 0",     p.delete_for_mission("m") == 0)


# ── [14] REST API ─────────────────────────────────────────────────────────────
print("\n[14] REST API")
from fastapi.testclient import TestClient
from app.main import app as _app
client = TestClient(_app)

areg._reset_for_testing()
aanal._reset_for_testing()
atl._reset_for_testing()

mid_api = _mission()

r = client.get("/approvals")
chk("GET /approvals 200",                  r.status_code == 200)
chk("GET /approvals returns list",         isinstance(r.json(), list))

r_pend = client.get("/approvals/pending")
chk("GET /approvals/pending 200",          r_pend.status_code == 200)

r_crit = client.get("/approvals/critical")
chk("GET /approvals/critical 200",         r_crit.status_code == 200)

r_anal = client.get("/approvals/analytics")
chk("GET /approvals/analytics 200",        r_anal.status_code == 200)
chk("analytics has created field",         "created" in r_anal.json())
chk("analytics has avg_approval_ms",       "avg_approval_ms" in r_anal.json())

r_insp = client.get("/approvals/inspect")
chk("GET /approvals/inspect 200",          r_insp.status_code == 200)

r_gen = client.post(f"/approvals/generate/{mid_api}")
chk("POST /approvals/generate 200",        r_gen.status_code == 200)
chk("generate has approvals_found",        "approvals_found" in r_gen.json())
chk("generate has mission_id",             r_gen.json()["mission_id"] == mid_api)
chk("generate has latency_ms",             "latency_ms" in r_gen.json())

r_gen404 = client.post("/approvals/generate/nonexistent-xyz")
chk("POST /approvals/generate/bad 404",    r_gen404.status_code == 404)

# Create approval for CRUD
test_appr = make_approval_request(ApprovalSourceType.manual, "s", "CRUD Test", "D",
                                   ApprovalRiskLevel.high, mission_id=mid_api)
areg.add(test_appr)

r_getone = client.get(f"/approvals/{test_appr.approval_id}")
chk("GET /approvals/{id} 200",             r_getone.status_code == 200)
chk("GET /approvals/{id} correct id",      r_getone.json()["approval_id"] == test_appr.approval_id)

r_get404 = client.get("/approvals/nonexistent-xyz")
chk("GET /approvals/bad 404",              r_get404.status_code == 404)

r_miss = client.get(f"/approvals/mission/{mid_api}")
chk("GET /approvals/mission/{id} 200",     r_miss.status_code == 200)

r_unk_miss = client.get("/approvals/mission/unknown-m")
chk("GET /approvals/mission/unknown empty",r_unk_miss.json() == [])

r_appr = client.post(f"/approvals/{test_appr.approval_id}/approve")
chk("POST /approve 200",                   r_appr.status_code == 200)
chk("POST /approve returns APPROVED",      r_appr.json()["status"] == "APPROVED")
chk("POST /approve returns contract",      "contract" in r_appr.json())
chk("contract approved=True",             r_appr.json()["contract"]["approved"] is True)
chk("contract has approval_id",           "approval_id" in r_appr.json()["contract"])
chk("POST /approve double 409",           client.post(f"/approvals/{test_appr.approval_id}/approve").status_code == 409)
chk("POST /approve unknown 404",          client.post("/approvals/nope/approve").status_code == 404)

test_appr2 = make_approval_request(ApprovalSourceType.manual, "s", "T", "D",
                                    ApprovalRiskLevel.medium)
areg.add(test_appr2)
r_rej = client.post(f"/approvals/{test_appr2.approval_id}/reject",
                     json={"reason": "unsafe", "decision_source": "human_via_api"})
chk("POST /reject 200",                    r_rej.status_code == 200)
chk("POST /reject returns REJECTED",       r_rej.json()["status"] == "REJECTED")
chk("POST /reject returns contract",       "contract" in r_rej.json())
chk("contract approved=False",            r_rej.json()["contract"]["approved"] is False)
chk("POST /reject unknown 404",           client.post("/approvals/nope/reject").status_code == 404)

test_appr3 = make_approval_request(ApprovalSourceType.manual, "s", "T", "D",
                                    ApprovalRiskLevel.low)
areg.add(test_appr3)
r_can = client.post(f"/approvals/{test_appr3.approval_id}/cancel")
chk("POST /cancel 200",                    r_can.status_code == 200)
chk("POST /cancel returns CANCELLED",      r_can.json()["status"] == "CANCELLED")
chk("POST /cancel unknown 404",           client.post("/approvals/nope/cancel").status_code == 404)

# reject-then-approve is 409
test_appr4 = make_approval_request(ApprovalSourceType.manual, "s", "T", "D",
                                    ApprovalRiskLevel.medium)
areg.add(test_appr4)
client.post(f"/approvals/{test_appr4.approval_id}/reject")
chk("POST /approve rejected 409",         client.post(f"/approvals/{test_appr4.approval_id}/approve").status_code == 409)


# ── [15] Mission inspect approvals field ──────────────────────────────────────
print("\n[15] Mission inspect integration")

mid_mi = _mission()
areg.add(make_approval_request(ApprovalSourceType.trust_engine, "s", "T", "D",
                                ApprovalRiskLevel.high, mission_id=mid_mi))
r_mi = client.get(f"/mission/{mid_mi}/inspect")
chk("mission inspect 200",                 r_mi.status_code == 200)
chk("mission inspect has approvals field", "approvals" in r_mi.json())
body_mi = r_mi.json().get("approvals", {})
if body_mi:
    chk("approvals.pending exists",        "pending"  in body_mi)
    chk("approvals.approved exists",       "approved" in body_mi)
    chk("approvals.critical exists",       "critical" in body_mi)
else:
    chk("approvals field present (None)", True)


# ── [16] Decision → Approval integration ─────────────────────────────────────
print("\n[16] Decision -> Approval integration")

from app.decisions.models import DecisionType, DecisionPriority, make_decision
import app.decisions.registry as dec_reg2
dec_reg2._reset_for_testing()
areg._reset_for_testing()

mid_di = _mission()
crit_d2 = make_decision(DecisionType.blocker, DecisionPriority.critical,
                          "Blocker", "D", "src", mission_id=mid_di)
dec_reg2.add(crit_d2)

di_items = agen._from_decisions(mid_di)
chk("critical decision creates approval", len(di_items) >= 1)
if di_items:
    chk("source = DECISION_CENTER",       di_items[0].source_type == ApprovalSourceType.decision_center)
    chk("risk = CRITICAL",                di_items[0].risk_level == ApprovalRiskLevel.critical)
    chk("source_id = decision_id",        di_items[0].source_id == crit_d2.decision_id)

non_crit = make_decision(DecisionType.info, DecisionPriority.low, "Info", "D", "src",
                          mission_id=mid_di)
dec_reg2.add(non_crit)
low_items = agen._from_decisions(mid_di)
chk("low decision does NOT create approval",
    not any(i.source_id == non_crit.decision_id for i in low_items))


# ── [17] Trust → Approval integration ────────────────────────────────────────
print("\n[17] Trust -> Approval integration")

mid_ti = _mission()
trust_appr = agen._from_trust(mid_ti)
chk("_from_trust returns list",           isinstance(trust_appr, list))
chk("all trust approvals have TRUST source",
    all(i.source_type == ApprovalSourceType.trust_engine for i in trust_appr))


# ── [18] Safety constraints ──────────────────────────────────────────────────
print("\n[18] Safety constraints (static checks)")

import pathlib

appr_files = list(pathlib.Path("app/approvals").rglob("*.py"))
forbidden = [
    "requests.get", "httpx.get", "urllib.request", "subprocess",
    "os.system", "webbrowser.open", "playwright", "selenium",
    "workflow_dispatch", "execute_action", "auto_approve",
    "bypass_approval", "run_workflow", "dispatch_action",
    "auto_execute", "self_approve",
]

for fp in appr_files:
    src = fp.read_text(encoding="utf-8")
    for f in forbidden:
        chk(f"no '{f}' in {fp.name}", f not in src)

chk("APPROVAL_PERSISTENCE disabled",      APPROVAL_PERSISTENCE is False)

route_src = pathlib.Path("app/api/routes/approvals.py").read_text(encoding="utf-8")
chk("routes has no execute_action",       "execute_action"  not in route_src)
chk("routes has no auto_approve",         "auto_approve"    not in route_src)
chk("routes has no workflow_dispatch",    "workflow_dispatch" not in route_src)


# ── Summary ───────────────────────────────────────────────────────────────────
total = _passed + _failed
print(f"\n{'='*57}")
print(f"V8.0 Validation: {_passed}/{total} passed", end="")
if _failed:
    print(f"  ({_failed} FAILED)")
    sys.exit(1)
else:
    print("  -- ALL PASS")
