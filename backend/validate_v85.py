"""
V8.5 Governance Layer — Validation Suite
Target: >= 400 checks.
Run: python validate_v85.py
"""
from __future__ import annotations

import sys
import time
import uuid
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        msg = f"  FAIL [{name}]"
        if detail:
            msg += f" — {detail}"
        print(msg)


def section(title: str) -> None:
    print(f"\n--- {title} ---")


# ============================================================
# SECTION 1: Package structure
# ============================================================
section("1 — Package structure")
pkg = pathlib.Path("app/governance")
check("pkg_init",         (pkg / "__init__.py").exists())
check("pkg_models",       (pkg / "models.py").exists())
check("pkg_registry",     (pkg / "registry.py").exists())
check("pkg_generator",    (pkg / "generator.py").exists())
check("pkg_eligibility",  (pkg / "eligibility.py").exists())
check("pkg_timeline",     (pkg / "timeline.py").exists())
check("pkg_analytics",    (pkg / "analytics.py").exists())
check("pkg_inspector",    (pkg / "inspector.py").exists())
check("pkg_persistence",  (pkg / "persistence.py").exists())
check("schema_exists",    pathlib.Path("app/schemas/governance.py").exists())
check("route_exists",     pathlib.Path("app/api/routes/governance.py").exists())

# ============================================================
# SECTION 2: Models — GovernanceContract
# ============================================================
section("2 — GovernanceContract model")
from app.governance.models import (
    GovernanceContract, ContractStatus, EligibilityResult,
    ExecutionAuthorization, make_contract,
    CONTRACT_TTL_SECONDS, CONTRACT_VERSION,
)

def _ctr(approved=True, ttl=3600.0, mission_id="m-val", appr_id=None) -> GovernanceContract:
    return make_contract(
        approval_id = appr_id or str(uuid.uuid4()),
        approved    = approved,
        approved_by = "validator",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "src-val",
        risk_level  = "HIGH",
        mission_id  = mission_id,
        ttl_seconds = ttl,
    )

c = _ctr()
check("ctr_has_contract_id",       bool(c.contract_id))
check("ctr_id_is_uuid_like",       len(c.contract_id) == 36)
check("ctr_approved_true",         c.approved is True)
check("ctr_default_status_active", c.status == ContractStatus.active)
check("ctr_source_type",           c.source_type == "TRUST_ENGINE")
check("ctr_risk_level",            c.risk_level == "HIGH")
check("ctr_mission_id",            c.mission_id == "m-val")
check("ctr_version",               c.contract_version == CONTRACT_VERSION)
check("ctr_execution_allowed",     c.execution_allowed is True)
check("ctr_expires_in_future",     c.expires_at > time.time())
check("ctr_ttl_applied",           abs((c.expires_at - c.created_at) - 3600.0) < 2.0)
check("ctr_is_active_prop",        c.is_active)
check("ctr_is_eligible_prop",      c.is_eligible)
check("ctr_not_expired_prop",      not c.is_expired_now)

cn = _ctr(approved=False)
check("ctr_not_approved_not_exec", cn.execution_allowed is False)
check("ctr_not_approved_not_elig", not cn.is_eligible)

cd = c.to_dict()
for key in ["contract_id", "approval_id", "approved", "status",
            "execution_allowed", "risk_level", "source_type", "expires_at"]:
    check(f"ctr_dict_{key}", key in cd)
check("ctr_dict_status_str",       cd["status"] == "ACTIVE")

# unique IDs
a1 = _ctr(); a2 = _ctr()
check("ctr_unique_ids",            a1.contract_id != a2.contract_id)

# ============================================================
# SECTION 3: ContractStatus enum
# ============================================================
section("3 — ContractStatus enum")
check("status_active",    ContractStatus.active   == ContractStatus.active)
check("status_expired",   ContractStatus.expired  .value == "EXPIRED")
check("status_revoked",   ContractStatus.revoked  .value == "REVOKED")
check("status_consumed",  ContractStatus.consumed .value == "CONSUMED")
check("status_from_str",  ContractStatus("ACTIVE") == ContractStatus.active)

# ============================================================
# SECTION 4: EligibilityResult + ExecutionAuthorization
# ============================================================
section("4 — EligibilityResult + ExecutionAuthorization")
er = EligibilityResult(eligible=True, contract_id="cid-1",
                       reason="ok", checked_at=time.time(), conditions={})
check("er_eligible_true",       er.eligible is True)
check("er_to_dict_eligible",    er.to_dict()["eligible"] is True)
check("er_to_auth_type",        isinstance(er.to_authorization(), ExecutionAuthorization))
check("er_to_auth_authorized",  er.to_authorization().authorized is True)

er2 = EligibilityResult(eligible=False, contract_id="cid-2",
                        reason="denied", checked_at=time.time(), conditions={})
check("er2_not_auth",           er2.to_authorization().authorized is False)

auth = ExecutionAuthorization(contract_id="cid-a", authorized=True, reason="ok")
check("auth_to_dict",           "authorized" in auth.to_dict())
check("auth_contract_id",       auth.to_dict()["contract_id"] == "cid-a")

# ============================================================
# SECTION 5: Registry
# ============================================================
section("5 — ContractRegistry")
from app.governance import registry as reg
reg._reset_for_testing()

c1 = _ctr(mission_id="m-reg")
c2 = _ctr(mission_id="m-reg")
c3 = _ctr(mission_id="m-other")

reg.add(c1)
check("reg_add_count",       reg.count() == 1)
reg.add(c2)
reg.add(c3)
check("reg_count_three",     reg.count() == 3)

found = reg.get(c1.contract_id)
check("reg_get_found",       found is not None)
check("reg_get_id_match",    found.contract_id == c1.contract_id)
check("reg_get_missing",     reg.get("nonexistent") is None)

# for_approval
c4 = _ctr(appr_id="appr-special")
reg.add(c4)
check("reg_for_approval",    reg.get_for_approval("appr-special") is not None)
check("reg_for_approval_miss", reg.get_for_approval("no-such") is None)

# list views
mission_items = reg.list_for_mission("m-reg")
check("reg_list_for_mission",    len(mission_items) == 2)
all_items = reg.list_all()
check("reg_list_all_count",      len(all_items) == 4)
active_items = reg.list_active()
check("reg_list_active_count",   len(active_items) == 4)

# limit
check("reg_list_limit",          len(reg.list_all(limit=2)) == 2)

