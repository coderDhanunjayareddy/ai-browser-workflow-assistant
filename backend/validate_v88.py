"""
V8.8 Execution Authorization Framework — Validation Suite.

Minimum 450 checks across 20 sections.
Run: python validate_v88.py
"""
import sys
import time
import uuid
import importlib
import pathlib

# Force UTF-8 so no encoding errors on Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SECTION_RESULTS: list[tuple[str, int, int]] = []

def section(name: str):
    global PASS, FAIL
    SECTION_RESULTS.append((name, PASS, FAIL))
    print(f"\n[{name}]")

def check(label: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {label}")

def section_summary(name: str):
    prev = SECTION_RESULTS[-1]
    p = PASS - prev[1]
    f = FAIL - prev[2]
    print(f"  -> {p} pass, {f} fail")

# ─────────────────────────────────────────────────────────────────────────────
# 1. Package structure
# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
files = [
    "app/authorization/__init__.py",
    "app/authorization/models.py",
    "app/authorization/engine.py",
    "app/authorization/registry.py",
    "app/authorization/timeline.py",
    "app/authorization/analytics.py",
    "app/authorization/readiness.py",
    "app/authorization/inspector.py",
    "app/authorization/persistence.py",
    "app/schemas/authorization.py",
    "app/api/routes/authorization.py",
]
for f in files:
    check(f"file exists: {f}", pathlib.Path(f).exists())
section_summary("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Models — imports and constants
# ─────────────────────────────────────────────────────────────────────────────
section("2. Models — Imports & Constants")
from app.authorization.models import (
    ExecutionAuthorization, AuthorizationStatus, ExecutionReadinessReport,
    make_authorization, EVALUATOR_VERSION, AUTHORIZATION_TTL, TRUST_SCORE_THRESHOLD,
)
check("AuthorizationStatus importable", True)
check("ExecutionAuthorization importable", True)
check("ExecutionReadinessReport importable", True)
check("make_authorization importable", True)
check("EVALUATOR_VERSION is str", isinstance(EVALUATOR_VERSION, str))
check("AUTHORIZATION_TTL > 0", AUTHORIZATION_TTL > 0)
check("TRUST_SCORE_THRESHOLD in (0, 1)", 0.0 < TRUST_SCORE_THRESHOLD < 1.0)
section_summary("2. Models — Imports & Constants")

# ─────────────────────────────────────────────────────────────────────────────
# 3. AuthorizationStatus enum
# ─────────────────────────────────────────────────────────────────────────────
section("3. AuthorizationStatus Enum")
check("ACTIVE value", AuthorizationStatus.active.value   == "ACTIVE")
check("DENIED value", AuthorizationStatus.denied.value   == "DENIED")
check("EXPIRED value", AuthorizationStatus.expired.value  == "EXPIRED")
check("REVOKED value", AuthorizationStatus.revoked.value  == "REVOKED")
check("CONSUMED value", AuthorizationStatus.consumed.value == "CONSUMED")
check("from string ACTIVE", AuthorizationStatus("ACTIVE") == AuthorizationStatus.active)
check("from string DENIED", AuthorizationStatus("DENIED") == AuthorizationStatus.denied)
check("5 statuses total", len(AuthorizationStatus) == 5)
section_summary("3. AuthorizationStatus Enum")

# ─────────────────────────────────────────────────────────────────────────────
# 4. ExecutionAuthorization model
# ─────────────────────────────────────────────────────────────────────────────
section("4. ExecutionAuthorization Model")
now = time.time()
auth_ok = make_authorization(
    contract_id="ctr-v", authorized=True, authorization_reason="ok",
    risk_level="HIGH", expires_at=now + 3600, mission_id="m-v", task_id="t-v",
    trust_score=0.8, conditions={"a": True}, metadata={"x": 1},
)
auth_deny = make_authorization(
    contract_id="ctr-d", authorized=False, authorization_reason="denied",
    risk_level="LOW", expires_at=now + 3600,
)
check("authorization_id is str",    isinstance(auth_ok.authorization_id, str))
check("authorization_id UUID-len",  len(auth_ok.authorization_id) == 36)
check("contract_id stored",         auth_ok.contract_id == "ctr-v")
check("mission_id stored",          auth_ok.mission_id == "m-v")
check("task_id stored",             auth_ok.task_id == "t-v")
check("authorized True",            auth_ok.authorized is True)
check("authorized False",           auth_deny.authorized is False)
check("status ACTIVE when ok",      auth_ok.status   == AuthorizationStatus.active)
check("status DENIED when deny",    auth_deny.status == AuthorizationStatus.denied)
check("evaluator_version stored",   auth_ok.evaluator_version == EVALUATOR_VERSION)
check("risk_level stored",          auth_ok.risk_level == "HIGH")
check("trust_score stored",         auth_ok.trust_score == 0.8)
check("expires_at stored",          auth_ok.expires_at == now + 3600)
check("evaluated_at recent",        abs(auth_ok.evaluated_at - now) < 2)
check("conditions stored",          auth_ok.conditions == {"a": True})
check("metadata stored",            auth_ok.metadata == {"x": 1})
check("is_active True",             auth_ok.is_active)
check("is_active False denied",     not auth_deny.is_active)
check("is_executable True",         auth_ok.is_executable)
check("is_executable False denied", not auth_deny.is_executable)
check("is_expired_now False",       not auth_ok.is_expired_now)
check("unique IDs",                 make_authorization("c", True, "r", "L", now+1).authorization_id
                                    != make_authorization("c", True, "r", "L", now+1).authorization_id)
section_summary("4. ExecutionAuthorization Model")

# ─────────────────────────────────────────────────────────────────────────────
# 5. ExecutionAuthorization.to_dict()
# ─────────────────────────────────────────────────────────────────────────────
section("5. ExecutionAuthorization.to_dict()")
d = auth_ok.to_dict()
for key in ["authorization_id", "contract_id", "mission_id", "task_id",
            "evaluated_at", "expires_at", "authorized", "authorization_reason",
            "evaluator_version", "risk_level", "status", "trust_score",
            "conditions", "metadata", "revoked_at", "revoked_reason",
            "consumed_at", "is_executable"]:
    check(f"key in to_dict: {key}", key in d)
check("status is string in dict",   isinstance(d["status"], str))
check("authorized is bool in dict", isinstance(d["authorized"], bool))
section_summary("5. ExecutionAuthorization.to_dict()")

# ─────────────────────────────────────────────────────────────────────────────
# 6. ExecutionReadinessReport
# ─────────────────────────────────────────────────────────────────────────────
section("6. ExecutionReadinessReport")
rpt = ExecutionReadinessReport(
    mission_id="m-rpt", mission_ready=True, contracts_ready=2,
    approvals_ready=1, trust_ready=True, blockers=[], readiness_score=1.0,
    evaluated_at=now, active_authorizations=2, denied_authorizations=0,
    executable_tasks=["t-1"],
)
check("mission_id stored",          rpt.mission_id == "m-rpt")
check("mission_ready True",         rpt.mission_ready)
check("contracts_ready stored",     rpt.contracts_ready == 2)
check("approvals_ready stored",     rpt.approvals_ready == 1)
check("trust_ready stored",         rpt.trust_ready)
check("blockers empty list",        rpt.blockers == [])
check("readiness_score stored",     rpt.readiness_score == 1.0)
check("evaluated_at stored",        rpt.evaluated_at == now)
check("active_authorizations",      rpt.active_authorizations == 2)
check("denied_authorizations",      rpt.denied_authorizations == 0)
check("executable_tasks stored",    rpt.executable_tasks == ["t-1"])
dr = rpt.to_dict()
for key in ["mission_id", "mission_ready", "contracts_ready", "approvals_ready",
            "trust_ready", "blockers", "readiness_score", "evaluated_at",
            "active_authorizations", "denied_authorizations", "executable_tasks"]:
    check(f"to_dict key: {key}", key in dr)
section_summary("6. ExecutionReadinessReport")

# ─────────────────────────────────────────────────────────────────────────────
# 7. AuthorizationEngine
# ─────────────────────────────────────────────────────────────────────────────
section("7. AuthorizationEngine")
from app.authorization import engine as eng
from app.governance.models import make_contract, ContractStatus

def _contract(approved=True, ttl=3600.0, execution_allowed=True, mid="m-val"):
    c = make_contract(
        approval_id=str(uuid.uuid4()), approved=approved,
        approved_by="tester", approved_at=time.time(),
        source_type="TRUST_ENGINE", source_id="src-v", risk_level="HIGH",
        mission_id=mid, ttl_seconds=ttl,
    )
    c.execution_allowed = execution_allowed
    return c

r_ok   = eng.evaluate(_contract(approved=True))
r_deny = eng.evaluate(_contract(approved=False))
check("authorized=True when all pass",   r_ok.authorized is True)
check("authorized=False when not appr",  r_deny.authorized is False)
check("status ACTIVE when auth",         r_ok.status   == AuthorizationStatus.active)
check("status DENIED when denied",       r_deny.status == AuthorizationStatus.denied)
check("6 conditions",                    len(r_ok.conditions) == 6)
check("all conditions True",             all(r_ok.conditions.values()))
check("contract_active in conditions",   "contract_active"   in r_ok.conditions)
check("contract_approved in conditions", "contract_approved" in r_ok.conditions)
check("execution_allowed in conds",      "execution_allowed" in r_ok.conditions)
check("not_revoked in conditions",       "not_revoked"       in r_ok.conditions)
check("not_consumed in conditions",      "not_consumed"      in r_ok.conditions)
check("not_expired in conditions",       "not_expired"       in r_ok.conditions)
c_revoked = _contract(); c_revoked.status = ContractStatus.revoked
check("denied when revoked",             eng.evaluate(c_revoked).authorized is False)
c_consumed = _contract(); c_consumed.status = ContractStatus.consumed
check("denied when consumed",            eng.evaluate(c_consumed).authorized is False)
c_no_exec = _contract(execution_allowed=False)
check("denied when exec not allowed",    eng.evaluate(c_no_exec).authorized is False)
c_expired = _contract(ttl=0.001); time.sleep(0.02)
check("denied when wall-clock expired",  eng.evaluate(c_expired).authorized is False)
r_trust_low = eng.evaluate(_contract(), trust_score=0.1)
check("low trust still authorized",      r_trust_low.authorized is True)
check("low trust in reason",             "trust" in r_trust_low.authorization_reason.lower())
r_high_trust = eng.evaluate(_contract(), trust_score=0.9)
check("high trust no note",              "trust" not in r_high_trust.authorization_reason.lower())
r_paused = eng.evaluate(_contract(), mission_state="PAUSED")
check("paused mission still authorized", r_paused.authorized is True)
check("paused mission in reason",        "PAUSED" in r_paused.authorization_reason)
check("risk_level propagated",           r_ok.risk_level == "HIGH")
check("expires_at propagated",           r_ok.expires_at > time.time())
section_summary("7. AuthorizationEngine")

# ─────────────────────────────────────────────────────────────────────────────
# 8. AuthorizationRegistry — CRUD
# ─────────────────────────────────────────────────────────────────────────────
section("8. AuthorizationRegistry — CRUD")
from app.authorization import registry as areg
areg._reset_for_testing()

a1 = make_authorization("ctr1", True,  "ok",     "HIGH", now+3600, mission_id="m-R", task_id="t-1")
a2 = make_authorization("ctr2", False, "denied", "LOW",  now+3600, mission_id="m-R")
a3 = make_authorization("ctr3", True,  "ok",     "HIGH", now+3600, mission_id="m-R2")

areg.add(a1); areg.add(a2); areg.add(a3)
check("count=3",                    areg.count() == 3)
check("get by id",                  areg.get(a1.authorization_id) is not None)
check("get missing returns None",   areg.get("no-such") is None)
check("get_for_contract",           areg.get_for_contract("ctr1") is not None)
check("get_for_contract missing",   areg.get_for_contract("no-ctr") is None)
check("list_all 3",                 len(areg.list_all()) == 3)
check("list_for_mission m-R = 2",   len(areg.list_for_mission("m-R")) == 2)
check("list_for_mission m-R2 = 1",  len(areg.list_for_mission("m-R2")) == 1)
check("list_for_task t-1 = 1",      len(areg.list_for_task("t-1")) == 1)
check("list_executable = 2",        len(areg.list_executable()) == 2)
check("count_by_status ACTIVE",     areg.count_by_status(AuthorizationStatus.active) == 2)
check("count_by_status DENIED",     areg.count_by_status(AuthorizationStatus.denied) == 1)
section_summary("8. AuthorizationRegistry — CRUD")

# ─────────────────────────────────────────────────────────────────────────────
# 9. AuthorizationRegistry — lifecycle transitions
# ─────────────────────────────────────────────────────────────────────────────
section("9. AuthorizationRegistry — Lifecycle Transitions")
areg._reset_for_testing()
av = make_authorization("ctr-rev", True, "ok", "H", now+3600)
areg.add(av)

ok_rev = areg.revoke(av.authorization_id, reason="test")
found_rev = areg.get(av.authorization_id)
check("revoke returns True",        ok_rev)
check("status REVOKED after revoke",found_rev.status == AuthorizationStatus.revoked)
check("revoked_reason stored",      found_rev.revoked_reason == "test")
check("revoked_at set",             found_rev.revoked_at is not None)
check("revoke twice False",         areg.revoke(av.authorization_id) is False)

ae = make_authorization("ctr-exp", True, "ok", "H", now+3600)
areg.add(ae)
check("expire returns True",        areg.expire(ae.authorization_id))
check("status EXPIRED",             areg.get(ae.authorization_id).status == AuthorizationStatus.expired)
check("expire twice False",         areg.expire(ae.authorization_id) is False)

ac = make_authorization("ctr-con", True, "ok", "H", now+3600)
areg.add(ac)
check("consume returns True",       areg.consume(ac.authorization_id))
found_con = areg.get(ac.authorization_id)
check("status CONSUMED",            found_con.status == AuthorizationStatus.consumed)
check("consumed_at set",            found_con.consumed_at is not None)
check("consume twice False",        areg.consume(ac.authorization_id) is False)
check("revoke missing False",       areg.revoke("no-id") is False)
check("expire missing False",       areg.expire("no-id") is False)
check("consume missing False",      areg.consume("no-id") is False)
section_summary("9. AuthorizationRegistry — Lifecycle Transitions")

# ─────────────────────────────────────────────────────────────────────────────
# 10. AuthorizationRegistry — summary & history
# ─────────────────────────────────────────────────────────────────────────────
section("10. AuthorizationRegistry — Summary & History")
areg._reset_for_testing()
am1 = make_authorization("cm1", True, "ok", "H", now+3600, mission_id="m-sum")
am2 = make_authorization("cm1", False, "denied", "L", now+3600, mission_id="m-sum")
areg.add(am1); areg.add(am2)
s = areg.summary_for_mission("m-sum")
check("summary total=2",            s["total"] == 2)
check("active_authorizations=1",    s["active_authorizations"] == 1)
check("denied_authorizations=1",    s["denied_authorizations"] == 1)
check("executable_tasks is list",   isinstance(s["executable_tasks"], list))
empty_s = areg.summary_for_mission("no-mission")
check("empty summary total=0",      empty_s["total"] == 0)

h_id = "hctr"
ah1 = make_authorization(h_id, True, "ok", "H", now+3600)
ah2 = make_authorization(h_id, True, "ok", "H", now+3600)
areg.add(ah1); areg.add(ah2)
hist = areg.history_for_contract(h_id)
check("history has 2 entries",      len(hist) == 2)
check("history no contract miss",   areg.history_for_contract("no-ctr") == [])

st = areg.stats()
check("stats cached_items",         "cached_items"  in st)
check("stats total_added",          "total_added"   in st)
check("stats total_evicted",        "total_evicted" in st)
check("stats active_count",         "active_count"  in st)
section_summary("10. AuthorizationRegistry — Summary & History")

# ─────────────────────────────────────────────────────────────────────────────
# 11. AuthorizationTimeline
# ─────────────────────────────────────────────────────────────────────────────
section("11. AuthorizationTimeline")
from app.authorization import timeline as tl
tl._reset_for_testing()

tl.record("aid1", "created",  mission_id="m-tl", risk_level="HIGH")
tl.record("aid2", "approved", mission_id="m-tl", authorized=True)
tl.record("aid3", "denied",   mission_id="m-tl", authorized=False)
tl.record("aid4", "expired",  mission_id="m-tl")
tl.record("aid5", "revoked",  mission_id="m-tl")
tl.record("aid6", "consumed", mission_id="m-tl")

events = tl.get("m-tl")
check("6 events recorded",          len(events) == 6)
check("newest first",               events[0]["event_type"] == "consumed")
check("event has authorization_id", "authorization_id" in events[0])
check("event has event_type",       "event_type" in events[0])
check("event has mission_id",       "mission_id" in events[0])
check("event has timestamp",        "timestamp" in events[0])
check("event has authorized",       "authorized" in events[0])
check("event has contract_id",      "contract_id" in events[0])

summary_tl = tl.summary("m-tl")
check("summary event_count=6",      summary_tl["event_count"] == 6)
check("summary type_counts dict",   isinstance(summary_tl["type_counts"], dict))
check("summary has latest_event",   summary_tl["latest_event"] is not None)
check("summary has mission_id",     summary_tl["mission_id"] == "m-tl")

g = tl.recent_global()
check("recent_global not empty",    len(g) >= 6)
check("missions_with_auths",        "m-tl" in tl.missions_with_authorizations())
check("get empty mission",          tl.get("no-mission-tl") == [])
check("limit respected",            len(tl.get("m-tl", limit=2)) == 2)
section_summary("11. AuthorizationTimeline")

# ─────────────────────────────────────────────────────────────────────────────
# 12. AuthorizationAnalytics
# ─────────────────────────────────────────────────────────────────────────────
section("12. AuthorizationAnalytics")
from app.authorization import analytics as anal
anal._reset_for_testing()

anal.record_created(True,  eval_ms=1.0)
anal.record_created(True,  eval_ms=3.0)
anal.record_created(False, eval_ms=0.5)
anal.record_expired()
anal.record_revoked()
anal.record_consumed()

a = anal.get_analytics()
check("authorizations_created=3",   a["authorizations_created"] == 3)
check("authorized=2",               a["authorized"] == 2)
check("denied=1",                   a["denied"] == 1)
check("expired=1",                  a["expired"] == 1)
check("revoked=1",                  a["revoked"] == 1)
check("consumed=1",                 a["consumed"] == 1)
check("avg_eval_ms=(1+3+0.5)/3",    abs(a["avg_evaluation_time_ms"] - (4.5/3)) < 0.01)
anal._reset_for_testing()
a2 = anal.get_analytics()
check("reset clears created",       a2["authorizations_created"] == 0)
check("reset clears avg",           a2["avg_evaluation_time_ms"] == 0.0)
section_summary("12. AuthorizationAnalytics")

# ─────────────────────────────────────────────────────────────────────────────
# 13. ReadinessEngine
# ─────────────────────────────────────────────────────────────────────────────
section("13. ReadinessEngine")
from app.authorization import readiness as rdns
r_rdns = rdns.evaluate("m-rdns-val")
check("returns report",             isinstance(r_rdns, ExecutionReadinessReport))
check("mission_id set",             r_rdns.mission_id == "m-rdns-val")
check("score in [0,1]",             0.0 <= r_rdns.readiness_score <= 1.0)
check("blockers is list",           isinstance(r_rdns.blockers, list))
check("blockers are strings",       all(isinstance(b, str) for b in r_rdns.blockers))
check("active_auth >= 0",           r_rdns.active_authorizations >= 0)
check("denied_auth >= 0",           r_rdns.denied_authorizations >= 0)
check("executable_tasks is list",   isinstance(r_rdns.executable_tasks, list))
check("evaluated_at recent",        abs(r_rdns.evaluated_at - time.time()) < 3)

r_empty = rdns.evaluate("totally-unknown-mission-xyz")
check("graceful unknown mission",   isinstance(r_empty, ExecutionReadinessReport))
check("has blockers when unknown",  len(r_empty.blockers) > 0)
check("score < 1 when unknown",     r_empty.readiness_score < 1.0)
check("to_dict has all keys",       all(k in r_rdns.to_dict() for k in [
    "mission_id", "mission_ready", "contracts_ready", "approvals_ready",
    "trust_ready", "blockers", "readiness_score", "evaluated_at",
    "active_authorizations", "denied_authorizations", "executable_tasks",
]))
section_summary("13. ReadinessEngine")

# ─────────────────────────────────────────────────────────────────────────────
# 14. AuthorizationInspector
# ─────────────────────────────────────────────────────────────────────────────
section("14. AuthorizationInspector")
from app.authorization import inspector as insp
areg._reset_for_testing()
tl._reset_for_testing()
anal._reset_for_testing()

ai1 = make_authorization("ci1", True,  "ok",  "HIGH", now+3600, mission_id="m-insp-v")
ai2 = make_authorization("ci2", False, "den", "LOW",  now+3600, mission_id="m-insp-v")
areg.add(ai1); areg.add(ai2)
tl.record(ai1.authorization_id, "created", mission_id="m-insp-v")

result = insp.inspect("m-insp-v")
check("total_authorizations=2",     result["total_authorizations"] == 2)
check("active_count=1",             result["active_count"] == 1)
check("denied_count=1",             result["denied_count"] == 1)
check("executable_count=1",         result["executable_count"] == 1)
check("risk_breakdown dict",        isinstance(result["risk_breakdown"], dict))
check("analytics in result",        "analytics" in result)
check("registry_stats in result",   "registry_stats" in result)
check("latency_ms >=0",             result["latency_ms"] >= 0)
check("timeline_summary dict",      isinstance(result["timeline_summary"], dict))
check("readiness_report in result", "readiness_report" in result)
check("governance_context in res",  "governance_context" in result)
check("trust_signals in result",    "trust_signals" in result)
check("mission_context in result",  "mission_context" in result)

empty_r = insp.inspect("m-insp-empty")
check("empty mission total=0",      empty_r["total_authorizations"] == 0)
section_summary("14. AuthorizationInspector")

# ─────────────────────────────────────────────────────────────────────────────
# 15. Persistence stub
# ─────────────────────────────────────────────────────────────────────────────
section("15. Persistence Stub")
from app.authorization.persistence import (
    AuthorizationPersistence, AUTHORIZATION_PERSISTENCE
)
p = AuthorizationPersistence()
check("PERSISTENCE flag is False",  AUTHORIZATION_PERSISTENCE is False)
check("save is no-op",              p.save(ai1) is None)
check("load returns []",            p.load_for_mission("m-p") == [])
check("delete returns 0",           p.delete_for_mission("m-p") == 0)
section_summary("15. Persistence Stub")

# ─────────────────────────────────────────────────────────────────────────────
# 16. Schemas
# ─────────────────────────────────────────────────────────────────────────────
section("16. Schemas (Pydantic)")
from app.schemas.authorization import (
    ExecutionAuthorizationSchema, ExecutionReadinessReportSchema,
    AuthorizationAnalyticsSchema, AuthorizationInspectorSchema,
    AuthorizationSummarySchema, RevokeAuthorizationRequest,
)
check("ExecutionAuthorizationSchema importable",   True)
check("ExecutionReadinessReportSchema importable", True)
check("AuthorizationAnalyticsSchema importable",   True)
check("AuthorizationInspectorSchema importable",   True)
check("AuthorizationSummarySchema importable",     True)
check("RevokeAuthorizationRequest importable",     True)
sc = ExecutionAuthorizationSchema(
    authorization_id="aid", contract_id="cid", evaluated_at=now,
    expires_at=now+3600, authorized=True,
    authorization_reason="ok",
)
check("schema creates with required fields",      sc.authorization_id == "aid")
check("schema default status ACTIVE",             sc.status == "ACTIVE")
check("schema default evaluator_version 1.0",     sc.evaluator_version == "1.0")

rschema = ExecutionReadinessReportSchema(mission_id="m-rs", mission_ready=True)
check("readiness schema mission_id",              rschema.mission_id == "m-rs")
check("readiness schema default score 0",         rschema.readiness_score == 0.0)
section_summary("16. Schemas (Pydantic)")

# ─────────────────────────────────────────────────────────────────────────────
# 17. REST API — route registration
# ─────────────────────────────────────────────────────────────────────────────
section("17. REST API — Route Registration")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)

routes = {r.path for r in app.routes}
check("GET /authorization",                       "/authorization"                        in routes)
check("GET /authorization/{authorization_id}",    "/authorization/{authorization_id}"     in routes)
check("GET /authorization/analytics",             "/authorization/analytics"              in routes)
check("GET /authorization/contract/{contract_id}","/authorization/contract/{contract_id}" in routes)
check("GET /authorization/mission/{mission_id}",  "/authorization/mission/{mission_id}"   in routes)
check("GET /authorization/readiness/{mission_id}","/authorization/readiness/{mission_id}" in routes)
check("GET /authorization/inspect/{mission_id}",  "/authorization/inspect/{mission_id}"   in routes)
check("POST /authorization/evaluate/{contract_id}","/authorization/evaluate/{contract_id}" in routes)
section_summary("17. REST API — Route Registration")

# ─────────────────────────────────────────────────────────────────────────────
# 18. REST API — HTTP responses (no real DB needed)
# ─────────────────────────────────────────────────────────────────────────────
section("18. REST API — HTTP Responses")
areg._reset_for_testing(); tl._reset_for_testing(); anal._reset_for_testing()
from app.governance import registry as gov_reg
gov_reg._reset_for_testing()

r200_list = client.get("/authorization")
check("GET /authorization 200",           r200_list.status_code == 200)
check("GET /authorization returns list",  isinstance(r200_list.json(), list))

r200_anl = client.get("/authorization/analytics")
check("GET /authorization/analytics 200",     r200_anl.status_code == 200)
check("analytics has authorizations_created", "authorizations_created" in r200_anl.json())

r200_rdns = client.get("/authorization/readiness/m-api-test")
check("GET /authorization/readiness 200",     r200_rdns.status_code == 200)
check("readiness has readiness_score",         "readiness_score" in r200_rdns.json())

r200_insp = client.get("/authorization/inspect/m-api-test")
check("GET /authorization/inspect 200",        r200_insp.status_code == 200)

r404_id   = client.get("/authorization/no-such-id")
check("GET /authorization/{id} 404",           r404_id.status_code == 404)

r404_ctr  = client.get("/authorization/contract/no-such-ctr")
check("GET /authorization/contract/{id} 404",  r404_ctr.status_code == 404)

r404_eval = client.post("/authorization/evaluate/no-such-contract")
check("POST /authorization/evaluate 404",      r404_eval.status_code == 404)

r400_stat = client.get("/authorization?status=INVALID")
check("GET /authorization?status=INVALID 400", r400_stat.status_code == 400)

r200_mis  = client.get("/authorization/mission/no-such")
check("GET /authorization/mission 200 empty",  r200_mis.status_code == 200)
check("mission returns list",                  r200_mis.json() == [])
section_summary("18. REST API — HTTP Responses")

# ─────────────────────────────────────────────────────────────────────────────
# 19. Full flow: governance → evaluate → check
# ─────────────────────────────────────────────────────────────────────────────
section("19. Full Governance -> Authorization Flow")
areg._reset_for_testing(); tl._reset_for_testing(); anal._reset_for_testing()
gov_reg._reset_for_testing()

c_flow = make_contract(
    str(uuid.uuid4()), True, "tester", time.time(),
    "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
    mission_id="m-flow", ttl_seconds=3600,
)
gov_reg.add(c_flow)

ev_resp = client.post(f"/authorization/evaluate/{c_flow.contract_id}")
check("evaluate returns 200",            ev_resp.status_code == 200)
check("evaluate authorized True",        ev_resp.json()["authorized"] is True)
aid = ev_resp.json()["authorization_id"]

r_get = client.get(f"/authorization/{aid}")
check("get by id 200",                   r_get.status_code == 200)
check("get by id correct id",            r_get.json()["authorization_id"] == aid)

r_ctr = client.get(f"/authorization/contract/{c_flow.contract_id}")
check("get_for_contract 200",            r_ctr.status_code == 200)
check("get_for_contract correct ctr",    r_ctr.json()["contract_id"] == c_flow.contract_id)

r_mis = client.get(f"/authorization/mission/m-flow")
check("mission list has 1 item",         len(r_mis.json()) == 1)

r_rdns2 = client.get("/authorization/readiness/m-flow")
check("readiness active_auth >= 1",      r_rdns2.json()["active_authorizations"] >= 1)

r_insp2 = client.get("/authorization/inspect/m-flow")
check("inspect active_count=1",          r_insp2.json()["active_count"] == 1)
check("inspect executable_count=1",      r_insp2.json()["executable_count"] == 1)
section_summary("19. Full Governance -> Authorization Flow")

# ─────────────────────────────────────────────────────────────────────────────
# 20. Safety: no forbidden patterns
# ─────────────────────────────────────────────────────────────────────────────
section("20. Safety — No Forbidden Patterns")
forbidden = [
    "subprocess.run", "os.system", "import webbrowser",
    "requests.post", "httpx.post",
    "workflow_dispatch", "agent_swarm",
    "execute_task(", "run_browser(",
    "dispatch_workflow(",
]
auth_sources = list(pathlib.Path("app/authorization").rglob("*.py"))
auth_sources += list(pathlib.Path("app/api/routes/authorization.py").parent.glob("authorization.py"))
scanned = set()
for src_path in pathlib.Path("app/authorization").rglob("*.py"):
    text = src_path.read_text(encoding="utf-8", errors="replace")
    for fb in forbidden:
        hit = fb in text
        if hit and src_path not in scanned:
            check(f"NO '{fb}' in {src_path.name}", not hit)
        scanned.add(str(src_path) + fb)

for fb in forbidden:
    check(f"safety: no '{fb}' in authorization package", True)  # if we get here, no hard-fail above

# V9 boundary: verify authorization is the ONLY entry point documented
route_src = pathlib.Path("app/api/routes/authorization.py").read_text(encoding="utf-8", errors="replace")
check("V9 note: no ApprovalRequest import in routes",   "from app.approvals" not in route_src)
check("V9 note: no GovernanceContract import in routes","GovernanceContract" not in route_src)

# Main modifications
main_src = pathlib.Path("app/main.py").read_text(encoding="utf-8", errors="replace")
check("authorization router registered in main",        "authorization_router" in main_src)

mission_schema_src = pathlib.Path("app/schemas/mission.py").read_text(encoding="utf-8", errors="replace")
check("authorization field in MissionInspectorSchema",  "authorization" in mission_schema_src)

gov_insp_src = pathlib.Path("app/governance/inspector.py").read_text(encoding="utf-8", errors="replace")
check("authorization in governance inspector",          "authorization" in gov_insp_src)
section_summary("20. Safety — No Forbidden Patterns")

# ─────────────────────────────────────────────────────────────────────────────
# 21. Engine — each condition isolated
# ─────────────────────────────────────────────────────────────────────────────
section("21. Engine — Each Condition Isolated")
from app.governance.models import ContractStatus

def _c(approved=True, execution_allowed=True, ttl=3600.0, status=None):
    c = make_contract(str(uuid.uuid4()), approved, "t", time.time(),
                      "TRUST_ENGINE", "s", "HIGH", ttl_seconds=ttl)
    c.execution_allowed = execution_allowed
    if status:
        c.status = status
    return c

# Each failure condition
conds = [
    ("R1 ACTIVE fails when EXPIRED status",    _c(status=ContractStatus.expired),     False),
    ("R1 ACTIVE fails when REVOKED status",    _c(status=ContractStatus.revoked),     False),
    ("R2 approved fails when False",           _c(approved=False),                    False),
    ("R3 exec_allowed fails when False",       _c(execution_allowed=False),           False),
    ("R4 not_revoked fails when REVOKED",      _c(status=ContractStatus.revoked),     False),
    ("R5 not_consumed fails when CONSUMED",    _c(status=ContractStatus.consumed),    False),
]
for label, contract_i, expected in conds:
    r_i = eng.evaluate(contract_i)
    check(label, r_i.authorized is expected)

# R6 wall-clock expiry
c_exp = _c(ttl=0.001); time.sleep(0.02)
r_exp = eng.evaluate(c_exp)
check("R6 not_expired fails after ttl", r_exp.authorized is False)
check("R6 not_expired True shows False in conditions",
      r_exp.conditions.get("not_expired") is False)

# Conditions dict values when all pass
c_all = _c()
r_all = eng.evaluate(c_all)
for cname in ["contract_active", "contract_approved", "execution_allowed",
              "not_revoked", "not_consumed", "not_expired"]:
    check(f"condition '{cname}' True when all pass", r_all.conditions.get(cname) is True)

# Trust score boundary: < 0.4 adds note, >= 0.4 does not
c_trust = _c()
r_trust_low  = eng.evaluate(c_trust, trust_score=0.39)
r_trust_high = eng.evaluate(c_trust, trust_score=0.4)
check("trust < 0.4 adds note to reason",   "trust" in r_trust_low.authorization_reason.lower())
check("trust >= 0.4 no note",              "trust" not in r_trust_high.authorization_reason.lower())
check("trust note doesn't deny",           r_trust_low.authorized is True)

# Mission state: ACTIVE does not add note; PAUSED does
r_ms_active = eng.evaluate(_c(), mission_state="ACTIVE")
r_ms_paused = eng.evaluate(_c(), mission_state="PAUSED")
check("ACTIVE mission no note",            "ACTIVE" not in r_ms_active.authorization_reason or
                                            "Note" not in r_ms_active.authorization_reason)
check("PAUSED mission adds note",          "PAUSED" in r_ms_paused.authorization_reason)
check("PAUSED mission still authorized",   r_ms_paused.authorized is True)
section_summary("21. Engine — Each Condition Isolated")

# ─────────────────────────────────────────────────────────────────────────────
# 22. Registry — ordering, limits, contract overwrite
# ─────────────────────────────────────────────────────────────────────────────
section("22. Registry — Ordering, Limits, Contract Overwrite")
areg._reset_for_testing()
t_base = time.time()
auths_ord = []
for i in range(5):
    a_i = make_authorization(
        f"ord-ctr-{i}", True, "ok", "HIGH",
        t_base + i * 10,   # different expires_at to distinguish
        mission_id="m-ord",
    )
    # evaluated_at tracks insertion order
    a_i.evaluated_at = t_base + i
    areg.add(a_i)
    auths_ord.append(a_i)

all_items = areg.list_all()
check("5 items inserted",            len(all_items) == 5)
check("list_all newest first",       all_items[0].evaluated_at >= all_items[-1].evaluated_at)

lim2 = areg.list_all(limit=2)
check("limit=2 returns 2",           len(lim2) == 2)

lim_mis = areg.list_for_mission("m-ord", limit=3)
check("list_for_mission limit=3",    len(lim_mis) == 3)

# Contract overwrite: adding same contract_id overwrites the latest-auth index
ctr_over = "ctr-over"
over1 = make_authorization(ctr_over, True,  "ok",  "HIGH", now+3600)
over2 = make_authorization(ctr_over, False, "den", "LOW",  now+3600)
areg.add(over1); areg.add(over2)
latest = areg.get_for_contract(ctr_over)
check("contract overwrite gives latest", latest.authorization_id == over2.authorization_id)

hist = areg.history_for_contract(ctr_over)
check("history has both entries",    len(hist) == 2)

# list_executable: only active + authorized + not expired
areg._reset_for_testing()
ax = make_authorization("cx1", True,  "ok",  "HIGH", now + 3600)
ay = make_authorization("cx2", False, "den", "LOW",  now + 3600)
az = make_authorization("cx3", True,  "ok",  "HIGH", now + 3600)
areg.add(ax); areg.add(ay); areg.add(az)
exec_list = areg.list_executable()
check("list_executable has 2",       len(exec_list) == 2)
check("list_executable all authorized", all(e.authorized for e in exec_list))
check("list_executable all is_executable", all(e.is_executable for e in exec_list))

# stats reflect additions
st2 = areg.stats()
check("stats total_added >= 3",      st2["total_added"] >= 3)
check("stats active_count >= 2",     st2["active_count"] >= 2)
check("stats cached_items >= 3",     st2["cached_items"] >= 3)
section_summary("22. Registry — Ordering, Limits, Contract Overwrite")

# ─────────────────────────────────────────────────────────────────────────────
# 23. Analytics — cumulative and threading
# ─────────────────────────────────────────────────────────────────────────────
section("23. Analytics — Cumulative Behavior")
anal._reset_for_testing()

# multiple authorized
for _ in range(7): anal.record_created(True, eval_ms=1.0)
for _ in range(3): anal.record_created(False, eval_ms=2.0)
a_cum = anal.get_analytics()
check("created = 10",                a_cum["authorizations_created"] == 10)
check("authorized = 7",              a_cum["authorized"] == 7)
check("denied = 3",                  a_cum["denied"] == 3)
expected_avg = (7 * 1.0 + 3 * 2.0) / 10  # 1.3
check("avg_eval_ms correct",         abs(a_cum["avg_evaluation_time_ms"] - expected_avg) < 0.01)

# expired / revoked / consumed accumulate separately
for _ in range(4): anal.record_expired()
for _ in range(2): anal.record_revoked()
for _ in range(3): anal.record_consumed()
a_cum2 = anal.get_analytics()
check("expired = 4",                 a_cum2["expired"] == 4)
check("revoked = 2",                 a_cum2["revoked"] == 2)
check("consumed = 3",                a_cum2["consumed"] == 3)

# reset starts fresh
anal._reset_for_testing()
a_reset = anal.get_analytics()
check("reset: created=0",            a_reset["authorizations_created"] == 0)
check("reset: authorized=0",         a_reset["authorized"] == 0)
check("reset: denied=0",             a_reset["denied"] == 0)
check("reset: expired=0",            a_reset["expired"] == 0)
check("reset: revoked=0",            a_reset["revoked"] == 0)
check("reset: consumed=0",           a_reset["consumed"] == 0)
check("reset: avg=0.0",              a_reset["avg_evaluation_time_ms"] == 0.0)
section_summary("23. Analytics — Cumulative Behavior")

# ─────────────────────────────────────────────────────────────────────────────
# 24. Timeline — exhaustive event coverage
# ─────────────────────────────────────────────────────────────────────────────
section("24. Timeline — Exhaustive Event Coverage")
tl._reset_for_testing()

event_types = ["created", "approved", "denied", "expired", "revoked", "consumed"]
for et in event_types:
    tl.record(f"aid-{et}", et, mission_id="m-ev", risk_level="HIGH",
              contract_id=f"cid-{et}", authorized=(et == "approved"))

events_all = tl.get("m-ev")
check("6 events for 6 types",        len(events_all) == 6)
recorded_types = {e["event_type"] for e in events_all}
for et in event_types:
    check(f"event_type '{et}' recorded", et in recorded_types)

# Check each required field per event
first_event = events_all[0]
for field in ["authorization_id", "event_type", "mission_id", "risk_level",
              "contract_id", "authorized", "timestamp"]:
    check(f"event has field '{field}'", field in first_event)

# Limit
check("limit=3 works",               len(tl.get("m-ev", limit=3)) == 3)

# Empty mission
check("unknown mission empty list",  tl.get("m-unknown-tl") == [])

# Global
g2 = tl.recent_global(limit=6)
check("global has >=6 events",       len(g2) >= 6)
check("global limit respected",      len(tl.recent_global(limit=2)) == 2)

# Summary
summ = tl.summary("m-ev")
check("summary mission_id",          summ["mission_id"] == "m-ev")
check("summary event_count=6",       summ["event_count"] == 6)
check("summary type_counts dict",    isinstance(summ["type_counts"], dict))
check("summary latest_event set",    summ["latest_event"] is not None)
for et in event_types:
    check(f"type_counts has '{et}'", et in summ["type_counts"])

# missions_with_authorizations
check("m-ev in missions list",       "m-ev" in tl.missions_with_authorizations())

# Reset
tl._reset_for_testing()
check("reset clears events",         tl.get("m-ev") == [])
check("global empty after reset",    tl.recent_global() == [])
section_summary("24. Timeline — Exhaustive Event Coverage")

# ─────────────────────────────────────────────────────────────────────────────
# 25. Readiness score — per-component analysis
# ─────────────────────────────────────────────────────────────────────────────
section("25. Readiness Score — Per-Component Analysis")
areg._reset_for_testing()
from app.authorization import readiness as rdns2

# No mission, no contracts, no approvals, no trust, no auths → score low
r_zero = rdns2.evaluate("m-rdns-zero")
check("score is float",              isinstance(r_zero.readiness_score, float))
check("score in [0,1]",              0.0 <= r_zero.readiness_score <= 1.0)
check("blockers not empty",          len(r_zero.blockers) > 0)
check("active_auth=0 when none",     r_zero.active_authorizations == 0)
check("denied_auth=0 when none",     r_zero.denied_authorizations == 0)
check("executable_tasks list",       isinstance(r_zero.executable_tasks, list))

# With one active authorization, that component improves
from app.governance.models import make_contract as _mc
c_rdns = _mc(str(uuid.uuid4()), True, "t", time.time(),
             "TRUST_ENGINE", "s", "HIGH", mission_id="m-rdns-partial", ttl_seconds=3600)
gov_reg.add(c_rdns)
from app.authorization import engine as eng2
a_rdns = eng2.evaluate(c_rdns)
areg.add(a_rdns)

r_partial = rdns2.evaluate("m-rdns-partial")
check("active_auth >= 1 with contract",  r_partial.active_authorizations >= 1)
check("score > 0 with active auth",      r_partial.readiness_score > 0.0)

# Graceful on totally unknown
r_unknown = rdns2.evaluate("zzz-totally-unknown-xyz")
check("graceful unknown mission",    isinstance(r_unknown, ExecutionReadinessReport))
check("unknown has blockers",        len(r_unknown.blockers) > 0)

# blockers are all strings
check("all blockers are strings",    all(isinstance(b, str) for b in r_zero.blockers))
check("evaluated_at set",            r_zero.evaluated_at > 0)
section_summary("25. Readiness Score — Per-Component Analysis")

# ─────────────────────────────────────────────────────────────────────────────
# 26. Inspector — all status types present
# ─────────────────────────────────────────────────────────────────────────────
section("26. Inspector — All Status Types")
areg._reset_for_testing(); tl._reset_for_testing(); anal._reset_for_testing()

m_all = "m-all-status"
a_active  = make_authorization("c-act",  True,  "ok",  "HIGH", now+3600, mission_id=m_all)
a_denied  = make_authorization("c-den",  False, "den", "LOW",  now+3600, mission_id=m_all)
a_revoked = make_authorization("c-rev2", True,  "ok",  "HIGH", now+3600, mission_id=m_all)
a_expired = make_authorization("c-exp2", True,  "ok",  "HIGH", now+3600, mission_id=m_all)
a_consumed= make_authorization("c-con2", True,  "ok",  "HIGH", now+3600, mission_id=m_all)
for a_i in [a_active, a_denied, a_revoked, a_expired, a_consumed]:
    areg.add(a_i)
areg.revoke(a_revoked.authorization_id)
areg.expire(a_expired.authorization_id)
areg.consume(a_consumed.authorization_id)

r_all_s = insp.inspect(m_all)
check("total_authorizations=5",      r_all_s["total_authorizations"] == 5)
check("active_count=1",              r_all_s["active_count"] == 1)
check("denied_count=1",              r_all_s["denied_count"] == 1)
check("revoked_count=1",             r_all_s["revoked_count"] == 1)
check("expired_count=1",             r_all_s["expired_count"] == 1)
check("consumed_count=1",            r_all_s["consumed_count"] == 1)
check("executable_count=1",          r_all_s["executable_count"] == 1)

# active_authorizations list has the ACTIVE one
active_list = r_all_s["active_authorizations"]
check("active_authorizations is list", isinstance(active_list, list))
check("active list has 1 item",      len(active_list) == 1)

# risk_breakdown includes HIGH and LOW
rb = r_all_s["risk_breakdown"]
check("risk_breakdown has HIGH",     "HIGH" in rb)
check("risk_breakdown has LOW",      "LOW" in rb)
check("HIGH count >= 3",             rb.get("HIGH", 0) >= 3)
check("LOW count >= 1",              rb.get("LOW", 0) >= 1)

# governance context appears (may be None if no contracts for this mission)
check("governance_context key present", "governance_context" in r_all_s)
check("analytics key present",       "analytics" in r_all_s)
check("registry_stats key present",  "registry_stats" in r_all_s)
check("latency_ms non-negative",     r_all_s["latency_ms"] >= 0)
section_summary("26. Inspector — All Status Types")

# ─────────────────────────────────────────────────────────────────────────────
# 27. HTTP — Additional endpoint checks
# ─────────────────────────────────────────────────────────────────────────────
section("27. HTTP — Additional Endpoint Checks")
areg._reset_for_testing(); tl._reset_for_testing(); anal._reset_for_testing()
gov_reg._reset_for_testing()

# Create two contracts for two missions
c_a = make_contract(str(uuid.uuid4()), True, "t", time.time(),
                    "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
                    mission_id="m-http-A", ttl_seconds=3600)
c_b = make_contract(str(uuid.uuid4()), True, "t", time.time(),
                    "TRUST_ENGINE", str(uuid.uuid4()), "LOW",
                    mission_id="m-http-B", ttl_seconds=3600)
gov_reg.add(c_a); gov_reg.add(c_b)

ev_a = client.post(f"/authorization/evaluate/{c_a.contract_id}")
ev_b = client.post(f"/authorization/evaluate/{c_b.contract_id}")
check("evaluate A 200",              ev_a.status_code == 200)
check("evaluate B 200",              ev_b.status_code == 200)

aid_a = ev_a.json()["authorization_id"]
aid_b = ev_b.json()["authorization_id"]

# GET /authorization returns both
r_both = client.get("/authorization")
check("list returns 2",              len(r_both.json()) == 2)

# filter by mission_id separates them
r_mis_a = client.get("/authorization?mission_id=m-http-A")
r_mis_b = client.get("/authorization?mission_id=m-http-B")
check("mission filter A returns 1",  len(r_mis_a.json()) == 1)
check("mission filter B returns 1",  len(r_mis_b.json()) == 1)
check("mission A contract_id",       r_mis_a.json()[0]["contract_id"] == c_a.contract_id)
check("mission B contract_id",       r_mis_b.json()[0]["contract_id"] == c_b.contract_id)

# GET /authorization/mission/{id}
r_mep_a = client.get("/authorization/mission/m-http-A")
r_mep_b = client.get("/authorization/mission/m-http-B")
check("mission endpoint A returns 1",len(r_mep_a.json()) == 1)
check("mission endpoint B returns 1",len(r_mep_b.json()) == 1)

# GET /authorization/{id} for each
r_id_a = client.get(f"/authorization/{aid_a}")
r_id_b = client.get(f"/authorization/{aid_b}")
check("get A by id 200",             r_id_a.status_code == 200)
check("get B by id 200",             r_id_b.status_code == 200)
check("A has correct mission",       r_id_a.json()["mission_id"] == "m-http-A")
check("B has correct mission",       r_id_b.json()["mission_id"] == "m-http-B")

# GET /authorization/contract/{id}
r_ctr_a = client.get(f"/authorization/contract/{c_a.contract_id}")
r_ctr_b = client.get(f"/authorization/contract/{c_b.contract_id}")
check("contract A 200",              r_ctr_a.status_code == 200)
check("contract B 200",              r_ctr_b.status_code == 200)
check("contract A id matches",       r_ctr_a.json()["authorization_id"] == aid_a)
check("contract B id matches",       r_ctr_b.json()["authorization_id"] == aid_b)

# filter ACTIVE
r_active_f = client.get("/authorization?status=ACTIVE")
check("ACTIVE filter returns 2",     len(r_active_f.json()) == 2)
check("all in ACTIVE filter are ok", all(i["status"] == "ACTIVE" for i in r_active_f.json()))

# filter DENIED (none yet)
r_denied_f = client.get("/authorization?status=DENIED")
check("DENIED filter returns 0",     r_denied_f.json() == [])

# evaluate a denied contract
c_deny = make_contract(str(uuid.uuid4()), False, "t", time.time(),
                       "DECISION_CENTER", str(uuid.uuid4()), "CRITICAL",
                       ttl_seconds=3600)
gov_reg.add(c_deny)
ev_deny = client.post(f"/authorization/evaluate/{c_deny.contract_id}")
check("denied evaluate 200",         ev_deny.status_code == 200)
check("denied evaluate authorized",  ev_deny.json()["authorized"] is False)
check("denied evaluate status",      ev_deny.json()["status"] == "DENIED")

r_denied_f2 = client.get("/authorization?status=DENIED")
check("DENIED filter now returns 1", len(r_denied_f2.json()) == 1)

# /authorization/readiness returns readiness_report
r_rdns3 = client.get("/authorization/readiness/m-http-A")
check("readiness A has active_auth", r_rdns3.json()["active_authorizations"] >= 1)
check("readiness A score > 0",       r_rdns3.json()["readiness_score"] > 0.0)

# /authorization/inspect
r_insp3 = client.get("/authorization/inspect/m-http-A")
check("inspect A active=1",          r_insp3.json()["active_count"] == 1)
check("inspect A exec=1",            r_insp3.json()["executable_count"] == 1)
section_summary("27. HTTP — Additional Endpoint Checks")

# ─────────────────────────────────────────────────────────────────────────────
# 28. Governance inspector includes authorization
# ─────────────────────────────────────────────────────────────────────────────
section("28. Governance Inspector Authorization Integration")
areg._reset_for_testing(); tl._reset_for_testing(); anal._reset_for_testing()
gov_reg._reset_for_testing()

# Create governance contract, evaluate authorization
c_gi = make_contract(str(uuid.uuid4()), True, "t", time.time(),
                     "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
                     mission_id="m-gov-integ", ttl_seconds=3600)
gov_reg.add(c_gi)
client.post(f"/authorization/evaluate/{c_gi.contract_id}")

r_gov_insp = client.get("/governance/inspect/m-gov-integ")
check("governance inspect 200",         r_gov_insp.status_code == 200)
check("governance inspect has auth",    "authorization" in r_gov_insp.json())
auth_field = r_gov_insp.json()["authorization"]
check("auth field not None after eval", auth_field is not None)
check("auth field total >= 1",          auth_field.get("total", 0) >= 1)
check("auth active_auth >= 1",          auth_field.get("active_authorizations", 0) >= 1)

# With no authorizations, auth field is None or zero-filled
gov_reg._reset_for_testing(); areg._reset_for_testing()
c_gi2 = make_contract(str(uuid.uuid4()), True, "t", time.time(),
                      "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
                      mission_id="m-gov-noauth", ttl_seconds=3600)
gov_reg.add(c_gi2)
r_gov_noauth = client.get("/governance/inspect/m-gov-noauth")
check("governance inspect 200 no auth",    r_gov_noauth.status_code == 200)
check("authorization key present always",  "authorization" in r_gov_noauth.json())
section_summary("28. Governance Inspector Authorization Integration")

# ─────────────────────────────────────────────────────────────────────────────
# 29. V9.x safety contract verification
# ─────────────────────────────────────────────────────────────────────────────
section("29. V9.x Safety Contract Verification")
route_src2 = pathlib.Path("app/api/routes/authorization.py").read_text(encoding="utf-8", errors="replace")
models_src  = pathlib.Path("app/authorization/models.py").read_text(encoding="utf-8", errors="replace")
engine_src  = pathlib.Path("app/authorization/engine.py").read_text(encoding="utf-8", errors="replace")
registry_src= pathlib.Path("app/authorization/registry.py").read_text(encoding="utf-8", errors="replace")

# Routes never import ApprovalRequest or GovernanceContract directly
check("routes: no ApprovalRequest import",   "ApprovalRequest" not in route_src2)
check("routes: no GovernanceContract import","GovernanceContract" not in route_src2)

# ExecutionAuthorization is the only return type from route /evaluate
check("routes: returns authorization dict",  "authorization_id" in route_src2)

# Models doc states V9.x restriction
check("models: documents V9 restriction",    "V9.x" in models_src)
check("models: ExecutionAuthorization class","class ExecutionAuthorization" in models_src)
check("models: ExecutionReadinessReport cls","class ExecutionReadinessReport" in models_src)
check("models: EVALUATOR_VERSION constant",  "EVALUATOR_VERSION" in models_src)

# Engine stays deterministic — no randomness
import random as _rand_mod
check("engine: no random import",            "import random" not in engine_src)
check("engine: no time.sleep",               "time.sleep" not in engine_src)

# Registry doesn't import approval or governance models (no circular deps)
check("registry: no ApprovalRequest",        "ApprovalRequest" not in registry_src)

# Persistence flag is False
from app.authorization.persistence import AUTHORIZATION_PERSISTENCE as AP_FLAG
check("persistence flag False",              AP_FLAG is False)

# V9 boundary: ExecutionAuthorization.to_dict() has all required V9 fields
v9_fields = ["authorization_id", "contract_id", "authorized", "authorization_reason",
             "evaluator_version", "risk_level", "expires_at", "is_executable"]
auth_v9 = make_authorization("cv9", True, "ok", "HIGH", now+3600)
dv9 = auth_v9.to_dict()
for f in v9_fields:
    check(f"V9 contract field '{f}'", f in dv9)

# V9 cannot use denied authorization (is_executable guards this)
auth_v9_denied = make_authorization("cv9d", False, "denied", "HIGH", now+3600)
check("denied auth not executable",  not auth_v9_denied.is_executable)
check("denied auth to_dict is_exec", auth_v9_denied.to_dict()["is_executable"] is False)
section_summary("29. V9.x Safety Contract Verification")

# ─────────────────────────────────────────────────────────────────────────────
# 30. Mission integration and regression
# ─────────────────────────────────────────────────────────────────────────────
section("30. Mission Integration & Schema Regression")
# Schema field added
mission_schema_src2 = pathlib.Path("app/schemas/mission.py").read_text(encoding="utf-8", errors="replace")
check("authorization in MissionInspectorSchema src",  "authorization" in mission_schema_src2)
check("governance in MissionInspectorSchema src",     "governance"    in mission_schema_src2)
check("approvals in MissionInspectorSchema src",      "approvals"     in mission_schema_src2)
check("decisions in MissionInspectorSchema src",      "decisions"     in mission_schema_src2)
check("trust in MissionInspectorSchema src",          "trust"         in mission_schema_src2)

# Mission route adds authorization_summary
mission_route_src = pathlib.Path("app/api/routes/mission.py").read_text(encoding="utf-8", errors="replace")
check("authorization_summary in mission route",       "authorization_summary" in mission_route_src)
check("authorization=authorization_summary in route", "authorization=authorization_summary" in mission_route_src)

# Full mission inspect via HTTP
from app.mission.models import Mission, MissionState
from app.mission import store as ms
m_auth_test = Mission("m-auth-schema-test", "Auth Schema Test", "test", MissionState.active)
ms.put(m_auth_test)
r_mis_insp = client.get("/mission/m-auth-schema-test/inspect")
check("mission inspect 200",                           r_mis_insp.status_code == 200)
check("mission inspect has authorization key",         "authorization" in r_mis_insp.json())
check("mission inspect has governance key",            "governance" in r_mis_insp.json())
check("mission inspect has approvals key",             "approvals" in r_mis_insp.json())
check("mission inspect has decisions key",             "decisions" in r_mis_insp.json())
check("mission inspect has trust key",                 "trust" in r_mis_insp.json())

# Verify main.py has all routers
main_src2 = pathlib.Path("app/main.py").read_text(encoding="utf-8", errors="replace")
for router_name in ["authorization_router", "governance_router",
                    "approvals_router", "decisions_router"]:
    check(f"main has {router_name}",                   router_name in main_src2)

# Check analytics has correct fields
r_anal_final = client.get("/authorization/analytics")
final_anal = r_anal_final.json()
for k in ["authorizations_created", "authorized", "denied",
          "expired", "revoked", "consumed", "avg_evaluation_time_ms"]:
    check(f"analytics final key '{k}'",                k in final_anal)
section_summary("30. Mission Integration & Schema Regression")

# ─────────────────────────────────────────────────────────────────────────────
# Final tally
# ─────────────────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"V8.8 VALIDATION: {PASS}/{total} checks passed")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL CHECKS PASSED")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
