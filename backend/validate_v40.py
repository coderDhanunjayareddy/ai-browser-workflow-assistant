"""
V4.0 Research → Workflow Intelligence Layer — Live Validation Script.

Validates all V4.0 components without requiring a running server.
Run from backend/ directory:
  PYTHONIOENCODING=utf-8 python validate_v40.py

Exit code: 0 = all checks pass, 1 = one or more failures.
"""
import sys
import time

PASS = "[PASS]"
FAIL = "[FAIL]"
SEP  = "-" * 60

results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    symbol = PASS if ok else FAIL
    print(f"  {symbol} {name}" + (f" -- {detail}" if detail else ""))
    results.append(ok)


def section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Models
# ─────────────────────────────────────────────────────────────────────────────
section("1. Intelligence Models")

try:
    from app.intelligence.models import (
        ActionType, ReadinessState, ApprovalLevel,
        ExecutionOpportunity, GoalNode, GoalTree,
        WorkflowReadiness, ExecutionPlan, WorkflowRecommendation,
        BootstrapFacts, IntelligenceResult,
    )
    check("ActionType enum values", "book" in ActionType._value2member_map_)
    check("ReadinessState enum values", "READY" in ReadinessState._value2member_map_)
    check("ApprovalLevel enum values", "HIGH_RISK" in ApprovalLevel._value2member_map_)

    opp = ExecutionOpportunity(
        detected=True, confidence=0.9, action_type=ActionType.book,
        required_entities=["destination"], missing_information=["destination"],
        workflow_candidate=True, raw_action_keywords=["book"],
    )
    check("ExecutionOpportunity instantiation", opp.detected is True)
    check("ExecutionOpportunity workflow_candidate", opp.workflow_candidate is True)

    node = GoalNode(node_id="n1", text="Book flight", parent_id=None, children=["n2"], is_leaf=False)
    check("GoalNode instantiation", node.text == "Book flight")

    tree = GoalTree(root_id="n1", nodes={"n1": node}, depth=1, leaf_count=0)
    check("GoalTree instantiation", tree.get_root() is node)

    wr = WorkflowReadiness(
        state=ReadinessState.blocked, ready_entities=[], missing_entities=["destination"],
        blocking_reason="Missing destination", readiness_score=0.0,
    )
    check("WorkflowReadiness instantiation", wr.state == ReadinessState.blocked)

    import uuid
    plan = ExecutionPlan(
        plan_id=str(uuid.uuid4())[:8], goal="book flight", workflow_type="booking_workflow",
        required_inputs=["destination"], inferred_inputs={}, missing_inputs=["destination"],
        confidence=0.5, recommended_next_action="Provide destination",
        approval_level=ApprovalLevel.requires_approval,
    )
    check("ExecutionPlan instantiation", plan.workflow_type == "booking_workflow")

    rec = WorkflowRecommendation(
        recommendation_id="r1", action="Prepare workflow", readiness=ReadinessState.ready,
        confidence=0.9, approval_level=ApprovalLevel.requires_approval, plan_id="p1",
    )
    check("WorkflowRecommendation instantiation", rec.action == "Prepare workflow")

    bf = BootstrapFacts(
        query="book a flight", goal_text=None, workflow_type="booking_workflow",
        goal_tree_summary=["Search flights", "Book ticket"],
        pre_filled_entities={}, research_topic="flight", research_summary="",
        confidence=0.9, approval_level=ApprovalLevel.requires_approval,
    )
    check("BootstrapFacts instantiation", bf.workflow_type == "booking_workflow")

    intel = IntelligenceResult(
        opportunity=opp, goal_tree=None, readiness=None, execution_plan=None,
        recommendations=[], bootstrap_facts=None, latency_ms=0,
    )
    check("IntelligenceResult instantiation", intel.latency_ms == 0)