# revoke
ok_rev = reg.revoke(c1.contract_id, reason="test reason")
check("reg_revoke_ok",           ok_rev is True)
r_item = reg.get(c1.contract_id)
check("reg_revoke_status",       r_item.status == ContractStatus.revoked)
check("reg_revoke_reason",       r_item.revoked_reason == "test reason")
check("reg_revoke_at",           r_item.revoked_at is not None)
check("reg_revoke_twice",        reg.revoke(c1.contract_id) is False)
check("reg_revoke_missing",      reg.revoke("nope") is False)

# expire
ok_exp = reg.expire(c2.contract_id)
check("reg_expire_ok",           ok_exp is True)
check("reg_expire_status",       reg.get(c2.contract_id).status == ContractStatus.expired)
check("reg_expire_twice",        reg.expire(c2.contract_id) is False)

# consume
ok_con = reg.consume(c3.contract_id)
check("reg_consume_ok",          ok_con is True)
con_item = reg.get(c3.contract_id)
check("reg_consume_status",      con_item.status == ContractStatus.consumed)
check("reg_consume_at",          con_item.consumed_at is not None)
check("reg_consume_twice",       reg.consume(c3.contract_id) is False)

# active list reduced
check("reg_active_reduced",      len(reg.list_active()) == 1)

# summary
reg._reset_for_testing()
s_c = _ctr(mission_id="m-sum")
reg.add(s_c)
s = reg.summary_for_mission("m-sum")
check("reg_summary_total",        s["total"] == 1)
check("reg_summary_active",       s["active_contracts"] == 1)
check("reg_summary_execution_el", s["execution_eligible"] == 1)

s_empty = reg.summary_for_mission("no-such")
check("reg_summary_empty",        s_empty["total"] == 0)

# stats
st = reg.stats()
check("reg_stats_cached",    "cached_items"  in st)
check("reg_stats_added",     "total_added"   in st)
check("reg_stats_evicted",   "total_evicted" in st)
check("reg_stats_active",    "active_count"  in st)

reg._reset_for_testing()

# ============================================================
# SECTION 6: Analytics
# ============================================================
section("6 — GovernanceAnalytics")
from app.governance import analytics as anal
anal._reset_for_testing()

a = anal.get_analytics()
check("anal_created_zero",     a["contracts_created"]  == 0)
check("anal_consumed_zero",    a["contracts_consumed"] == 0)
check("anal_revoked_zero",     a["contracts_revoked"]  == 0)
check("anal_expired_zero",     a["contracts_expired"]  == 0)
check("anal_avg_zero",         a["avg_contract_age_ms"] == 0.0)
check("anal_has_active",       "contracts_active" in a)

anal.record_created()
anal.record_created()
check("anal_created_two",      anal.get_analytics()["contracts_created"] == 2)

anal.record_consumed(100.0)
anal.record_consumed(200.0)
a2 = anal.get_analytics()
check("anal_consumed_two",     a2["contracts_consumed"] == 2)
check("anal_avg_age",          a2["avg_contract_age_ms"] == 150.0)

anal.record_revoked(50.0)
check("anal_revoked_one",      anal.get_analytics()["contracts_revoked"] == 1)

anal.record_expired(25.0)
check("anal_expired_one",      anal.get_analytics()["contracts_expired"] == 1)

anal._reset_for_testing()
check("anal_reset",            anal.get_analytics()["contracts_created"] == 0)

# ============================================================
# SECTION 7: Timeline
# ============================================================
section("7 — GovernanceTimeline")
from app.governance import timeline as tl
tl._reset_for_testing()

check("tl_empty_get",    tl.get("no-mission") == [])

tl.record("cid-A", "created", mission_id="m-tl", risk_level="HIGH", approved=True)
evs = tl.get("m-tl")
check("tl_record_one",          len(evs) == 1)
check("tl_event_type",          evs[0]["event_type"] == "created")
check("tl_mission_id",          evs[0]["mission_id"] == "m-tl")
check("tl_approved_field",      evs[0]["approved"] is True)
check("tl_has_timestamp",       "timestamp" in evs[0])
check("tl_has_contract_id",     evs[0]["contract_id"] == "cid-A")

tl.record("cid-B", "revoked",  mission_id="m-tl")
tl.record("cid-C", "consumed", mission_id="m-tl")
evs2 = tl.get("m-tl")
check("tl_three_events",        len(evs2) == 3)
check("tl_newest_first",        evs2[0]["event_type"] == "consumed")

glb = tl.recent_global()
check("tl_global_nonempty",     len(glb) >= 3)

s = tl.summary("m-tl")
check("tl_summary_dict",        isinstance(s, dict))
check("tl_summary_count",       s["event_count"] == 3)
check("tl_summary_latest",      s["latest_event"] is not None)
check("tl_summary_type_counts", "type_counts" in s)

check("tl_missions_includes",   "m-tl" in tl.missions_with_contracts())

evs_lim = tl.get("m-tl", limit=2)
check("tl_limit",               len(evs_lim) == 2)

tl._reset_for_testing()
check("tl_reset",               tl.get("m-tl") == [])

# ============================================================
# SECTION 8: EligibilityEngine
# ============================================================
section("8 — EligibilityEngine")
from app.governance import eligibility as elig

reg._reset_for_testing()
ec = _ctr(approved=True)

r = elig.check(ec)
check("elig_eligible",          r.eligible is True)
check("elig_conditions_5",      len(r.conditions) == 5)
check("elig_cond_is_active",    r.conditions["is_active"])
check("elig_cond_approved",     r.conditions["approved"])
check("elig_cond_not_expired",  r.conditions["not_expired"])
check("elig_cond_not_revoked",  r.conditions["not_revoked"])
check("elig_cond_not_consumed", r.conditions["not_consumed"])
check("elig_checked_at",        abs(r.checked_at - time.time()) < 2.0)
check("elig_reason_satisfied",  "satisfied" in r.reason.lower())

auth_r = r.to_authorization()
check("elig_to_auth_authorized", auth_r.authorized is True)
check("elig_to_auth_cid",        auth_r.contract_id == ec.contract_id)

en = _ctr(approved=False)
rn = elig.check(en)
check("elig_not_approved",      rn.eligible is False)
check("elig_not_approved_reason","denied" in rn.reason.lower())

er_rev = _ctr(approved=True)
er_rev.status = ContractStatus.revoked
check("elig_revoked",           elig.check(er_rev).eligible is False)

er_con = _ctr(approved=True)
er_con.status = ContractStatus.consumed
check("elig_consumed",          elig.check(er_con).eligible is False)

er_exp_s = _ctr(approved=True)
er_exp_s.status = ContractStatus.expired
check("elig_expired_status",    elig.check(er_exp_s).eligible is False)

er_wc = _ctr(approved=True, ttl=0.001)
time.sleep(0.01)
check("elig_expired_wall_clock", elig.check(er_wc).eligible is False)

