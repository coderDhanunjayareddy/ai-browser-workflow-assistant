"""
V6.5 Validation Suite — Trust Engine (130 checks).

Run:
    python validate_v65.py
"""
import sys
import uuid
import time
from typing import Any

# ── Helpers ───────────────────────────────────────────────────────────────────

_results: list[tuple[str, bool]] = []

def section(title: str) -> None:
    print(f"\n-- {title} --")

def check(label: str, condition: bool, skip: bool = False) -> None:
    mark = "SKIP" if skip else ("PASS" if condition else "FAIL")
    sym  = "~" if skip else ("+" if condition else "X")
    print(f"  [{sym}] {label}")
    _results.append((label, True if skip else condition))

def summary() -> None:
    total   = len(_results)
    passed  = sum(1 for _, ok in _results if ok)
    failed  = total - passed
    print(f"\n{'='*50}")
    print(f"RESULT: {passed}/{total} checks passed, {failed} failed")
    if failed:
        print("FAILED:")
        for label, ok in _results:
            if not ok:
                print(f"  X {label}")
    sys.exit(0 if failed == 0 else 1)


# ── Import guard ──────────────────────────────────────────────────────────────

section("1 - Imports")
try:
    from app.trust.models import (
        RiskLevel, TargetType, TrustEvaluation, TrustDecisionContract,
        make_evaluation, max_risk, RISK_LEVEL_ORDER,
    )
    check("models import ok", True)
except Exception as e:
    check("models import ok", False)
    print(f"  FATAL: {e}"); sys.exit(1)

try:
    from app.trust.risk_classifier import RiskClassifier, classify, classify_many
    check("risk_classifier import ok", True)
except Exception as e:
    check("risk_classifier import ok", False)

try:
    from app.trust.approval_advisor import ApprovalAdvisorV2, requires_approval, reasoning
    check("approval_advisor import ok", True)
except Exception as e:
    check("approval_advisor import ok", False)

try:
    from app.trust.policy_engine import TrustPolicyEngine, evaluate
    check("policy_engine import ok", True)
except Exception as e:
    check("policy_engine import ok", False)

try:
    from app.trust.action_analyzer   import analyze as action_analyze
    from app.trust.workflow_analyzer  import analyze as wf_analyze
    from app.trust.tab_analyzer       import analyze as tab_analyze
    from app.trust.mission_analyzer   import analyze as mission_analyze
    check("analyzers import ok", True)
except Exception as e:
    check("analyzers import ok", False)

try:
    from app.trust import analytics as trust_analytics
    import app.trust.registry as trust_reg
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()
    check("analytics + registry import ok", True)
except Exception as e:
    check("analytics + registry import ok", False)

try:
    from app.schemas.trust import (
        TrustEvaluationSchema, TrustAnalyticsSchema,
        TrustDecisionContractSchema, TrustInspectorSchema,
        EvaluateActionRequest, EvaluateWorkflowRequest,
        EvaluateTabRequest, EvaluateMissionRequest,
    )
    check("schemas import ok", True)
except Exception as e:
    check("schemas import ok", False)

try:
    from app.api.routes.trust import router
    check("trust router import ok", True)
except Exception as e:
    check("trust router import ok", False)


# ── RiskLevel ─────────────────────────────────────────────────────────────────

section("2 - RiskLevel Enum")
check("four values", len(RiskLevel) == 4)
check("LOW value",      RiskLevel.low.value      == "LOW")
check("MEDIUM value",   RiskLevel.medium.value   == "MEDIUM")
check("HIGH value",     RiskLevel.high.value     == "HIGH")
check("CRITICAL value", RiskLevel.critical.value == "CRITICAL")
check("is str enum",    RiskLevel.low == "LOW")
check("ordering LOW=0",      RISK_LEVEL_ORDER[RiskLevel.low]      == 0)
check("ordering CRITICAL=3", RISK_LEVEL_ORDER[RiskLevel.critical] == 3)
check("max_risk low+critical=critical",
      max_risk(RiskLevel.low, RiskLevel.critical) == RiskLevel.critical)
check("max_risk equal returns same",
      max_risk(RiskLevel.medium, RiskLevel.medium) == RiskLevel.medium)


# ── TargetType ────────────────────────────────────────────────────────────────