except Exception as e:
    check("Models", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Opportunity Detector
# ─────────────────────────────────────────────────────────────────────────────
section("2. ExecutionOpportunityDetector")

try:
    from app.intelligence.opportunity_detector import ExecutionOpportunityDetector
    from app.intelligence.models import ActionType

    det = ExecutionOpportunityDetector()

    r1 = det.detect("research flights from Hyderabad to Goa")
    check("pure research not detected", r1.detected is False)
    check("pure research confidence=0", r1.confidence == 0.0)

    r2 = det.detect("book a flight to Mumbai")
    check("book keyword detected", r2.detected is True)
    check("book action_type=book", r2.action_type == ActionType.book)
    check("book workflow_candidate=True", r2.workflow_candidate is True)
    check("book required_entities has destination", "destination" in r2.required_entities)

    r3 = det.detect("buy the iPhone 15")
    check("buy keyword detected", r3.detected is True)
    check("buy action_type=purchase", r3.action_type == ActionType.purchase)

    r4 = det.detect("sign up for the newsletter")
    check("sign up detected", r4.detected is True)
    check("register action_type", r4.action_type == ActionType.register)

    r5 = det.detect("schedule a doctor appointment")
    check("schedule detected", r5.detected is True)

    r6 = det.detect("download Python 3.12")
    check("download detected", r6.detected is True)
    check("download action_type", r6.action_type == ActionType.download)

    r7 = det.detect("open amazon.com")
    check("open/navigate detected", r7.detected is True)
    check("navigate action_type", r7.action_type == ActionType.navigate)
    check("navigate not workflow_candidate", r7.workflow_candidate is False)

    r8 = det.detect("research and book cheapest flight")
    check("compound research+book detected", r8.detected is True)
    check("compound action_type=book", r8.action_type == ActionType.book)

except Exception as e:
    check("OpportunityDetector", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Goal Decomposer
# ─────────────────────────────────────────────────────────────────────────────
section("3. GoalDecomposer")

try:
    from app.intelligence.goal_decomposer import GoalDecomposer
    from app.intelligence.models import ActionType, ExecutionOpportunity

    decomp = GoalDecomposer()
    opp_book = ExecutionOpportunity(
        detected=True, confidence=0.9, action_type=ActionType.book,
        required_entities=[], missing_information=[],
        workflow_candidate=True, raw_action_keywords=["book"],
    )

    tree = decomp.decompose("flight to Mumbai", opp_book)
    check("goal tree has root", tree.root_id in tree.nodes)
    check("root text contains topic", "flight to Mumbai" in tree.get_root().text)
    check("tree depth >= 2", tree.depth >= 2)
    check("tree has leaves", tree.leaf_count > 0)
    check("leaf count matches", tree.leaf_count == len(tree.get_leaves()))

    leaves = tree.get_leaves()
    check("leaves have no children", all(n.children == [] for n in leaves))
    check("all node IDs unique", len(tree.nodes) == len(set(tree.nodes.keys())))

    # Children exist in nodes
    all_children_valid = all(
        cid in tree.nodes
        for n in tree.nodes.values()
        for cid in n.children
    )
    check("all children exist in nodes", all_children_valid)

    opp_purchase = ExecutionOpportunity(
        detected=True, confidence=0.9, action_type=ActionType.purchase,
        required_entities=[], missing_information=[],
        workflow_candidate=True, raw_action_keywords=["buy"],
    )
    tree2 = decomp.decompose("laptop", opp_purchase)
    texts = [n.text.lower() for n in tree2.nodes.values()]
    check("purchase tree has cart/checkout step", any("cart" in t or "checkout" in t for t in texts))

except Exception as e:
    check("GoalDecomposer", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: WorkflowReadinessAnalyzer
# ─────────────────────────────────────────────────────────────────────────────
section("4. WorkflowReadinessAnalyzer")

try:
    from app.intelligence.readiness_analyzer import WorkflowReadinessAnalyzer
    from app.intelligence.models import ActionType, ReadinessState, ExecutionOpportunity

    ana = WorkflowReadinessAnalyzer()

    def _opp(action_type, required):
        return ExecutionOpportunity(
            detected=True, confidence=0.9, action_type=action_type,
            required_entities=required, missing_information=[],
            workflow_candidate=True, raw_action_keywords=[],
        )

    # No requirements → READY
    r_nav = ana.analyze(_opp(ActionType.navigate, []), None, None)
    check("no requirements → READY", r_nav.state == ReadinessState.ready)
    check("no requirements score=1.0", r_nav.readiness_score == 1.0)

    # All missing → BLOCKED
    r_blocked = ana.analyze(_opp(ActionType.book, ["destination"]), None, None)
    check("missing critical → BLOCKED", r_blocked.state == ReadinessState.blocked)
    check("blocked has reason", r_blocked.blocking_reason is not None)
    check("blocked score=0.0", r_blocked.readiness_score == 0.0)

    # Session with all required
    class _FakeEntity:
        def __init__(self, name):
            self.name = name; self.aliases = []; self.metadata = {}
    class _FakeSession:
        def __init__(self, names):
            self.active_entities = {n: _FakeEntity(n) for n in names}
            self.active_goal = None

    sess_ready = _FakeSession(["destination", "date"])
    r_ready = ana.analyze(_opp(ActionType.book, ["destination", "date"]), None, sess_ready)
    check("all entities present → READY", r_ready.state == ReadinessState.ready)
    check("ready score=1.0", r_ready.readiness_score == 1.0)

    sess_partial = _FakeSession(["destination"])
    r_partial = ana.analyze(_opp(ActionType.book, ["origin", "destination", "date"]), None, sess_partial)
    check("partial entities → PARTIALLY_READY or BLOCKED", r_partial.state in (ReadinessState.partially_ready, ReadinessState.blocked))

except Exception as e:
    check("ReadinessAnalyzer", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: ApprovalPolicyAdvisor
# ─────────────────────────────────────────────────────────────────────────────
section("5. ApprovalPolicyAdvisor")

try:
    from app.intelligence.approval_advisor import ApprovalPolicyAdvisor
    from app.intelligence.models import ActionType, ApprovalLevel, ExecutionOpportunity

    adv = ApprovalPolicyAdvisor()

    def _opp_adv(action_type, detected=True):
        return ExecutionOpportunity(
            detected=detected, confidence=0.9 if detected else 0.0,
            action_type=action_type, required_entities=[], missing_information=[],
            workflow_candidate=True, raw_action_keywords=[],
        )

    check("not detected → SAFE", adv.classify(_opp_adv(ActionType.unknown, False)) == ApprovalLevel.safe)
    check("navigate → SAFE", adv.classify(_opp_adv(ActionType.navigate), "open page") == ApprovalLevel.safe)
    check("book → REQUIRES_APPROVAL", adv.classify(_opp_adv(ActionType.book), "book flight") == ApprovalLevel.requires_approval)
    check("register → REQUIRES_APPROVAL", adv.classify(_opp_adv(ActionType.register), "sign up") == ApprovalLevel.requires_approval)
    check("purchase → HIGH_RISK", adv.classify(_opp_adv(ActionType.purchase), "buy laptop") == ApprovalLevel.high_risk)
    check("communicate → HIGH_RISK", adv.classify(_opp_adv(ActionType.communicate), "send email") == ApprovalLevel.high_risk)
    check("pay phrase → HIGH_RISK override", adv.classify(_opp_adv(ActionType.book), "book and pay now") == ApprovalLevel.high_risk)
    check("delete phrase → HIGH_RISK override", adv.classify(_opp_adv(ActionType.navigate), "delete my account") == ApprovalLevel.high_risk)

except Exception as e:
    check("ApprovalAdvisor", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: ExecutionPlanBuilder
# ─────────────────────────────────────────────────────────────────────────────
section("6. ExecutionPlanBuilder")

try:
    from app.intelligence.plan_builder import ExecutionPlanBuilder
    from app.intelligence.models import (
        ActionType, ApprovalLevel, ExecutionOpportunity,
        ReadinessState, WorkflowReadiness,
    )

    bld = ExecutionPlanBuilder()

    opp_bk = ExecutionOpportunity(
        detected=True, confidence=0.9, action_type=ActionType.book,
        required_entities=["destination"], missing_information=["destination"],
        workflow_candidate=True, raw_action_keywords=["book"],
    )
    r_blocked = WorkflowReadiness(
        state=ReadinessState.blocked, ready_entities=[], missing_entities=["destination"],
        blocking_reason="Missing destination", readiness_score=0.0,
    )
    plan = bld.build("book a flight", "flight", opp_bk, r_blocked, ApprovalLevel.requires_approval)
    check("plan_id is string", isinstance(plan.plan_id, str))
    check("workflow_type=booking_workflow", plan.workflow_type == "booking_workflow")
    check("missing_inputs=['destination']", "destination" in plan.missing_inputs)
    check("confidence < 0.5 when blocked", plan.confidence < 0.5)
    check("blocked reason in recommended_next_action", "Missing destination" in plan.recommended_next_action)

    r_ready = WorkflowReadiness(
        state=ReadinessState.ready, ready_entities=["destination"], missing_entities=[],
        blocking_reason=None, readiness_score=1.0,
    )
    plan_ready = bld.build("book a flight", "flight", opp_bk, r_ready, ApprovalLevel.requires_approval)
    check("confidence >= 0.7 when ready", plan_ready.confidence >= 0.7)

except Exception as e:
    check("PlanBuilder", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: WorkflowRecommendationEngine
# ─────────────────────────────────────────────────────────────────────────────
section("7. WorkflowRecommendationEngine")

try:
    from app.intelligence.recommendation_engine import WorkflowRecommendationEngine
    from app.intelligence.models import (
        ActionType, ApprovalLevel, ExecutionPlan, ReadinessState, WorkflowReadiness,
    )

    rec_eng = WorkflowRecommendationEngine()

    plan = ExecutionPlan(
        plan_id="test-plan", goal="book flight", workflow_type="booking_workflow",
        required_inputs=["destination"], inferred_inputs={},
        missing_inputs=["destination"], confidence=0.3,
        recommended_next_action="Provide destination",
        approval_level=ApprovalLevel.requires_approval,
    )
    readiness_blocked = WorkflowReadiness(
        state=ReadinessState.blocked, ready_entities=[], missing_entities=["destination"],
        blocking_reason="Missing destination", readiness_score=0.0,
    )
    recs = rec_eng.generate(plan, readiness_blocked)
    check("at least 1 recommendation", len(recs) >= 1)
    check("max 3 recommendations", len(recs) <= 3)
    check("primary plan_id matches", recs[0].plan_id == "test-plan")
    check("blocked has missing-info rec", len(recs) >= 2)

    plan_ready = ExecutionPlan(
        plan_id="ready-plan", goal="book flight", workflow_type="booking_workflow",
        required_inputs=[], inferred_inputs={}, missing_inputs=[],
        confidence=0.95, recommended_next_action="Launch workflow",
        approval_level=ApprovalLevel.high_risk,
    )
    readiness_ready = WorkflowReadiness(
        state=ReadinessState.ready, ready_entities=[], missing_entities=[],
        blocking_reason=None, readiness_score=1.0,
    )
    recs_ready = rec_eng.generate(plan_ready, readiness_ready)
    check("ready state produces recs", len(recs_ready) >= 1)
    ids = [r.recommendation_id for r in recs_ready]
    check("all recommendation_ids unique", len(ids) == len(set(ids)))

except Exception as e:
    check("RecommendationEngine", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 8: WorkflowBootstrapGenerator
# ─────────────────────────────────────────────────────────────────────────────
section("8. WorkflowBootstrapGenerator")

try:
    from app.intelligence.bootstrap_generator import WorkflowBootstrapGenerator
    from app.intelligence.models import (
        ActionType, ApprovalLevel, ExecutionOpportunity, ExecutionPlan,
        ReadinessState, WorkflowReadiness,
    )
    from app.intelligence.goal_decomposer import GoalDecomposer

    gen = WorkflowBootstrapGenerator()
    opp_bt = ExecutionOpportunity(
        detected=True, confidence=0.9, action_type=ActionType.book,
        required_entities=["destination"], missing_information=[],
        workflow_candidate=True, raw_action_keywords=["book"],
    )
    tree = GoalDecomposer().decompose("flight", opp_bt)
    plan_bt = ExecutionPlan(
        plan_id="bt-plan", goal="book flight", workflow_type="booking_workflow",
        required_inputs=["destination"], inferred_inputs={"destination": "Mumbai"},
        missing_inputs=[], confidence=0.95,
        recommended_next_action="Launch workflow",
        approval_level=ApprovalLevel.requires_approval,
        goal_tree=tree,
    )

    bf = gen.generate(
        query="book a flight to Mumbai",
        execution_plan=plan_bt,
        research_topic="flight to Mumbai",
        research_summary="Flights are available from ₹3000.",
    )
    check("bootstrap query preserved", bf.query == "book a flight to Mumbai")
    check("bootstrap workflow_type=booking_workflow", bf.workflow_type == "booking_workflow")
    check("bootstrap research_topic set", bf.research_topic == "flight to Mumbai")
    check("bootstrap research_summary set", "₹3000" in bf.research_summary)
    check("bootstrap pre_filled has destination", "destination" in bf.pre_filled_entities)
    check("bootstrap goal_tree_summary non-empty", len(bf.goal_tree_summary) > 0)
    check("bootstrap goal_text None when no session", bf.goal_text is None)
    check("bootstrap confidence=0.95", bf.confidence == 0.95)
    check("bootstrap approval=REQUIRES_APPROVAL", bf.approval_level == ApprovalLevel.requires_approval)

    # With session that has goal
    class _FE:
        def __init__(self, n):
            self.name = n; self.aliases = []; self.metadata = {}
    class _FS:
        def __init__(self):
            self.active_entities = {"origin": _FE("origin")}
            self.active_goal = type("G", (), {"goal_text": "Find cheapest flight", "status": type("S", (), {"value": "active"})()})()

    bf2 = gen.generate("q", plan_bt, "t", "s", cognitive_session=_FS())
    check("bootstrap goal_text from session", bf2.goal_text == "Find cheapest flight")
    check("bootstrap merges session entities", "origin" in bf2.pre_filled_entities)

except Exception as e:
    check("BootstrapGenerator", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 9: Intelligence Engine
# ─────────────────────────────────────────────────────────────────────────────
section("9. Intelligence Engine (end-to-end)")

try:
    from app.intelligence.engine import run_intelligence
    from app.intelligence.models import ReadinessState, ApprovalLevel

    # Pure research
    r1 = run_intelligence("research flights", "flights", "Summary text")
    check("pure research: not detected", r1.opportunity.detected is False)
    check("pure research: no plan", r1.execution_plan is None)
    check("pure research: no bootstrap", r1.bootstrap_facts is None)
    check("pure research: latency_ms is int", isinstance(r1.latency_ms, int))

    # Book with no session → blocked
    r2 = run_intelligence("book a flight to Goa", "flight to Goa", "Flights from ₹3000")
    check("book: detected", r2.opportunity.detected is True)
    check("book: plan built", r2.execution_plan is not None)
    check("book: readiness BLOCKED (no entities)", r2.readiness.state == ReadinessState.blocked)
    check("book: recommendations non-empty", len(r2.recommendations) >= 1)
    check("book: bootstrap facts set", r2.bootstrap_facts is not None)
    check("book: approval=REQUIRES_APPROVAL", r2.execution_plan.approval_level == ApprovalLevel.requires_approval)

    # Purchase → HIGH_RISK
    r3 = run_intelligence("buy iPhone 15", "iPhone 15", "")
    check("purchase: HIGH_RISK", r3.execution_plan.approval_level == ApprovalLevel.high_risk)

    # Navigate → SAFE
    r4 = run_intelligence("open amazon.com", "amazon", "")
    check("navigate: SAFE", r4.execution_plan.approval_level == ApprovalLevel.safe)

    # Pay phrase → HIGH_RISK override
    r5 = run_intelligence("book and pay now for ticket", "ticket", "")
    check("pay phrase: HIGH_RISK", r5.execution_plan.approval_level == ApprovalLevel.high_risk)

except Exception as e:
    check("IntelligenceEngine", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 10: Analytics
# ─────────────────────────────────────────────────────────────────────────────
section("10. Intelligence Analytics")

try:
    from app.intelligence import analytics as ia
    ia._reset_for_testing()

    ia.record_opportunity_detected()
    ia.record_opportunity_detected()
    ia.record_research_only()
    ia.record_recommendations(3)
    ia.record_plan_built()
    ia.record_bootstrap_generated()
    ia.record_readiness("READY")
    ia.record_readiness("BLOCKED")
    ia.record_readiness("PARTIALLY_READY")
    ia.record_approval("SAFE")
    ia.record_approval("REQUIRES_APPROVAL")
    ia.record_approval("HIGH_RISK")
    ia.record_workflow_conversion()

    data = ia.get_analytics()
    check("opportunities_detected=2", data["opportunities_detected"] == 2)
    check("research_only_count=1", data["research_only_count"] == 1)
    check("recommendations_generated=3", data["recommendations_generated"] == 3)
    check("plans_built=1", data["plans_built"] == 1)
    check("bootstrap_generated=1", data["bootstrap_generated"] == 1)
    check("ready_count=1", data["readiness_distribution"]["ready"] == 1)
    check("blocked_count=1", data["readiness_distribution"]["blocked"] == 1)
    check("partially_ready_count=1", data["readiness_distribution"]["partially_ready"] == 1)
    check("safe_count=1", data["approval_distribution"]["safe"] == 1)
    check("requires_approval_count=1", data["approval_distribution"]["requires_approval"] == 1)
    check("high_risk_count=1", data["approval_distribution"]["high_risk"] == 1)
    check("workflow_conversions=1", data["workflow_conversions"] == 1)

    # Research analytics extension
    from app.research import analytics as ra
    ra._reset_for_testing()
    ra.record_intelligence_run(opportunity_detected=True, recommendation_count=2, is_blocked=True)
    ra.record_intelligence_run(opportunity_detected=False, recommendation_count=0, is_blocked=False)
    rdata = ra.get_analytics()
    check("research analytics intelligence_runs=2", rdata["intelligence_layer"]["intelligence_runs"] == 2)
    check("research analytics opportunities=1", rdata["intelligence_layer"]["execution_opportunities_detected"] == 1)
    check("research analytics recommendations=2", rdata["intelligence_layer"]["execution_recommendations_generated"] == 2)
    check("research analytics blocked=1", rdata["intelligence_layer"]["blocked_workflows"] == 1)

except Exception as e:
    check("Analytics", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Section 11: Schemas
# ─────────────────────────────────────────────────────────────────────────────
section("11. API Schemas (assist.py)")

try:
    from app.schemas.assist import (
        ExecutionOpportunitySchema, WorkflowReadinessSchema,
        GoalNodeSchema, GoalTreeSchema,
        ExecutionPlanSchema, WorkflowRecommendationSchema,
        BootstrapFactsSchema, IntelligenceLayerSchema, AssistResponse,
    )

    opp_s = ExecutionOpportunitySchema(
        detected=True, confidence=0.9, action_type="book",
        required_entities=["destination"], missing_information=["destination city"],
        workflow_candidate=True,
    )
    check("ExecutionOpportunitySchema instantiation", opp_s.detected is True)

    rn_s = WorkflowReadinessSchema(
        state="BLOCKED", ready_entities=[], missing_entities=["destination"],
        blocking_reason="Missing destination", readiness_score=0.0,
    )
    check("WorkflowReadinessSchema instantiation", rn_s.state == "BLOCKED")

    node_s = GoalNodeSchema(node_id="n1", text="Book flight", parent_id=None, children=[], is_leaf=True)
    tree_s = GoalTreeSchema(root_id="n1", nodes={"n1": node_s}, depth=1, leaf_count=1)
    check("GoalTreeSchema instantiation", tree_s.root_id == "n1")

    plan_s = ExecutionPlanSchema(
        plan_id="p1", goal="book flight", workflow_type="booking_workflow",
        required_inputs=["destination"], inferred_inputs={}, missing_inputs=["destination"],
        confidence=0.3, recommended_next_action="Provide destination",
        approval_level="REQUIRES_APPROVAL",
    )
    check("ExecutionPlanSchema instantiation", plan_s.workflow_type == "booking_workflow")

    rec_s = WorkflowRecommendationSchema(
        recommendation_id="r1", action="Prepare workflow", readiness="BLOCKED",
        confidence=0.3, approval_level="REQUIRES_APPROVAL", plan_id="p1",
    )
    check("WorkflowRecommendationSchema instantiation", rec_s.action == "Prepare workflow")

    bf_s = BootstrapFactsSchema(
        query="book flight", goal_text=None, workflow_type="booking_workflow",
        goal_tree_summary=["Step 1"], pre_filled_entities={},
        research_topic="flight", research_summary="Summary",
        confidence=0.9, approval_level="REQUIRES_APPROVAL",
    )
    check("BootstrapFactsSchema instantiation", bf_s.confidence == 0.9)

    intel_s = IntelligenceLayerSchema(
        opportunity=opp_s, readiness=rn_s, execution_plan=plan_s,
        goal_tree=tree_s, recommendations=[rec_s], bootstrap_facts=bf_s, latency_ms=2,
    )
    check("IntelligenceLayerSchema instantiation", intel_s.latency_ms == 2)

    # AssistResponse now has intelligence field
    import inspect
    fields = AssistResponse.model_fields
    check("AssistResponse has intelligence field", "intelligence" in fields)
    check("intelligence field is optional", fields["intelligence"].is_required() is False)

except Exception as e:
    check("Schemas", False, str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
failed = total - passed

print(f"\n{SEP}")
print(f"  V4.0 Validation: {passed}/{total} checks passed  ({failed} failed)")
print(SEP)

if failed:
    print("  RESULT: FAILED")
    sys.exit(1)
else:
    print("  RESULT: ALL PASSED")
    sys.exit(0)