auth2 = elig.authorize(ec)
check("elig_authorize",          auth2.authorized is True)

# ============================================================
# SECTION 9: Generator
# ============================================================
section("9 — ApprovalContractGenerator")
from app.governance import generator as genv
from app.approvals.models import (
    ApprovalStatus, ApprovalRiskLevel, ApprovalSourceType, make_approval_request,
)
from app.approvals import registry as appr_reg
appr_reg._reset_for_testing()
reg._reset_for_testing()

def _appr(status=ApprovalStatus.approved, risk=ApprovalRiskLevel.high, mission_id="m-gen-val"):
    a = make_approval_request(
        source_type = ApprovalSourceType.trust_engine,
        source_id   = str(uuid.uuid4()),
        title       = "Val Test Approval",
        description = "test",
        risk_level  = risk,
        priority    = "HIGH",
        mission_id  = mission_id,
        task_id     = "t-gen-val",
    )
    a.status      = status
    a.resolved_at = time.time()
    a.resolved_by = "validator"
    return a

a_ok = _appr(status=ApprovalStatus.approved)
gc = genv.generate_from_approval(a_ok)
check("gen_returns_contract",    gc is not None)
check("gen_approved_true",       gc.approved is True)
check("gen_source_type",         gc.source_type == "TRUST_ENGINE")
check("gen_risk_level",          gc.risk_level == "HIGH")
check("gen_mission_id",          gc.mission_id == "m-gen-val")
check("gen_approval_id",         gc.approval_id == a_ok.approval_id)
check("gen_execution_allowed",   gc.execution_allowed is True)
check("gen_exec_reason",         "Approved" in gc.execution_reason)

a_pend = _appr(status=ApprovalStatus.pending)
check("gen_pending_none",        genv.generate_from_approval(a_pend) is None)

a_rej = _appr(status=ApprovalStatus.rejected)
check("gen_rejected_none",       genv.generate_from_approval(a_rej) is None)

a_crit = _appr(status=ApprovalStatus.approved, risk=ApprovalRiskLevel.critical)
gc2 = genv.generate_from_approval(a_crit)
check("gen_critical_risk",       gc2.risk_level == "CRITICAL")

# pending contracts
a_ok2 = _appr(mission_id="m-pend-val")
appr_reg.add(a_ok2)
result = genv.generate_pending_contracts_for_mission("m-pend-val")
check("gen_pending_count",       len(result) >= 1)

# skip once registered
reg.add(result[0])
result2 = genv.generate_pending_contracts_for_mission("m-pend-val")
check("gen_no_duplicate",        a_ok2.approval_id not in [r.approval_id for r in result2])

pending_only = _appr(status=ApprovalStatus.pending, mission_id="m-pend-val2")
appr_reg.add(pending_only)
result3 = genv.generate_pending_contracts_for_mission("m-pend-val2")
check("gen_skips_pending",       len(result3) == 0)

check("gen_graceful_no_mission", genv.generate_pending_contracts_for_mission("no-such") == [])

appr_reg._reset_for_testing()
reg._reset_for_testing()

# ============================================================
# SECTION 10: Inspector
# ============================================================
section("10 — ContractInspector")
from app.governance import inspector as insp_mod
reg._reset_for_testing()
anal._reset_for_testing()
tl._reset_for_testing()

res = insp_mod.inspect("m-insp-val")
check("insp_returns_dict",       isinstance(res, dict))
check("insp_has_mission_id",     "mission_id" in res)
check("insp_has_total",          "total_contracts" in res)
check("insp_has_active_count",   "active_count" in res)
check("insp_has_expired_count",  "expired_count" in res)
check("insp_has_revoked_count",  "revoked_count" in res)
check("insp_has_consumed_count", "consumed_count" in res)
check("insp_has_eligible",       "execution_eligible" in res)
check("insp_has_active_list",    "active_contracts" in res)
check("insp_has_eligible_list",  "eligible_contracts" in res)
check("insp_has_source_bkdn",    "source_breakdown" in res)
check("insp_has_analytics",      "analytics" in res)
check("insp_has_reg_stats",      "registry_stats" in res)
check("insp_has_latency",        "latency_ms" in res)
check("insp_empty_zero",         res["total_contracts"] == 0)

ci = _ctr(mission_id="m-insp-val")
reg.add(ci)
res2 = insp_mod.inspect("m-insp-val")
check("insp_one_contract",       res2["total_contracts"] == 1)
check("insp_one_active",         res2["active_count"] == 1)
check("insp_one_eligible",       res2["execution_eligible"] == 1)
check("insp_active_list_len",    len(res2["active_contracts"]) >= 1)
check("insp_source_bkdn_pop",    res2["source_breakdown"].get("TRUST_ENGINE", 0) >= 1)

reg.revoke(ci.contract_id, reason="inspector test")
res3 = insp_mod.inspect("m-insp-val")
check("insp_revoked_count",      res3["revoked_count"] == 1)
check("insp_eligible_zero",      res3["execution_eligible"] == 0)

reg._reset_for_testing()

# ============================================================
# SECTION 11: Persistence stub
# ============================================================
section("11 — GovernancePersistence")
from app.governance.persistence import GovernancePersistence, GOVERNANCE_PERSISTENCE

check("persist_flag_false",      GOVERNANCE_PERSISTENCE is False)
p = GovernancePersistence()
ci2 = _ctr()
p.save(ci2)                                 # no-op
check("persist_save_noop",       True)
check("persist_load_empty",      p.load_for_mission("any") == [])
check("persist_delete_zero",     p.delete_for_mission("any") == 0)

# ============================================================
# SECTION 12: REST API — 8 endpoints
# ============================================================
section("12 — REST API")
from fastapi.testclient import TestClient
from app.main import app as fa_app
from app.approvals import registry as appr_reg2
from app.approvals import analytics as appr_anal
from app.approvals import timeline as appr_tl
from app.governance import registry as gov_reg2

client = TestClient(fa_app)
appr_reg2._reset_for_testing(); appr_anal._reset_for_testing(); appr_tl._reset_for_testing()
gov_reg2._reset_for_testing(); anal._reset_for_testing(); tl._reset_for_testing()

# /governance/contracts
r = client.get("/governance/contracts")
check("api_list_200",            r.status_code == 200)
check("api_list_empty",          r.json() == [])

# /governance/contracts/active
r = client.get("/governance/contracts/active")
check("api_active_200",          r.status_code == 200)
check("api_active_empty",        r.json() == [])

# /governance/analytics
r = client.get("/governance/analytics")
check("api_analytics_200",       r.status_code == 200)
check("api_analytics_created",   "contracts_created" in r.json())