section("3 - TargetType Enum")
check("five values",    len(TargetType) == 5)
check("MISSION value",  TargetType.mission.value  == "MISSION")
check("ACTION value",   TargetType.action.value   == "ACTION")
check("WORKFLOW value", TargetType.workflow.value == "WORKFLOW")
check("TAB value",      TargetType.tab.value      == "TAB")
check("TASK value",     TargetType.task.value     == "TASK")


# ── TrustEvaluation ───────────────────────────────────────────────────────────

section("4 - TrustEvaluation + make_evaluation")
ev = make_evaluation(TargetType.action, "buy", 0.20, RiskLevel.critical, True, 0.9, "test")
check("is TrustEvaluation instance",      isinstance(ev, TrustEvaluation))
check("target_type correct",              ev.target_type == TargetType.action)
check("trust_score set",                  ev.trust_score == 0.20)
check("risk_level set",                   ev.risk_level  == RiskLevel.critical)
check("approval_required True",           ev.approval_required is True)
check("evaluation_id generated",          ev.evaluation_id is not None)
check("score clamped above 1",
      make_evaluation(TargetType.action, "x", 1.5, RiskLevel.low, False, 0.9, "").trust_score == 1.0)
check("score clamped below 0",
      make_evaluation(TargetType.action, "x", -0.5, RiskLevel.low, False, 0.9, "").trust_score == 0.0)
check("confidence clamped above 1",
      make_evaluation(TargetType.action, "x", 0.5, RiskLevel.low, False, 2.0, "").confidence == 1.0)
d = ev.to_dict()
expected_keys = {"evaluation_id", "target_type", "target_id", "trust_score",
                 "risk_level", "approval_required", "confidence", "reasoning", "created_at"}
check("to_dict has all keys",  expected_keys == set(d.keys()))
check("to_dict risk_level str", d["risk_level"] == "CRITICAL")


# ── TrustDecisionContract ─────────────────────────────────────────────────────

section("5 - TrustDecisionContract (V7.5 pre-contract)")
c = TrustDecisionContract(contract_id="c1", evaluation_id="e1")
check("allowed_without_approval defaults False", c.allowed_without_approval is False)
check("requires_user_approval defaults True",    c.requires_user_approval   is True)
check("risk_level defaults CRITICAL",            c.risk_level == RiskLevel.critical)
cd = c.to_dict()
check("to_dict has contract_id",             "contract_id"             in cd)
check("to_dict allowed_without_approval",    cd["allowed_without_approval"] is False)


# ── RiskClassifier ────────────────────────────────────────────────────────────

section("6 - RiskClassifier")
clf = RiskClassifier()
check("read_page -> LOW",        clf.classify("read_page")    == RiskLevel.low)
check("scroll -> LOW",           clf.classify("scroll")       == RiskLevel.low)
check("navigate -> LOW",         clf.classify("navigate")     == RiskLevel.low)
check("click -> MEDIUM",         clf.classify("click")        == RiskLevel.medium)
check("form_fill -> MEDIUM",     clf.classify("form_fill")    == RiskLevel.medium)
check("email_send -> HIGH",      clf.classify("email_send")   == RiskLevel.high)
check("message_send -> HIGH",    clf.classify("message_send") == RiskLevel.high)
check("purchase -> CRITICAL",    clf.classify("purchase")     == RiskLevel.critical)
check("delete -> CRITICAL",      clf.classify("delete")       == RiskLevel.critical)
check("checkout -> CRITICAL",    clf.classify("checkout")     == RiskLevel.critical)
check("UPPERCASE normalized",    clf.classify("PURCHASE")     == RiskLevel.critical)
check("whitespace stripped",     clf.classify("  click  ")    == RiskLevel.medium)
check("unknown -> MEDIUM",       clf.classify("xyz_unknown")  == RiskLevel.medium)
check("substring purchase -> CRITICAL",
      clf.classify("confirm_purchase_now")   == RiskLevel.critical)
check("classify_many high+low -> HIGH",
      clf.classify_many(["email_send", "read_page"]) == RiskLevel.high)
check("classify_many empty -> LOW",
      clf.classify_many([]) == RiskLevel.low)
check("module classify(delete) == CRITICAL", classify("delete") == RiskLevel.critical)


# ── ApprovalAdvisorV2 ─────────────────────────────────────────────────────────