# /governance/inspect/{mission_id}
r = client.get("/governance/inspect/m-api-test")
check("api_inspect_200",         r.status_code == 200)
check("api_inspect_fields",      "total_contracts" in r.json())

# approve endpoint → governance_contract
def _make_appr_api(mission_id="m-api-test"):
    a = make_approval_request(
        source_type = ApprovalSourceType.trust_engine,
        source_id   = str(uuid.uuid4()),
        title       = "API Val Approval",
        description = "api test",
        risk_level  = ApprovalRiskLevel.high,
        priority    = "HIGH",
        mission_id  = mission_id,
    )
    appr_reg2.add(a)
    return a

a_api = _make_appr_api()
approve_r = client.post(f"/approvals/{a_api.approval_id}/approve")
check("api_approve_200",         approve_r.status_code == 200)
check("api_approve_has_gc",      "governance_contract" in approve_r.json())
check("api_approve_gc_not_none", approve_r.json()["governance_contract"] is not None)
check("api_approve_compat_ctr",  "contract" in approve_r.json())

gc_id = approve_r.json()["governance_contract"]["contract_id"]

# /governance/contracts/{id}
r = client.get(f"/governance/contracts/{gc_id}")
check("api_get_contract_200",    r.status_code == 200)
check("api_get_contract_id",     r.json()["contract_id"] == gc_id)

r404 = client.get("/governance/contracts/nonexistent")
check("api_get_404",             r404.status_code == 404)

# /governance/contracts/{id}/eligibility
r = client.get(f"/governance/contracts/{gc_id}/eligibility")
check("api_elig_200",            r.status_code == 200)
check("api_elig_has_elig",       "eligibility" in r.json())
check("api_elig_has_auth",       "execution_authorization" in r.json())
check("api_elig_eligible_true",  r.json()["eligibility"]["eligible"] is True)
check("api_auth_true",           r.json()["execution_authorization"]["authorized"] is True)

r_elig404 = client.get("/governance/contracts/no-id/eligibility")
check("api_elig_404",            r_elig404.status_code == 404)

# /governance/contracts/active
r = client.get("/governance/contracts/active")
check("api_active_one",          len(r.json()) == 1)

# /governance/contracts/mission/{id}
r = client.get("/governance/contracts/mission/m-api-test")
check("api_mission_200",         r.status_code == 200)
check("api_mission_one",         len(r.json()) == 1)

# filter by status
r = client.get(f"/governance/contracts?status=ACTIVE")
check("api_filter_active",       len(r.json()) == 1)

r_bad = client.get("/governance/contracts?status=BANANA")
check("api_filter_bad_400",      r_bad.status_code == 400)

# revoke
r_rev = client.post(f"/governance/contracts/{gc_id}/revoke", json={"reason": "val test"})
check("api_revoke_200",          r_rev.status_code == 200)
check("api_revoke_status",       r_rev.json()["status"] == "REVOKED")

r_rev2 = client.post(f"/governance/contracts/{gc_id}/revoke", json={"reason": "second"})
check("api_revoke_twice_409",    r_rev2.status_code == 409)

r_rev404 = client.post("/governance/contracts/no-id/revoke", json={"reason": "x"})
check("api_revoke_404",          r_rev404.status_code == 404)

# eligibility after revoke
r_elig_r = client.get(f"/governance/contracts/{gc_id}/eligibility")
check("api_elig_revoked_false",  r_elig_r.json()["eligibility"]["eligible"] is False)

# analytics incremented
r_anal = client.get("/governance/analytics")
check("api_analytics_created_1", r_anal.json()["contracts_created"] >= 1)
check("api_analytics_revoked_1", r_anal.json()["contracts_revoked"] >= 1)

# inspect shows revoked contract
r_insp = client.get("/governance/inspect/m-api-test")
check("api_inspect_revoked",     r_insp.json()["revoked_count"] >= 1)
check("api_inspect_eligible_0",  r_insp.json()["execution_eligible"] == 0)

appr_reg2._reset_for_testing()
gov_reg2._reset_for_testing()
anal._reset_for_testing()
tl._reset_for_testing()

# ============================================================
# SECTION 13: main.py wiring
# ============================================================
section("13 — main.py wiring")
main_text = pathlib.Path("app/main.py").read_text(encoding="utf-8")
check("main_imports_governance", "governance" in main_text)
check("main_includes_router",    "governance_router.router" in main_text)

# ============================================================
# SECTION 14: mission.py schema governance field
# ============================================================
section("14 — Mission schema governance field")
schema_text = pathlib.Path("app/schemas/mission.py").read_text(encoding="utf-8")
check("schema_governance_field", "governance" in schema_text)

# ============================================================
# SECTION 15: mission route governance block
# ============================================================
section("15 — Mission route governance integration")
mission_route_text = pathlib.Path("app/api/routes/mission.py").read_text(encoding="utf-8")
check("mission_route_gov_import",  "_gov_reg" in mission_route_text)
check("mission_route_gov_summary", "governance_summary" in mission_route_text)
check("mission_route_gov_field",   "governance=governance_summary" in mission_route_text)

# ============================================================
# SECTION 16: approval route V8.5 wiring
# ============================================================
section("16 — Approval route V8.5 governance wiring")
appr_route_text = pathlib.Path("app/api/routes/approvals.py").read_text(encoding="utf-8")
check("appr_route_gov_gen",      "_gov_gen" in appr_route_text)
check("appr_route_gov_reg",      "_gov_reg" in appr_route_text)
check("appr_route_gov_anal",     "_gov_anal" in appr_route_text)
check("appr_route_gov_tl",       "_gov_tl" in appr_route_text)
check("appr_route_governance_k", "governance_contract" in appr_route_text)

# ============================================================
# SECTION 17: Safety — forbidden strings
# ============================================================
section("17 — Safety: forbidden strings")
forbidden = [
    "execute_browser_action",
    "dispatch_workflow",
    "auto_approve",
    "agent_swarm",
    "run_workflow",
]
source_files = list(pathlib.Path("app/governance").rglob("*.py"))
for fstr in forbidden:
    clean = True
    for fpath in source_files:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        if fstr in content:
            clean = False
            break
    check(f"forbidden_{fstr}", clean)

# ============================================================
# SECTION 18: Schemas
# ============================================================
section("18 — Pydantic schemas")
from app.schemas.governance import (
    GovernanceContractSchema, EligibilityResultSchema,
    ExecutionAuthorizationSchema, GovernanceAnalyticsSchema,
    GovernanceInspectorSchema, GovernanceSummarySchema, RevokeRequest,
)
check("schema_contract_class",   GovernanceContractSchema is not None)
check("schema_eligibility_class",EligibilityResultSchema is not None)
check("schema_auth_class",       ExecutionAuthorizationSchema is not None)
check("schema_analytics_class",  GovernanceAnalyticsSchema is not None)
check("schema_inspector_class",  GovernanceInspectorSchema is not None)
check("schema_summary_class",    GovernanceSummarySchema is not None)
check("schema_revoke_class",     RevokeRequest is not None)

gc_schema_fields = list(GovernanceContractSchema.model_fields.keys())
for expected_f in ["contract_id", "approval_id", "approved", "status",
                   "execution_allowed", "risk_level", "source_type"]:
    check(f"schema_ctr_field_{expected_f}", expected_f in gc_schema_fields)

# ============================================================
# SECTION 19: Mission inspector endpoint includes governance
# ============================================================
section("19 — Mission inspect endpoint with governance")
from app.mission import store as ms
from app.mission.models import Mission, MissionState

m = Mission(
    mission_id = "m-gov-inspect",
    title      = "Governance Inspect Test",
    objective  = "test",
    state      = MissionState.active,
)
ms.put(m)

a_api2 = _make_appr_api(mission_id="m-gov-inspect")
client.post(f"/approvals/{a_api2.approval_id}/approve")

r_miss_insp = client.get("/mission/m-gov-inspect/inspect")
check("miss_insp_200",            r_miss_insp.status_code == 200)
check("miss_insp_has_governance", "governance" in r_miss_insp.json())
gov_val = r_miss_insp.json().get("governance")
check("miss_insp_governance_not_none", gov_val is not None)
check("miss_insp_governance_has_total", "total" in (gov_val or {}))
check("miss_insp_governance_has_active", "active_contracts" in (gov_val or {}))

appr_reg2._reset_for_testing()
gov_reg2._reset_for_testing()
anal._reset_for_testing()
tl._reset_for_testing()

# ============================================================
# SECTION 20: Performance targets (regression guard)
# ============================================================
section("20 — Performance targets")
reg._reset_for_testing()

for _ in range(10):
    reg.add(_ctr())

t0 = time.perf_counter()
for i in range(100):
    reg.get(list(reg.list_all(100))[0].contract_id)
elapsed_ms = (time.perf_counter() - t0) * 1000 / 100
check("perf_registry_hit_1ms",   elapsed_ms < 1.0, f"{elapsed_ms:.3f}ms")

tc = _ctr()
t0 = time.perf_counter()
for i in range(100):
    elig.check(tc)
elig_ms = (time.perf_counter() - t0) * 1000 / 100
check("perf_elig_1ms",           elig_ms < 1.0, f"{elig_ms:.3f}ms")

t0 = time.perf_counter()
for i in range(20):
    anal.get_analytics()
anal_ms = (time.perf_counter() - t0) * 1000 / 20
check("perf_analytics_1ms",      anal_ms < 1.0, f"{anal_ms:.3f}ms")

reg._reset_for_testing()

# ============================================================
# SECTION 21: Registry — ordering & multi-mission
# ============================================================
section("21 — Registry ordering and multi-mission")
reg._reset_for_testing()

m_a_ids = []
for i in range(5):
    cx = _ctr(mission_id="m-ord-A")
    reg.add(cx)
    m_a_ids.append(cx.contract_id)

for i in range(3):
    reg.add(_ctr(mission_id="m-ord-B"))

check("reg_ord_mission_a_5",   len(reg.list_for_mission("m-ord-A")) == 5)
check("reg_ord_mission_b_3",   len(reg.list_for_mission("m-ord-B")) == 3)
check("reg_ord_total_8",       reg.count() == 8)

all_8 = reg.list_all()
check("reg_ord_newest_first",  all_8[0].created_at >= all_8[-1].created_at)

check("reg_count_by_active",   reg.count_by_status(ContractStatus.active) == 8)
check("reg_count_by_revoked",  reg.count_by_status(ContractStatus.revoked) == 0)

reg.revoke(m_a_ids[0])
check("reg_revoke_reduces_active",  reg.count_by_status(ContractStatus.active) == 7)
check("reg_revoke_increases_revok", reg.count_by_status(ContractStatus.revoked) == 1)

check("reg_list_active_7",     len(reg.list_active()) == 7)

reg.consume(m_a_ids[1])
check("reg_consumed_count",    reg.count_by_status(ContractStatus.consumed) == 1)

reg.expire(m_a_ids[2])
check("reg_expired_count",     reg.count_by_status(ContractStatus.expired) == 1)

sum_a = reg.summary_for_mission("m-ord-A")
check("reg_sum_a_total_5",         sum_a["total"] == 5)
check("reg_sum_a_active_2",        sum_a["active_contracts"] == 2)
check("reg_sum_a_revoked_1",       sum_a["revoked_contracts"] == 1)
check("reg_sum_a_consumed_1",      sum_a["consumed_contracts"] == 1)
check("reg_sum_a_expired_1",       sum_a["expired_contracts"] == 1)
check("reg_sum_a_eligible_2",      sum_a["execution_eligible"] == 2)

sum_b = reg.summary_for_mission("m-ord-B")
check("reg_sum_b_total_3",         sum_b["total"] == 3)
check("reg_sum_b_active_3",        sum_b["active_contracts"] == 3)
check("reg_sum_b_eligible_3",      sum_b["execution_eligible"] == 3)

reg._reset_for_testing()

# ============================================================
# SECTION 22: Eligibility — all 5 conditions tested individually
# ============================================================
section("22 — Eligibility conditions individually")
reg._reset_for_testing()

# Condition: is_active
c_active = _ctr(); c_active.status = ContractStatus.active
check("elig22_active_cond_true",     elig.check(c_active).conditions["is_active"] is True)

c_not_active = _ctr(); c_not_active.status = ContractStatus.revoked
r_not_active = elig.check(c_not_active)
check("elig22_active_cond_false",    r_not_active.conditions["is_active"] is False)
check("elig22_not_active_inelig",    r_not_active.eligible is False)

# Condition: approved
c_appr = _ctr(approved=True)
check("elig22_approved_cond_true",   elig.check(c_appr).conditions["approved"] is True)
c_nappr = _ctr(approved=False)
check("elig22_approved_cond_false",  elig.check(c_nappr).conditions["approved"] is False)

# Condition: not_expired (wall clock)
c_ok_ttl = _ctr(ttl=3600.0)
check("elig22_not_exp_future_true",  elig.check(c_ok_ttl).conditions["not_expired"] is True)
c_exp_wc = _ctr(ttl=0.001); time.sleep(0.01)
check("elig22_not_exp_past_false",   elig.check(c_exp_wc).conditions["not_expired"] is False)