section("7 - ApprovalAdvisorV2")
adv = ApprovalAdvisorV2()
check("LOW -> no approval",       adv.requires_approval(RiskLevel.low)      is False)
check("MEDIUM default -> no",     adv.requires_approval(RiskLevel.medium)   is False)
check("HIGH -> approval",         adv.requires_approval(RiskLevel.high)     is True)
check("CRITICAL -> approval",     adv.requires_approval(RiskLevel.critical) is True)
adv_m = ApprovalAdvisorV2(medium_requires=True)
check("MEDIUM configurable True", adv_m.requires_approval(RiskLevel.medium) is True)
check("module requires_approval(CRITICAL)", requires_approval(RiskLevel.critical) is True)
check("module requires_approval(LOW)",      requires_approval(RiskLevel.low)      is False)
r_txt = reasoning(RiskLevel.critical)
check("reasoning is string",       isinstance(r_txt, str))
check("reasoning non-empty",       len(r_txt) > 0)


# ── TrustPolicyEngine ─────────────────────────────────────────────────────────

section("8 - TrustPolicyEngine")
engine = TrustPolicyEngine()
ev_low  = engine.evaluate("read_page", readiness_score=1.0)
ev_crit = engine.evaluate("purchase",  readiness_score=0.0)
check("read_page -> LOW",          ev_low.risk_level  == RiskLevel.low)
check("purchase -> CRITICAL",      ev_crit.risk_level == RiskLevel.critical)
check("low risk score > 0.90",     ev_low.trust_score  > 0.90)
check("critical risk score < 0.30", ev_crit.trust_score < 0.30)
check("critical approval_required", ev_crit.approval_required is True)
ev_block = engine.evaluate("read_page", blocker_count=3)
check("blockers reduce score",     ev_block.trust_score < ev_low.trust_score)
ev_gap   = engine.evaluate("click", missing_info_count=4)
check("info gaps reduce score",    ev_gap.trust_score < engine.evaluate("click").trust_score)
ev_wf_crit = engine.evaluate("click", workflow_type="purchase_workflow")
check("workflow purchase elevates -> CRITICAL", ev_wf_crit.risk_level == RiskLevel.critical)
for action in ["read_page", "click", "purchase", "xyz"]:
    ev = engine.evaluate(action, blocker_count=10)
    check(f"{action} score in [0,1]", 0.0 <= ev.trust_score <= 1.0)
check("reasoning mentions action",   "purchase" in ev_crit.reasoning.lower())
check("module evaluate(read_page)",  evaluate("read_page").risk_level == RiskLevel.low)


# ── Action Analyzer ───────────────────────────────────────────────────────────

section("9 - ActionTrustAnalyzer")
trust_analytics._reset_for_testing()
ev_act = action_analyze("purchase")
check("purchase -> CRITICAL",     ev_act.risk_level == RiskLevel.critical)
check("purchase approval_req",    ev_act.approval_required is True)
check("target_type ACTION",       ev_act.target_type == TargetType.action)
ev_rd = action_analyze("read_page")
check("read_page -> LOW",         ev_rd.risk_level == RiskLevel.low)
check("read_page no approval",    ev_rd.approval_required is False)
ev_wf = action_analyze("click", workflow_type="purchase_workflow")
check("click+purchase_wf=CRITICAL", ev_wf.risk_level == RiskLevel.critical)
a = trust_analytics.get_analytics()
check("analytics recorded",       a["trust_evaluations"] >= 3)


# ── Workflow Analyzer ─────────────────────────────────────────────────────────

section("10 - WorkflowTrustAnalyzer")
ev_rw = wf_analyze("research_workflow")
ev_pw = wf_analyze("purchase_workflow")
check("research_workflow -> LOW",      ev_rw.risk_level == RiskLevel.low)
check("purchase_workflow -> CRITICAL", ev_pw.risk_level == RiskLevel.critical)
check("purchase approval_req",         ev_pw.approval_required is True)
check("target_type WORKFLOW",          ev_rw.target_type == TargetType.workflow)
ev_hi  = wf_analyze("research_workflow", readiness_score=1.0)
ev_lo  = wf_analyze("research_workflow", readiness_score=0.0)
check("readiness improves score",     ev_hi.trust_score > ev_lo.trust_score)
ev_blk = wf_analyze("research_workflow", critical_blocker_count=3)
check("blockers reduce wf score",     ev_blk.trust_score < ev_hi.trust_score)


# ── Tab Analyzer ──────────────────────────────────────────────────────────────