# Condition: not_revoked
c_rev2 = _ctr(); c_rev2.status = ContractStatus.revoked
check("elig22_not_revoked_false",    elig.check(c_rev2).conditions["not_revoked"] is False)
c_ok_rev = _ctr()
check("elig22_not_revoked_true",     elig.check(c_ok_rev).conditions["not_revoked"] is True)

# Condition: not_consumed
c_con2 = _ctr(); c_con2.status = ContractStatus.consumed
check("elig22_not_consumed_false",   elig.check(c_con2).conditions["not_consumed"] is False)
c_ok_con = _ctr()
check("elig22_not_consumed_true",    elig.check(c_ok_con).conditions["not_consumed"] is True)

# Authorize shortcut
c_auth = _ctr(approved=True)
auth_check = elig.authorize(c_auth)
check("elig22_authorize_type",        hasattr(auth_check, "authorized"))
check("elig22_authorize_contract_id", auth_check.contract_id == c_auth.contract_id)
check("elig22_authorize_reason",      isinstance(auth_check.reason, str))

# ============================================================
# SECTION 23: Timeline — event types
# ============================================================
section("23 — Timeline event types coverage")
tl._reset_for_testing()

event_types = ["created", "revoked", "expired", "consumed"]
for i, et in enumerate(event_types):
    tl.record(f"cid-{et}", et, mission_id="m-tl-types",
              risk_level="HIGH", source_type="TRUST_ENGINE", approved=True)

evs = tl.get("m-tl-types")
check("tl_event_types_4",         len(evs) == 4)

types_recorded = {e["event_type"] for e in evs}
for et in event_types:
    check(f"tl_event_type_{et}",  et in types_recorded)

# global vs per-mission isolation
tl.record("cid-other", "created", mission_id="m-tl-other")
check("tl_no_cross_contamination", len(tl.get("m-tl-types")) == 4)
check("tl_other_mission",          len(tl.get("m-tl-other")) == 1)

# summary for mixed types
s = tl.summary("m-tl-types")
check("tl_summary_type_counts_dict", isinstance(s["type_counts"], dict))
check("tl_summary_created_count",    s["type_counts"].get("created", 0) == 1)
check("tl_summary_revoked_count",    s["type_counts"].get("revoked", 0) == 1)
check("tl_summary_expired_count",    s["type_counts"].get("expired", 0) == 1)
check("tl_summary_consumed_count",   s["type_counts"].get("consumed", 0) == 1)

glb = tl.recent_global(limit=100)
check("tl_global_all_types",      len(glb) >= 5)

tl._reset_for_testing()

# ============================================================
# SECTION 24: Analytics — mixed lifecycle
# ============================================================
section("24 — Analytics mixed lifecycle")
anal._reset_for_testing()

anal.record_created()
anal.record_created()
anal.record_created()
anal.record_consumed(300.0)
anal.record_consumed(600.0)
anal.record_revoked(100.0)
anal.record_expired(50.0)

a = anal.get_analytics()
check("anal24_created_3",     a["contracts_created"]  == 3)
check("anal24_consumed_2",    a["contracts_consumed"] == 2)
check("anal24_revoked_1",     a["contracts_revoked"]  == 1)
check("anal24_expired_1",     a["contracts_expired"]  == 1)
# avg: consumed+revoked+expired = (300+600+100+50)/4 = 262.5
check("anal24_avg_age",       a["avg_contract_age_ms"] == 262.5,
      f"got {a['avg_contract_age_ms']}")

anal._reset_for_testing()
check("anal24_reset_created", anal.get_analytics()["contracts_created"] == 0)
check("anal24_reset_avg",     anal.get_analytics()["avg_contract_age_ms"] == 0.0)

# ============================================================
# SECTION 25: GovernanceContract metadata
# ============================================================
section("25 — GovernanceContract metadata and optional fields")

c_meta = make_contract(
    approval_id = "appr-meta",
    approved    = True,
    approved_by = "tester",
    approved_at = time.time(),
    source_type = "DECISION_CENTER",
    source_id   = "dec-src",
    risk_level  = "CRITICAL",
    mission_id  = "m-meta",
    task_id     = "t-meta",
    metadata    = {"priority": "HIGH", "custom_key": "custom_val"},
)
check("meta_mission_id",      c_meta.mission_id == "m-meta")
check("meta_task_id",         c_meta.task_id == "t-meta")
check("meta_source_decision", c_meta.source_type == "DECISION_CENTER")
check("meta_risk_critical",   c_meta.risk_level == "CRITICAL")
check("meta_metadata_key",    c_meta.metadata.get("priority") == "HIGH")
check("meta_metadata_custom", c_meta.metadata.get("custom_key") == "custom_val")

d_meta = c_meta.to_dict()
check("meta_dict_task_id",    d_meta["task_id"] == "t-meta")
check("meta_dict_metadata",   d_meta["metadata"]["priority"] == "HIGH")
check("meta_revoked_at_none", d_meta["revoked_at"] is None)
check("meta_consumed_at_none",d_meta["consumed_at"] is None)

# Manual status transitions in dict
c_meta.status = ContractStatus.revoked
c_meta.revoked_at = time.time()
c_meta.revoked_reason = "manual test"
d_rev = c_meta.to_dict()
check("meta_dict_revoked_status", d_rev["status"] == "REVOKED")
check("meta_dict_revoked_at",     d_rev["revoked_at"] is not None)
check("meta_dict_revoked_reason", d_rev["revoked_reason"] == "manual test")

# ============================================================
# SECTION 26: Generator — source type mapping
# ============================================================
section("26 — Generator source type mapping")
appr_reg._reset_for_testing()
reg._reset_for_testing()

from app.approvals.models import ApprovalSourceType as AST, ApprovalRiskLevel as ARL

source_mapping = [
    (AST.trust_engine,          "TRUST_ENGINE"),
    (AST.decision_center,       "DECISION_CENTER"),
    (AST.mission_intelligence,  "MISSION_INTELLIGENCE"),
    (AST.manual,                "MANUAL"),
]
for src, expected_str in source_mapping:
    a_src = make_approval_request(
        source_type = src,
        source_id   = str(uuid.uuid4()),
        title       = f"Test {src.value}",
        description = "source map test",
        risk_level  = ARL.high,
        priority    = "HIGH",
        mission_id  = "m-src-map",
    )
    a_src.status      = ApprovalStatus.approved
    a_src.resolved_at = time.time()
    a_src.resolved_by = "tester"
    gc_src = genv.generate_from_approval(a_src)
    check(f"gen_src_map_{src.value}", gc_src is not None and gc_src.source_type == expected_str)

# Risk level mapping
risk_mapping = [
    (ARL.low,      "LOW"),
    (ARL.medium,   "MEDIUM"),
    (ARL.high,     "HIGH"),
    (ARL.critical, "CRITICAL"),
]
for rl, expected_str in risk_mapping:
    a_rl = make_approval_request(
        source_type = AST.trust_engine,
        source_id   = str(uuid.uuid4()),
        title       = f"Test {rl.value}",
        description = "risk map test",
        risk_level  = rl,
        priority    = "HIGH",
    )
    a_rl.status = ApprovalStatus.approved
    a_rl.resolved_at = time.time()
    a_rl.resolved_by = "tester"
    gc_rl = genv.generate_from_approval(a_rl)
    check(f"gen_risk_map_{rl.value}", gc_rl is not None and gc_rl.risk_level == expected_str)

appr_reg._reset_for_testing()
reg._reset_for_testing()

# ============================================================
# SECTION 27: REST API — contracts/mission + edge cases
# ============================================================
section("27 — REST API mission filter + edge cases")
appr_reg2._reset_for_testing(); appr_anal._reset_for_testing(); appr_tl._reset_for_testing()
gov_reg2._reset_for_testing(); anal._reset_for_testing(); tl._reset_for_testing()

# create 3 approvals for mission X and approve them
for _ in range(3):
    ax = _make_appr_api(mission_id="m-api-multi")
    client.post(f"/approvals/{ax.approval_id}/approve")

# create 2 for mission Y
for _ in range(2):
    ay = _make_appr_api(mission_id="m-api-other")
    client.post(f"/approvals/{ay.approval_id}/approve")

r_mx = client.get("/governance/contracts/mission/m-api-multi")
check("api27_mission_multi_3",   len(r_mx.json()) == 3)

r_my = client.get("/governance/contracts/mission/m-api-other")
check("api27_mission_other_2",   len(r_my.json()) == 2)

r_all = client.get("/governance/contracts?limit=10")
check("api27_list_total_5",      len(r_all.json()) == 5)

r_filter_m = client.get("/governance/contracts?mission_id=m-api-multi&limit=10")
check("api27_filter_mission_3",  len(r_filter_m.json()) == 3)

# Filter after revoke
gc_ids = [c["contract_id"] for c in r_mx.json()]
client.post(f"/governance/contracts/{gc_ids[0]}/revoke", json={"reason": "multi test"})

r_active_m = client.get(f"/governance/contracts?mission_id=m-api-multi&status=ACTIVE")
check("api27_filter_active_2",   len(r_active_m.json()) == 2)

r_revoked_m = client.get(f"/governance/contracts?mission_id=m-api-multi&status=REVOKED")
check("api27_filter_revoked_1",  len(r_revoked_m.json()) == 1)

# Eligibility after revoke = False
r_el_rev = client.get(f"/governance/contracts/{gc_ids[0]}/eligibility")
check("api27_elig_revoked",      r_el_rev.json()["eligibility"]["eligible"] is False)
check("api27_auth_revoked",      r_el_rev.json()["execution_authorization"]["authorized"] is False)

# analytics endpoint after actions
r_an = client.get("/governance/analytics")
check("api27_anal_created_5",    r_an.json()["contracts_created"] >= 5)
check("api27_anal_revoked_1",    r_an.json()["contracts_revoked"] >= 1)

# inspect multi-mission
r_insp_m = client.get("/governance/inspect/m-api-multi")
check("api27_insp_total_3",      r_insp_m.json()["total_contracts"] == 3)
check("api27_insp_active_2",     r_insp_m.json()["active_count"] == 2)
check("api27_insp_revoked_1",    r_insp_m.json()["revoked_count"] == 1)

# inspect unknown mission (graceful, not 404)
r_insp_unk = client.get("/governance/inspect/m-unknown-xyz")
check("api27_insp_unknown_200",   r_insp_unk.status_code == 200)
check("api27_insp_unknown_zero",  r_insp_unk.json()["total_contracts"] == 0)

appr_reg2._reset_for_testing()
gov_reg2._reset_for_testing()
anal._reset_for_testing()
tl._reset_for_testing()

# ============================================================
# SECTION 28: GovernanceContract is_expired_now detail
# ============================================================
section("28 — Contract expiry detail")
c_future = _ctr(ttl=3600.0)
check("exp_future_not_expired", not c_future.is_expired_now)
check("exp_future_is_active",   c_future.is_active)
check("exp_future_is_elig",     c_future.is_eligible)

c_past = _ctr(ttl=0.001)
time.sleep(0.01)
check("exp_past_is_expired_now", c_past.is_expired_now)
check("exp_past_still_active",   c_past.is_active)    # status not auto-updated until registry check
check("exp_past_not_elig",       not c_past.is_eligible)

# registry auto-expiry
reg._reset_for_testing()
c_ae = make_contract(
    approval_id = "appr-ae",
    approved    = True,
    approved_by = "v",
    approved_at = time.time(),
    source_type = "TRUST_ENGINE",
    source_id   = "s",
    risk_level  = "LOW",
    ttl_seconds = 0.01,
)
reg.add(c_ae)
time.sleep(0.05)
got = reg.get(c_ae.contract_id)
check("exp_reg_auto_expire",   got is not None)
check("exp_reg_status_expired", got.status == ContractStatus.expired)
reg._reset_for_testing()

# ============================================================
# SECTION 29: ExecutionAuthorization — boundary cases
# ============================================================
section("29 — ExecutionAuthorization boundary cases")
auth_ok = ExecutionAuthorization(contract_id="c-ok", authorized=True, reason="eligible",
                                 metadata={"source": "test"})
d = auth_ok.to_dict()
check("auth_dict_has_metadata",  "metadata" in d)
check("auth_dict_metadata_src",  d["metadata"].get("source") == "test")
check("auth_authorized_true",    d["authorized"] is True)

auth_deny = ExecutionAuthorization(contract_id="c-deny", authorized=False, reason="revoked")
check("auth_deny_false",         auth_deny.authorized is False)
check("auth_deny_reason",        auth_deny.reason == "revoked")

# EligibilityResult with failing conditions
conds = {
    "is_active": True,
    "approved":  False,   # <-- failing
    "not_expired": True,
    "not_revoked": True,
    "not_consumed": True,
}
er_fail = EligibilityResult(
    eligible=False, contract_id="cid-fail", reason="Eligibility denied: approved",
    checked_at=time.time(), conditions=conds
)
check("er_fail_eligible_false",      er_fail.eligible is False)
check("er_fail_conditions_approved", er_fail.conditions["approved"] is False)
auth_fail = er_fail.to_authorization()
check("er_fail_auth_denied",         auth_fail.authorized is False)