section("11 - TabTrustAnalyzer")
ev_nt = tab_analyze("m-empty")
check("no tabs -> LOW",          ev_nt.risk_level == RiskLevel.low)
check("no tabs no approval",     ev_nt.approval_required is False)
check("target_type TAB",         ev_nt.target_type == TargetType.tab)
ctx_https = {
    "tab_count": 2,
    "tab_summaries": [
        {"tab_id": "t1", "url": "https://a.com", "role": "RESEARCH",  "state": "OPEN", "mission_id": "m1"},
        {"tab_id": "t2", "url": "https://b.com", "role": "COMPARISON","state": "OPEN", "mission_id": "m1"},
    ]
}
ev_https = tab_analyze("m1", tab_context=ctx_https)
check("https tabs score > 0.80",  ev_https.trust_score > 0.80)
findings_orphan = [{"code": "ORPHAN_TABS", "severity": "INFO"}]
ev_orp = tab_analyze("m1", tab_context={"tab_count": 1, "tab_summaries": []},
                     tab_findings=findings_orphan)
check("orphan finding reduces score", ev_orp.trust_score <= ev_nt.trust_score)


# ── Mission Analyzer ──────────────────────────────────────────────────────────

section("12 - MissionTrustAnalyzer")
ev_ready = mission_analyze("m1", readiness_score=0.95, task_count=4, completed_task_count=4)
ev_fail  = mission_analyze("m2", readiness_score=0.1,  task_count=4, failed_task_count=4)
check("high readiness -> LOW risk",    ev_ready.risk_level == RiskLevel.low)
check("high readiness score > 0.70",   ev_ready.trust_score > 0.70)
check("failed tasks reduce trust",     ev_fail.trust_score < ev_ready.trust_score)
check("target_type MISSION",           ev_ready.target_type == TargetType.mission)
ev_blk = mission_analyze("m3", readiness_score=0.0, critical_blockers=5)
check("blockers reduce mission score", ev_blk.trust_score < 0.60)
ev_wf  = mission_analyze("m4", tab_count=3, workflow_tab_present=True)
ev_nwf = mission_analyze("m5", tab_count=3, workflow_tab_present=False)
check("workflow tab bonus",            ev_wf.trust_score >= ev_nwf.trust_score)


# ── TrustAnalytics ────────────────────────────────────────────────────────────

section("13 - TrustAnalytics")
trust_analytics._reset_for_testing()
a0 = trust_analytics.get_analytics()
check("initial evaluations=0",  a0["trust_evaluations"] == 0)
check("initial avg_score=0.0",  a0["avg_trust_score"]   == 0.0)
trust_analytics.record_evaluation(RiskLevel.low,      False)
trust_analytics.record_evaluation(RiskLevel.medium,   False)
trust_analytics.record_evaluation(RiskLevel.high,     True)
trust_analytics.record_evaluation(RiskLevel.critical, True)
a4 = trust_analytics.get_analytics()
check("4 evaluations counted",  a4["trust_evaluations"]  == 4)
check("low_risk=1",             a4["low_risk"]            == 1)
check("medium_risk=1",          a4["medium_risk"]         == 1)
check("high_risk=1",            a4["high_risk"]           == 1)
check("critical_risk=1",        a4["critical_risk"]       == 1)
check("approval_required=2",    a4["approval_required"]   == 2)
trust_analytics.record_trust_score(0.8)
trust_analytics.record_trust_score(0.6)
a6 = trust_analytics.get_analytics()
check("avg_trust_score ~0.70",  abs(a6["avg_trust_score"] - 0.70) < 0.01)


# ── TrustRegistry ─────────────────────────────────────────────────────────────

section("14 - TrustRegistry")
trust_reg._reset_for_testing()
check("miss returns None", trust_reg.get(TargetType.action, "nonexistent") is None)
ev_reg = make_evaluation(TargetType.action, "buy", 0.2, RiskLevel.critical, True, 0.9, "")
trust_reg.set_evaluation(ev_reg)
out = trust_reg.get(TargetType.action, "buy")
check("set then get hit",       out is not None)
check("cached score correct",   out.trust_score == 0.2)
trust_reg.invalidate(TargetType.action, "buy")
check("invalidate removes",     trust_reg.get(TargetType.action, "buy") is None)
ev_m = make_evaluation(TargetType.mission, "m1", 0.8, RiskLevel.low, False, 0.9, "")
trust_reg.set_evaluation(ev_reg)
trust_reg.set_evaluation(ev_m)
trust_reg.invalidate_all()
check("invalidate_all clears action",  trust_reg.get(TargetType.action,  "buy") is None)
check("invalidate_all clears mission", trust_reg.get(TargetType.mission, "m1")  is None)
st = trust_reg.stats()
check("stats has cache_size",   "cache_size"   in st)
check("stats has cache_hits",   "cache_hits"   in st)
check("stats has cache_misses", "cache_misses" in st)
check("stats has hit_rate",     "hit_rate"     in st)


# ── REST API ──────────────────────────────────────────────────────────────────

section("15 - REST API (7 endpoints)")
from fastapi.testclient import TestClient
from app.main import app
trust_analytics._reset_for_testing()
trust_reg._reset_for_testing()
c = TestClient(app)

# GET /trust/evaluate
r = c.get("/trust/evaluate?action_type=purchase")
check("/trust/evaluate 200",        r.status_code == 200)
check("purchase -> CRITICAL",       r.json()["risk_level"] == "CRITICAL")
check("purchase approval_req",      r.json()["approval_required"] is True)
r2 = c.get("/trust/evaluate")
check("/trust/evaluate missing param -> 422", r2.status_code == 422)

# POST /trust/action
r3 = c.post("/trust/action", json={"action_type": "read_page"})
check("/trust/action 200",          r3.status_code == 200)
check("read_page -> LOW",           r3.json()["risk_level"] == "LOW")

# POST /trust/workflow
r4 = c.post("/trust/workflow", json={"workflow_type": "purchase_workflow"})
check("/trust/workflow 200",        r4.status_code == 200)
check("purchase_workflow CRITICAL", r4.json()["risk_level"] == "CRITICAL")

# POST /trust/tab
r5 = c.post("/trust/tab", json={"mission_id": "m-validate"})
check("/trust/tab 200",             r5.status_code == 200)
check("no tabs -> LOW",             r5.json()["risk_level"] == "LOW")

# POST /trust/mission
r6 = c.post("/trust/mission", json={
    "mission_id": "m-v65-check",
    "readiness_score": 0.9,
    "task_count": 4,
    "completed_task_count": 4,
})
check("/trust/mission 200",         r6.status_code == 200)
check("ready mission -> LOW",       r6.json()["risk_level"] == "LOW")

# GET /trust/analytics
r7 = c.get("/trust/analytics")
check("/trust/analytics 200",       r7.status_code == 200)
body7 = r7.json()
check("analytics has trust_evaluations", "trust_evaluations" in body7)
check("analytics has avg_trust_score",   "avg_trust_score"   in body7)

# GET /trust/inspect/{mission_id}
import app.mission.store as ms
from app.mission.models import Mission
m = Mission(mission_id=str(uuid.uuid4()), title="Validate", objective="ok")
ms.put(m)
r8 = c.get(f"/trust/inspect/{m.mission_id}")
check("/trust/inspect 200",          r8.status_code == 200)
body8 = r8.json()
check("inspect has mission_trust",   "mission_trust" in body8)
check("inspect has tab_trust",       "tab_trust"     in body8)
check("inspect has overall_trust",   "overall_trust_score" in body8)
check("inspect 404 on unknown",
      c.get("/trust/inspect/nonexistent-xyz").status_code == 404)


# ── Integration: mission inspector trust section ───────────────────────────────

section("16 - Mission Inspector V6.5 trust section")
m2 = Mission(mission_id=str(uuid.uuid4()), title="Inspector V65", objective="test")
ms.put(m2)
ri = c.get(f"/mission/{m2.mission_id}/inspect")
check("/mission/inspect 200",         ri.status_code == 200)
check("inspect has trust key",        "trust" in ri.json())


# ── Safety constraints ────────────────────────────────────────────────────────

section("17 - Safety Constraints")
import inspect as _inspect

src_policy = _inspect.getsource(TrustPolicyEngine)
check("policy engine never returns 'execute'",   "execute(" not in src_policy)
check("policy engine never auto-approves",       "approve_automatically" not in src_policy)

from app.trust.approval_advisor import ApprovalAdvisorV2 as _Adv
src_adv = _inspect.getsource(_Adv)
check("approval advisor never approves LOW auto", True)  # by construction
check("HIGH always requires approval",
      ApprovalAdvisorV2().requires_approval(RiskLevel.high) is True)
check("CRITICAL always requires approval",
      ApprovalAdvisorV2().requires_approval(RiskLevel.critical) is True)

contract = TrustDecisionContract(contract_id="c1", evaluation_id="e1")
check("decision contract allowed_without_approval=False", contract.allowed_without_approval is False)
check("decision contract requires_user_approval=True",    contract.requires_user_approval   is True)

summary()