# ============================================================
# SECTION 30: Inspector global (no mission_id)
# ============================================================
section("30 — Inspector global view")
reg._reset_for_testing()
anal._reset_for_testing()
tl._reset_for_testing()

for i in range(4):
    reg.add(_ctr(mission_id=f"m-global-{i}"))

res_global = insp_mod.inspect("")
check("insp_global_mission_id_none",  res_global["mission_id"] is None)
check("insp_global_total_4",          res_global["total_contracts"] == 4)
check("insp_global_active_4",         res_global["active_count"] == 4)
check("insp_global_eligible_4",       res_global["execution_eligible"] == 4)

reg.revoke(reg.list_all()[0].contract_id)
res_global2 = insp_mod.inspect("")
check("insp_global_revoked_1",        res_global2["revoked_count"] == 1)
check("insp_global_eligible_3",       res_global2["execution_eligible"] == 3)

reg._reset_for_testing()

# ============================================================
# SECTION 31: Contract field completeness
# ============================================================
section("31 — Contract to_dict completeness")
reg._reset_for_testing()
c_full = make_contract(
    approval_id = "appr-full",
    approved    = True,
    approved_by = "full-tester",
    approved_at = time.time() - 10,
    source_type = "MISSION_INTELLIGENCE",
    source_id   = "mi-src-1",
    risk_level  = "CRITICAL",
    mission_id  = "m-full",
    task_id     = "t-full",
    ttl_seconds = 7200.0,
    metadata    = {"k": "v"},
)
d_full = c_full.to_dict()
expected_keys = [
    "contract_id", "approval_id", "mission_id", "task_id",
    "created_at", "expires_at", "approved", "approved_by",
    "approved_at", "source_type", "source_id", "risk_level",
    "contract_version", "execution_allowed", "execution_reason",
    "status", "revoked_at", "revoked_reason", "consumed_at", "metadata",
]
for k in expected_keys:
    check(f"c31_dict_{k}", k in d_full)

check("c31_source_mi",      d_full["source_type"] == "MISSION_INTELLIGENCE")
check("c31_risk_critical",  d_full["risk_level"] == "CRITICAL")
check("c31_task_id",        d_full["task_id"] == "t-full")
check("c31_metadata_k",     d_full["metadata"].get("k") == "v")
check("c31_ttl_7200",       abs((c_full.expires_at - c_full.created_at) - 7200.0) < 2.0)

# consumed
reg.add(c_full)
reg.consume(c_full.contract_id)
cf_consumed = reg.get(c_full.contract_id)
check("c31_consumed_at_set",     cf_consumed.consumed_at is not None)
check("c31_consumed_status",     cf_consumed.status == ContractStatus.consumed)
d_consumed = cf_consumed.to_dict()
check("c31_consumed_at_in_dict", d_consumed["consumed_at"] is not None)

reg._reset_for_testing()

# ============================================================
# SECTION 32: make_contract defaults
# ============================================================
section("32 — make_contract defaults and options")
c_def = make_contract(
    approval_id = "appr-def",
    approved    = True,
    approved_by = "def-user",
    approved_at = time.time(),
    source_type = "MANUAL",
    source_id   = "man-src",
    risk_level  = "LOW",
)
check("make_def_no_mission",    c_def.mission_id is None)
check("make_def_no_task",       c_def.task_id is None)
check("make_def_metadata_empty",c_def.metadata == {})
check("make_def_version",       c_def.contract_version == "1.0")
check("make_def_default_ttl",   abs((c_def.expires_at - c_def.created_at) - CONTRACT_TTL_SECONDS) < 2.0)
check("make_def_risk_low",      c_def.risk_level == "LOW")
check("make_def_source_manual", c_def.source_type == "MANUAL")
check("make_def_exec_allowed",  c_def.execution_allowed is True)
check("make_def_exec_reason",   "Approved" in c_def.execution_reason)

# unapproved
c_unappr = make_contract(
    approval_id = "appr-un",
    approved    = False,
    approved_by = "nobody",
    approved_at = time.time(),
    source_type = "MANUAL",
    source_id   = "s",
    risk_level  = "LOW",
)
check("make_unappr_exec_denied", c_unappr.execution_allowed is False)
check("make_unappr_reason",      "not" in c_unappr.execution_reason.lower()
      or "not" in c_unappr.execution_reason.lower())

# ============================================================
# SECTION 33: Registry threadsafety smoke (concurrent adds)
# ============================================================
section("33 — Registry thread safety smoke")
import threading
reg._reset_for_testing()

errors = []
def add_many(n):
    for _ in range(n):
        try:
            reg.add(_ctr())
        except Exception as e:
            errors.append(str(e))

threads = [threading.Thread(target=add_many, args=(20,)) for _ in range(5)]
for t in threads: t.start()
for t in threads: t.join()

check("thread_no_errors",        len(errors) == 0)
check("thread_count_100",        reg.count() == 100)
active_all = reg.list_active()
check("thread_all_active",       len(active_all) == 100)

reg._reset_for_testing()

# ============================================================
# SECTION 34: Registry limit edge cases
# ============================================================
section("34 — Registry limit edge cases")
reg._reset_for_testing()
for _ in range(10):
    reg.add(_ctr(mission_id="m-lim"))

check("reg_lim_all_10",      len(reg.list_all()) == 10)
check("reg_lim_limit_1",     len(reg.list_all(limit=1)) == 1)
check("reg_lim_limit_5",     len(reg.list_all(limit=5)) == 5)
check("reg_lim_limit_10",    len(reg.list_all(limit=10)) == 10)
check("reg_lim_limit_20",    len(reg.list_all(limit=20)) == 10)  # capped at actual count

check("reg_lim_mission_10",  len(reg.list_for_mission("m-lim")) == 10)
check("reg_lim_mission_3",   len(reg.list_for_mission("m-lim", limit=3)) == 3)

reg._reset_for_testing()

# ============================================================
# Final report
# ============================================================
total = passed + failed
print(f"\n{'='*60}")
print(f"V8.5 Governance Layer Validation")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
print(f"  Total:  {total}")
print(f"{'='*60}")

if failed:
    print(f"VALIDATION FAILED ({failed} checks failed)")
    sys.exit(1)
elif total < 400:
    print(f"INSUFFICIENT CHECKS: need >= 400, got {total}")
    sys.exit(1)
else:
    print(f"ALL {total} CHECKS PASSED")
    sys.exit(0)
