"""
V9.0 Execution Planning Layer — Validation Suite.

Minimum 600 checks across 24 sections.
Run: python validate_v90.py
"""
import sys
import time
import uuid
import pathlib

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
    print(f"  -> {PASS - prev[1]} pass, {FAIL - prev[2]} fail")


from app.execution_planning import (
    registry as preg, analytics as panal, timeline as ptl, planner as pplanner,
    validator as pvalidator, rollback as prollback, inspector as pinsp,
)
from app.execution_planning.models import (
    PlanStatus, ExecutionMode, ActionType, TargetType, ValidationStrategy,
    RollbackAction, ExecutionStep, ExecutionPlan, PlanValidationResult,
    ACTION_PROFILE, MUTATING_ACTIONS, VALID_EXECUTION_MODES, PLANNER_VERSION,
    PLANNING_ASSIGNABLE_STATUSES, GATEWAY_ONLY_STATUSES, make_step, make_plan,
)
from app.authorization.models import make_authorization
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


def _reset_all():
    preg._reset_for_testing(); panal._reset_for_testing(); ptl._reset_for_testing()
    auth_reg._reset_for_testing(); mission_store._reset_for_testing()


def _auth(risk="HIGH", mission="m-1", task="t-1", authorized=True):
    a = make_authorization("ctr-1", authorized, "ok", risk, time.time() + 3600,
                           mission_id=mission, task_id=task)
    auth_reg.add(a)
    return a


def _mission(mid="m-1", active=True, tasks=("t-1",)):
    state = MissionState.active if active else MissionState.paused
    m = Mission(mid, "t", "research objective", state, task_ids=list(tasks))
    mission_store.put(m)
    return m


# ─────────────────────────────────────────────────────────────────────────────
# 1. Package structure
# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
for f in [
    "app/execution_planning/__init__.py",
    "app/execution_planning/models.py",
    "app/execution_planning/planner.py",
    "app/execution_planning/validator.py",
    "app/execution_planning/registry.py",
    "app/execution_planning/timeline.py",
    "app/execution_planning/analytics.py",
    "app/execution_planning/rollback.py",
    "app/execution_planning/inspector.py",
    "app/execution_planning/persistence.py",
    "app/schemas/execution_planning.py",
    "app/api/routes/plans.py",
]:
    check(f"file exists: {f}", pathlib.Path(f).exists())
section_summary("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
# 2. PlanStatus enum
# ─────────────────────────────────────────────────────────────────────────────
section("2. PlanStatus Enum")
check("6 statuses", len(PlanStatus) == 6)
for st, val in [(PlanStatus.draft, "DRAFT"), (PlanStatus.ready, "READY"),
                (PlanStatus.executing, "EXECUTING"), (PlanStatus.completed, "COMPLETED"),
                (PlanStatus.failed, "FAILED"), (PlanStatus.aborted, "ABORTED")]:
    check(f"PlanStatus {val}", st.value == val)
check("from string READY", PlanStatus("READY") == PlanStatus.ready)
check("planning assignable has draft", PlanStatus.draft in PLANNING_ASSIGNABLE_STATUSES)
check("planning assignable has ready", PlanStatus.ready in PLANNING_ASSIGNABLE_STATUSES)
check("planning assignable has aborted", PlanStatus.aborted in PLANNING_ASSIGNABLE_STATUSES)
check("gateway-only has executing", PlanStatus.executing in GATEWAY_ONLY_STATUSES)
check("gateway-only has completed", PlanStatus.completed in GATEWAY_ONLY_STATUSES)
check("gateway-only has failed", PlanStatus.failed in GATEWAY_ONLY_STATUSES)
check("assignable disjoint from gateway", PLANNING_ASSIGNABLE_STATUSES.isdisjoint(GATEWAY_ONLY_STATUSES))
section_summary("2. PlanStatus Enum")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Execution mode / action / target / validation / rollback enums
# ─────────────────────────────────────────────────────────────────────────────
section("3. Mode / Action / Target Enums")
check("3 execution modes", len(ExecutionMode) == 3)
check("mode SEQUENTIAL", ExecutionMode.sequential.value == "SEQUENTIAL")
check("mode ATOMIC", ExecutionMode.atomic.value == "ATOMIC")
check("mode DRY_RUN", ExecutionMode.dry_run.value == "DRY_RUN")
check("VALID_EXECUTION_MODES = 3", len(VALID_EXECUTION_MODES) == 3)
check("8 action types", len(ActionType) == 8)
for at, val in [(ActionType.navigate, "NAVIGATE"), (ActionType.read, "READ"),
                (ActionType.extract, "EXTRACT"), (ActionType.input, "INPUT"),
                (ActionType.click, "CLICK"), (ActionType.scroll, "SCROLL"),
                (ActionType.wait, "WAIT"), (ActionType.validate, "VALIDATE")]:
    check(f"ActionType {val}", at.value == val)
check("6 target types", len(TargetType) == 6)
for tt, val in [(TargetType.url, "URL"), (TargetType.element, "ELEMENT"),
                (TargetType.page, "PAGE"), (TargetType.tab, "TAB"),
                (TargetType.form, "FORM"), (TargetType.region, "REGION")]:
    check(f"TargetType {val}", tt.value == val)
check("5 validation strategies", len(ValidationStrategy) == 5)
check("5 rollback actions", len(RollbackAction) == 5)
check("PLANNER_VERSION 1.0", PLANNER_VERSION == "1.0")
section_summary("3. Mode / Action / Target Enums")

# ─────────────────────────────────────────────────────────────────────────────
# 4. ACTION_PROFILE + mutating actions
# ─────────────────────────────────────────────────────────────────────────────
section("4. Action Profile")
for at in ActionType:
    check(f"profile has {at.value}", at in ACTION_PROFILE)
    prof = ACTION_PROFILE[at]
    for key in ["duration_ms", "validation", "rollback", "mutating"]:
        check(f"{at.value} profile has {key}", key in prof)
    check(f"{at.value} duration > 0", prof["duration_ms"] > 0)
check("navigate mutating", ACTION_PROFILE[ActionType.navigate]["mutating"] is True)
check("extract not mutating", ACTION_PROFILE[ActionType.extract]["mutating"] is False)
check("read not mutating", ACTION_PROFILE[ActionType.read]["mutating"] is False)
check("navigate in MUTATING_ACTIONS", ActionType.navigate in MUTATING_ACTIONS)
check("click in MUTATING_ACTIONS", ActionType.click in MUTATING_ACTIONS)
check("input in MUTATING_ACTIONS", ActionType.input in MUTATING_ACTIONS)
check("scroll in MUTATING_ACTIONS", ActionType.scroll in MUTATING_ACTIONS)
check("extract not in MUTATING_ACTIONS", ActionType.extract not in MUTATING_ACTIONS)
check("validate not in MUTATING_ACTIONS", ActionType.validate not in MUTATING_ACTIONS)
section_summary("4. Action Profile")

# ─────────────────────────────────────────────────────────────────────────────
# 5. ExecutionStep
# ─────────────────────────────────────────────────────────────────────────────
section("5. ExecutionStep")
s = make_step(1, ActionType.navigate, TargetType.url, "http://a", parameters={"url": "http://a"})
check("step id prefix", s.step_id.startswith("step-"))
check("order", s.order == 1)
check("action type", s.action_type == ActionType.navigate)
check("target type", s.target_type == TargetType.url)
check("default validation url_match", s.validation_strategy == ValidationStrategy.url_match)
check("default rollback navigate_back", s.rollback_action == RollbackAction.navigate_back)
check("is_mutating True", s.is_mutating is True)
check("requires_rollback True", s.requires_rollback is True)
check("has_rollback True", s.has_rollback is True)
s_ro = make_step(2, ActionType.extract, TargetType.region, "content")
check("extract not mutating", s_ro.is_mutating is False)
check("extract not requires rollback", s_ro.requires_rollback is False)
check("extract no rollback", s_ro.has_rollback is False)
s_norb = make_step(3, ActionType.click, TargetType.element, "btn", rollback_action=RollbackAction.none)
check("click override rollback none", s_norb.rollback_action == RollbackAction.none)
check("click without rollback has_rollback False", s_norb.has_rollback is False)
sd = s.to_dict()
for k in ["step_id", "order", "action_type", "target_type", "target_description",
          "parameters", "expected_result", "validation_strategy", "rollback_action",
          "approval_scope", "is_mutating", "requires_rollback", "has_rollback"]:
    check(f"step.to_dict has {k}", k in sd)
check("step.to_dict action string", sd["action_type"] == "NAVIGATE")
check("step.to_dict target string", sd["target_type"] == "URL")
check("step ids unique", make_step(1, ActionType.read, TargetType.page, "p").step_id !=
                          make_step(1, ActionType.read, TargetType.page, "p").step_id)
section_summary("5. ExecutionStep")

# ─────────────────────────────────────────────────────────────────────────────
# 6. ExecutionPlan
# ─────────────────────────────────────────────────────────────────────────────
section("6. ExecutionPlan")
steps = [
    make_step(1, ActionType.navigate, TargetType.url, "u", parameters={"url": "u"}),
    make_step(2, ActionType.extract, TargetType.region, "c"),
]
plan = make_plan("auth-1", mission_id="m-1", task_id="t-1", created_at=100.0,
                 execution_mode=ExecutionMode.atomic, steps=steps,
                 estimated_duration_ms=1200, rollback_supported=True, confidence=0.8)
check("plan id prefix", plan.plan_id.startswith("plan-"))
check("authorization_id", plan.authorization_id == "auth-1")
check("mission_id", plan.mission_id == "m-1")
check("task_id", plan.task_id == "t-1")
check("created_at", plan.created_at == 100.0)
check("planner_version", plan.planner_version == PLANNER_VERSION)
check("execution_mode atomic", plan.execution_mode == ExecutionMode.atomic)
check("estimated_steps 2", plan.estimated_steps == 2)
check("estimated_duration", plan.estimated_duration_ms == 1200)
check("rollback_supported", plan.rollback_supported is True)
check("confidence", plan.confidence == 0.8)
check("status draft", plan.status == PlanStatus.draft)
check("is_ready False", plan.is_ready is False)
check("mutating_step_count 1", plan.mutating_step_count == 1)
plan.status = PlanStatus.ready
check("is_ready True after ready", plan.is_ready is True)
pd = plan.to_dict()
for k in ["plan_id", "authorization_id", "mission_id", "task_id", "created_at",
          "planner_version", "execution_mode", "estimated_steps",
          "estimated_duration_ms", "rollback_supported", "confidence", "status",
          "mutating_step_count", "is_ready", "steps"]:
    check(f"plan.to_dict has {k}", k in pd)
check("plan.to_dict mode string", pd["execution_mode"] == "ATOMIC")
check("plan.to_dict no steps when excluded", "steps" not in plan.to_dict(include_steps=False))
check("plan ids unique", make_plan("a", mission_id="m", task_id="t", created_at=1.0,
        execution_mode=ExecutionMode.sequential, steps=steps, estimated_duration_ms=1,
        rollback_supported=True, confidence=0.5).plan_id !=
        make_plan("a", mission_id="m", task_id="t", created_at=1.0,
        execution_mode=ExecutionMode.sequential, steps=steps, estimated_duration_ms=1,
        rollback_supported=True, confidence=0.5).plan_id)
section_summary("6. ExecutionPlan")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Planner — input contract
# ─────────────────────────────────────────────────────────────────────────────
section("7. Planner — Input Contract")
from app.execution_planning.planner import PlannerInputError
_reset_all()
for bad in [{"x": 1}, "string", None, 42, ["list"]]:
    try:
        pplanner.create_plan(bad)
        check(f"rejects {type(bad).__name__}", False)
    except PlannerInputError:
        check(f"rejects {type(bad).__name__}", True)
# Governance contract rejected
from app.governance.models import make_contract
gc = make_contract(str(uuid.uuid4()), True, "t", time.time(), "TRUST_ENGINE",
                   str(uuid.uuid4()), "HIGH", mission_id="m-1", ttl_seconds=3600)
try:
    pplanner.create_plan(gc)
    check("rejects GovernanceContract", False)
except PlannerInputError:
    check("rejects GovernanceContract", True)
check("accepts ExecutionAuthorization", pplanner.create_plan(_auth()) is not None)
section_summary("7. Planner — Input Contract")

# ─────────────────────────────────────────────────────────────────────────────
# 8. Planner — canonical plan
# ─────────────────────────────────────────────────────────────────────────────
section("8. Planner — Canonical Plan")
_reset_all()
a = _auth(mission="m-c", task="t-c")
p = pplanner.create_plan(a)
check("3 steps", p.estimated_steps == 3)
check("step1 navigate", p.steps[0].action_type == ActionType.navigate)
check("step2 extract", p.steps[1].action_type == ActionType.extract)
check("step3 validate", p.steps[2].action_type == ActionType.validate)
check("status draft", p.status == PlanStatus.draft)
check("auth id propagated", p.authorization_id == a.authorization_id)
check("mission propagated", p.mission_id == "m-c")
check("task propagated", p.task_id == "t-c")
check("navigate has url", "url" in p.steps[0].parameters)
check("steps have approval scope", all(st.approval_scope for st in p.steps))
check("approval scope references auth", a.authorization_id in p.steps[0].approval_scope)
check("metadata source canonical", p.metadata["source"] == "canonical")
check("duration sum 1450", p.estimated_duration_ms == 1450)
check("rollback supported", p.rollback_supported is True)
check("confidence in range", 0.0 <= p.confidence <= 1.0)
check("mode atomic (mutating+rollback)", p.execution_mode == ExecutionMode.atomic)
# determinism
p2 = pplanner.create_plan(a, now=50.0)
p3 = pplanner.create_plan(a, now=50.0)
check("deterministic actions", [s.action_type for s in p2.steps] == [s.action_type for s in p3.steps])
check("deterministic duration", p2.estimated_duration_ms == p3.estimated_duration_ms)
check("deterministic confidence", p2.confidence == p3.confidence)
check("deterministic mode", p2.execution_mode == p3.execution_mode)
section_summary("8. Planner — Canonical Plan")

# ─────────────────────────────────────────────────────────────────────────────
# 9. Planner — modes, confidence, url resolution
# ─────────────────────────────────────────────────────────────────────────────
section("9. Planner — Modes / Confidence / URL")
_reset_all()
check("CRITICAL -> dry_run", pplanner.create_plan(_auth(risk="CRITICAL")).execution_mode == ExecutionMode.dry_run)
check("HIGH -> atomic", pplanner.create_plan(_auth(risk="HIGH")).execution_mode == ExecutionMode.atomic)
class _RC:
    def __init__(self, url): self.last_url = url
class _M:
    def __init__(self, obj="", md=None):
        self.objective = obj; self.metadata = md or {}
p_no = pplanner.create_plan(_auth())
p_rt = pplanner.create_plan(_auth(), runtime_context=_RC("http://live"))
check("confidence higher with runtime", p_rt.confidence > p_no.confidence)
check("runtime url used", pplanner.create_plan(_auth(), runtime_context=_RC("http://x")).steps[0].parameters["url"] == "http://x")
check("mission target_url used", pplanner.create_plan(_auth(), mission=_M(md={"target_url": "http://m"})).steps[0].parameters["url"] == "http://m")
check("default about:blank", pplanner.create_plan(_auth()).steps[0].parameters["url"] == "about:blank")
check("objective in metadata", pplanner.create_plan(_auth(), mission=_M(obj="goal")).metadata["objective"] == "goal")
check("confidence max 1.0", pplanner.create_plan(_auth(), runtime_context=_RC("http://x")).confidence <= 1.0)
section_summary("9. Planner — Modes / Confidence / URL")

# ─────────────────────────────────────────────────────────────────────────────
# 10. Planner — workflow graph
# ─────────────────────────────────────────────────────────────────────────────
section("10. Planner — Workflow Graph")
class _Node:
    def __init__(self, nid, desc, prereq=None):
        self.node_id = nid; self.description = desc; self.prerequisites = prereq or []
class _Graph:
    def __init__(self, nodes): self.nodes = nodes
_reset_all()
g = _Graph([_Node("n1", "Navigate to homepage"), _Node("n2", "Click search"),
            _Node("n3", "Extract results"), _Node("n4", "Verify output")])
pg = pplanner.create_plan(_auth(), workflow_graph=g)
check("graph 4 steps", pg.estimated_steps == 4)
check("graph step1 navigate", pg.steps[0].action_type == ActionType.navigate)
check("graph step2 click", pg.steps[1].action_type == ActionType.click)
check("graph step3 extract", pg.steps[2].action_type == ActionType.extract)
check("graph step4 validate", pg.steps[3].action_type == ActionType.validate)
check("graph source metadata", pg.metadata["source"] == "workflow_graph")
check("node_id in params", pg.steps[0].parameters["node_id"] == "n1")
g_pre = _Graph([_Node("n2", "Click submit", prereq=["n1"])])
check("prerequisites preserved", pplanner.create_plan(_auth(), workflow_graph=g_pre).steps[0].parameters["prerequisites"] == ["n1"])
check("empty graph -> canonical", pplanner.create_plan(_auth(), workflow_graph=_Graph([])).metadata["source"] == "canonical")
# action inference matrix
eng = pplanner.ExecutionPlanner()
for desc, exp in [("navigate to x", ActionType.navigate), ("go to page", ActionType.navigate),
                  ("click button", ActionType.click), ("submit form", ActionType.click),
                  ("type query", ActionType.input), ("fill field", ActionType.input),
                  ("extract data", ActionType.extract), ("scrape", ActionType.extract),
                  ("scroll down", ActionType.scroll), ("wait for load", ActionType.wait),
                  ("verify result", ActionType.validate), ("check output", ActionType.validate),
                  ("undefined thing", ActionType.read)]:
    check(f"infer '{desc}'", eng._infer_action(desc)[0] == exp)
section_summary("10. Planner — Workflow Graph")

# ─────────────────────────────────────────────────────────────────────────────
# 11. RollbackPlanner
# ─────────────────────────────────────────────────────────────────────────────
section("11. RollbackPlanner")
check("navigate -> navigate_back", prollback.rollback_for_action(ActionType.navigate) == RollbackAction.navigate_back)
check("input -> clear_input", prollback.rollback_for_action(ActionType.input) == RollbackAction.clear_input)
check("click -> manual_review", prollback.rollback_for_action(ActionType.click) == RollbackAction.manual_review)
check("scroll -> scroll_restore", prollback.rollback_for_action(ActionType.scroll) == RollbackAction.scroll_restore)
check("extract -> none", prollback.rollback_for_action(ActionType.extract) == RollbackAction.none)
nav = make_step(1, ActionType.navigate, TargetType.url, "http://a")
desc = prollback.describe(nav)
for k in ["step_id", "order", "action_type", "rollback_action", "reversible", "requires_manual", "target"]:
    check(f"describe has {k}", k in desc)
check("navigate reversible", desc["reversible"] is True)
check("extract not reversible", prollback.describe(make_step(1, ActionType.extract, TargetType.region, "c"))["reversible"] is False)
check("click requires manual", prollback.describe(make_step(1, ActionType.click, TargetType.element, "b"))["requires_manual"] is True)
multi = [make_step(1, ActionType.navigate, TargetType.url, "a"),
         make_step(2, ActionType.input, TargetType.form, "f"),
         make_step(3, ActionType.click, TargetType.element, "b")]
meta = prollback.plan_rollback(multi)
for k in ["rollback_steps", "mutating_steps", "covered_steps", "fully_supported", "manual_steps"]:
    check(f"plan_rollback has {k}", k in meta)
check("reverse order", [d["order"] for d in meta["rollback_steps"]] == [3, 2, 1])
check("mutating count 3", meta["mutating_steps"] == 3)
check("fully supported", meta["fully_supported"] is True)
check("manual steps 1", meta["manual_steps"] == 1)
check("is_supported navigate", prollback.is_supported([nav]) is True)
check("is_supported empty", prollback.is_supported([]) is True)
bad = make_step(1, ActionType.click, TargetType.element, "b", rollback_action=RollbackAction.none)
check("is_supported false for bad", prollback.is_supported([bad]) is False)
check("plan_rollback bad not fully supported", prollback.plan_rollback([bad])["fully_supported"] is False)
section_summary("11. RollbackPlanner")

# ─────────────────────────────────────────────────────────────────────────────
# 12. PlanRegistry — CRUD
# ─────────────────────────────────────────────────────────────────────────────
section("12. PlanRegistry — CRUD")
_reset_all()
def _rplan(auth="auth-1", mission="m-1", task="t-1", created=None):
    return make_plan(auth, mission_id=mission, task_id=task,
                     created_at=created if created is not None else time.time(),
                     execution_mode=ExecutionMode.sequential,
                     steps=[make_step(1, ActionType.read, TargetType.page, "p")],
                     estimated_duration_ms=300, rollback_supported=True, confidence=0.6)
p1 = _rplan(); preg.add(p1)
check("get", preg.get(p1.plan_id) is not None)
check("get missing", preg.get("absent") is None)
preg.add(_rplan()); check("count 2", preg.count() == 2)
pa = _rplan(auth="auth-X"); preg.add(pa)
pb = _rplan(auth="auth-X"); preg.add(pb)
check("latest for auth", preg.get_for_authorization("auth-X").plan_id == pb.plan_id)
check("history 2", len(preg.history_for_authorization("auth-X")) == 2)
_reset_all()
preg.add(_rplan(mission="m-A")); preg.add(_rplan(mission="m-A")); preg.add(_rplan(mission="m-B"))
check("list_for_mission m-A 2", len(preg.list_for_mission("m-A")) == 2)
check("list_for_mission m-B 1", len(preg.list_for_mission("m-B")) == 1)
_reset_all()
preg.add(_rplan(task="t-A")); preg.add(_rplan(task="t-B"))
check("list_for_task t-A 1", len(preg.list_for_task("t-A")) == 1)
_reset_all()
preg.add(_rplan(created=100.0)); preg.add(_rplan(created=200.0))
check("list_all 2", len(preg.list_all()) == 2)
check("list_all newest first", preg.list_all()[0].created_at >= preg.list_all()[1].created_at)
sm = preg.summary_for_mission("m-1")
_reset_all()
preg.add(_rplan(mission="m-S"))
sm = preg.summary_for_mission("m-S")
for k in ["total_plans", "ready_plans", "draft_plans", "archived_plans", "active_plan_id", "plan_ids"]:
    check(f"summary has {k}", k in sm)
check("summary total 1", sm["total_plans"] == 1)
check("empty summary 0", preg.summary_for_mission("absent")["total_plans"] == 0)
section_summary("12. PlanRegistry — CRUD")

# ─────────────────────────────────────────────────────────────────────────────
# 13. PlanRegistry — transitions
# ─────────────────────────────────────────────────────────────────────────────
section("13. PlanRegistry — Transitions")
_reset_all()
pp = _rplan(); preg.add(pp)
check("set_status ready", preg.set_status(pp.plan_id, PlanStatus.ready) is True)
check("status is ready", preg.get(pp.plan_id).status == PlanStatus.ready)
check("set_status missing", preg.set_status("absent", PlanStatus.ready) is False)
check("mark_validated", preg.mark_validated(pp.plan_id, 99.0) is True)
check("validated_at set", preg.get(pp.plan_id).validated_at == 99.0)
check("count_by_status ready 1", preg.count_by_status(PlanStatus.ready) == 1)
pq = _rplan(); preg.add(pq)
check("archive", preg.archive(pq.plan_id, 5.0) is True)
check("archived status", preg.get(pq.plan_id).status == PlanStatus.aborted)
check("archived_at set", preg.get(pq.plan_id).archived_at == 5.0)
check("archive twice false", preg.archive(pq.plan_id, 6.0) is False)
check("archive missing false", preg.archive("absent", 1.0) is False)
ps1 = _rplan(auth="auth-S"); preg.add(ps1)
ps2 = _rplan(auth="auth-S"); preg.add(ps2)
check("supersede", preg.supersede(ps1.plan_id, ps2.plan_id) is True)
check("superseded_by set", preg.get(ps1.plan_id).superseded_by == ps2.plan_id)
check("superseded status aborted", preg.get(ps1.plan_id).status == PlanStatus.aborted)
check("supersede missing false", preg.supersede("absent", "x") is False)
for k in ["cached_plans", "total_added", "total_evicted", "ready_count", "mission_keys", "task_keys"]:
    check(f"stats has {k}", k in preg.stats())
section_summary("13. PlanRegistry — Transitions")

# ─────────────────────────────────────────────────────────────────────────────
# 14. PlanRegistry — TTL
# ─────────────────────────────────────────────────────────────────────────────
section("14. PlanRegistry — TTL")
from app.execution_planning.registry import PlanRegistry
rttl = PlanRegistry(ttl=0.05)
pt = _rplan(); rttl.add(pt)
check("present before ttl", rttl.get(pt.plan_id) is not None)
time.sleep(0.08)
check("expired after ttl", rttl.get(pt.plan_id) is None)
check("count 0 after expiry", rttl.count() == 0)
section_summary("14. PlanRegistry — TTL")

# ─────────────────────────────────────────────────────────────────────────────
# 15. PlanValidator
# ─────────────────────────────────────────────────────────────────────────────
section("15. PlanValidator")
_reset_all()
av = _auth(mission="m-1", task="t-1"); _mission("m-1", active=True, tasks=("t-1",))
pv = pplanner.create_plan(av, runtime_context=_RC("http://a"))
res = pvalidator.validate(pv)
check("valid true", res.valid is True)
for k in ["authorization_valid", "mission_active", "task_exists",
          "no_missing_parameters", "rollback_defined", "execution_mode_valid", "has_steps"]:
    check(f"check {k}", res.checks[k] is True)
check("no errors", res.errors == [])
check("validated_at set", res.validated_at > 0)
rd = res.to_dict()
for k in ["plan_id", "valid", "checks", "errors", "validated_at"]:
    check(f"result.to_dict has {k}", k in rd)
# auth missing
_reset_all()
av2 = _auth(); _mission()
pv2 = pplanner.create_plan(av2)
auth_reg._reset_for_testing()
check("missing auth fails", pvalidator.validate(pv2).checks["authorization_valid"] is False)
# paused mission
_reset_all()
av3 = _auth(); _mission(active=False)
check("paused mission fails", pvalidator.validate(pplanner.create_plan(av3)).checks["mission_active"] is False)
# task not attached
_reset_all()
av4 = _auth(task="t-999"); _mission(tasks=("t-1",))
check("task not attached fails", pvalidator.validate(pplanner.create_plan(av4)).checks["task_exists"] is False)
# navigate missing url
_reset_all()
av5 = _auth(); _mission()
bad_plan = make_plan(av5.authorization_id, mission_id="m-1", task_id="t-1", created_at=time.time(),
                     execution_mode=ExecutionMode.sequential,
                     steps=[make_step(1, ActionType.navigate, TargetType.url, "u")],
                     estimated_duration_ms=800, rollback_supported=True, confidence=0.5)
check("navigate missing url fails", pvalidator.validate(bad_plan).checks["no_missing_parameters"] is False)
# mutating without rollback
mut_plan = make_plan(av5.authorization_id, mission_id="m-1", task_id="t-1", created_at=time.time(),
                     execution_mode=ExecutionMode.sequential,
                     steps=[make_step(1, ActionType.click, TargetType.element, "b", rollback_action=RollbackAction.none)],
                     estimated_duration_ms=600, rollback_supported=False, confidence=0.5)
check("mutating no rollback fails", pvalidator.validate(mut_plan).checks["rollback_defined"] is False)
# empty plan
empty_plan = make_plan(av5.authorization_id, mission_id="m-1", task_id="t-1", created_at=time.time(),
                       execution_mode=ExecutionMode.sequential, steps=[],
                       estimated_duration_ms=0, rollback_supported=True, confidence=0.5)
check("empty plan has_steps false", pvalidator.validate(empty_plan).checks["has_steps"] is False)
check("empty plan invalid", pvalidator.validate(empty_plan).valid is False)
# no mission id skips mission/task
_reset_all()
av6 = make_authorization("ctr-1", True, "ok", "HIGH", time.time() + 3600, mission_id=None, task_id=None)
auth_reg.add(av6)
res6 = pvalidator.validate(pplanner.create_plan(av6))
check("no mission skip passes", res6.checks["mission_active"] is True)
check("no task skip passes", res6.checks["task_exists"] is True)
section_summary("15. PlanValidator")

# ─────────────────────────────────────────────────────────────────────────────
# 16. PlanTimeline
# ─────────────────────────────────────────────────────────────────────────────
section("16. PlanTimeline")
ptl._reset_for_testing()
for et in ["created", "validated", "ready", "cancelled", "superseded", "archived"]:
    ptl.record("plan-1", et, mission_id="m-tl")
evs = ptl.get("m-tl")
check("6 events", len(evs) == 6)
check("newest first", evs[0]["event_type"] == "archived")
types = {e["event_type"] for e in evs}
for et in ["created", "validated", "ready", "cancelled", "superseded", "archived"]:
    check(f"event {et} present", et in types)
ev = evs[0]
for k in ["plan_id", "event_type", "mission_id", "authorization_id", "status", "timestamp"]:
    check(f"event has {k}", k in ev)
check("get empty", ptl.get("absent") == [])
check("limit", len(ptl.get("m-tl", limit=2)) == 2)
check("recent_global", len(ptl.recent_global()) >= 6)
summ = ptl.summary("m-tl")
check("summary count 6", summ["event_count"] == 6)
check("summary type_counts", isinstance(summ["type_counts"], dict))
check("summary latest", summ["latest_event"] is not None)
check("missions_with_plans", "m-tl" in ptl.missions_with_plans())
ptl._reset_for_testing()
check("reset clears", ptl.get("m-tl") == [])
section_summary("16. PlanTimeline")

# ─────────────────────────────────────────────────────────────────────────────
# 17. PlanAnalytics
# ─────────────────────────────────────────────────────────────────────────────
section("17. PlanAnalytics")
panal._reset_for_testing()
a0 = panal.get_analytics()
for k in ["plans_created", "plans_validated", "validation_failures",
          "avg_steps", "avg_duration_ms", "rollback_supported", "archived"]:
    check(f"analytics has {k}", k in a0)
check("initial created 0", a0["plans_created"] == 0)
panal.record_created(3, 1450, True)
panal.record_created(5, 1550, False)
a1 = panal.get_analytics()
check("created 2", a1["plans_created"] == 2)
check("rollback_supported 1", a1["rollback_supported"] == 1)
check("avg_steps 4", a1["avg_steps"] == 4.0)
check("avg_duration 1500", a1["avg_duration_ms"] == 1500.0)
panal.record_validated(True); panal.record_validated(True); panal.record_validated(False)
a2 = panal.get_analytics()
check("validated 2", a2["plans_validated"] == 2)
check("failures 1", a2["validation_failures"] == 1)
panal.record_archived()
check("archived 1", panal.get_analytics()["archived"] == 1)
panal._reset_for_testing()
check("reset created 0", panal.get_analytics()["plans_created"] == 0)
check("reset avg 0", panal.get_analytics()["avg_steps"] == 0.0)
section_summary("17. PlanAnalytics")

# ─────────────────────────────────────────────────────────────────────────────
# 18. PlanInspector
# ─────────────────────────────────────────────────────────────────────────────
section("18. PlanInspector")
_reset_all()
ai = _auth(); _mission()
pi = pplanner.create_plan(ai); preg.add(pi)
ins = pinsp.inspect(pi.plan_id)
check("inspect not None", ins is not None)
check("inspect missing None", pinsp.inspect("absent") is None)
for k in ["plan_id", "plan", "step_count", "mutating_steps", "rollback", "validation",
          "authorization", "mission_context", "timeline_summary", "analytics",
          "registry_stats", "latency_ms"]:
    check(f"inspect has {k}", k in ins)
check("inspect plan_id", ins["plan_id"] == pi.plan_id)
check("inspect step_count 3", ins["step_count"] == 3)
check("inspect plan has steps", len(ins["plan"]["steps"]) == 3)
check("inspect rollback fully_supported", ins["rollback"]["fully_supported"] is True)
check("inspect validation valid", ins["validation"]["valid"] is True)
check("inspect auth executable", ins["authorization"]["is_executable"] is True)
check("inspect mission active", ins["mission_context"]["state"] == "ACTIVE")
check("inspect latency >= 0", ins["latency_ms"] >= 0.0)
section_summary("18. PlanInspector")

# ─────────────────────────────────────────────────────────────────────────────
# 19. Persistence stub
# ─────────────────────────────────────────────────────────────────────────────
section("19. Persistence Stub")
from app.execution_planning.persistence import ExecutionPlanPersistence, execution_plan_persistence
pers = ExecutionPlanPersistence()
check("flag False", execution_plan_persistence is False)
check("enabled False", pers.enabled() is False)
check("save no-op", pers.save(pi) is None)
check("load empty", pers.load_for_mission("m-1") == [])
check("delete 0", pers.delete_for_plan("plan-1") == 0)
section_summary("19. Persistence Stub")

# ─────────────────────────────────────────────────────────────────────────────
# 20. Schemas
# ─────────────────────────────────────────────────────────────────────────────
section("20. Schemas (Pydantic)")
from app.schemas.execution_planning import (
    ExecutionStepSchema, ExecutionPlanSchema, PlanValidationResultSchema,
    PlanAnalyticsSchema, PlanInspectorSchema, PlanSummarySchema,
)
check("step schema", ExecutionStepSchema(step_id="s", order=1, action_type="NAVIGATE",
        target_type="URL", target_description="u").action_type == "NAVIGATE")
check("plan schema", ExecutionPlanSchema(plan_id="p", authorization_id="a").status == "DRAFT")
check("plan schema default mode", ExecutionPlanSchema(plan_id="p", authorization_id="a").execution_mode == "SEQUENTIAL")
check("validation schema", PlanValidationResultSchema(plan_id="p", valid=True).valid is True)
check("analytics schema", PlanAnalyticsSchema().plans_created == 0)
check("inspector schema", PlanInspectorSchema(plan_id="p").plan_id == "p")
check("summary schema", PlanSummarySchema().total_plans == 0)
check("plan schema version default", ExecutionPlanSchema(plan_id="p", authorization_id="a").planner_version == "1.0")
section_summary("20. Schemas (Pydantic)")

# ─────────────────────────────────────────────────────────────────────────────
# 21. REST API — registration + responses
# ─────────────────────────────────────────────────────────────────────────────
section("21. REST API")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
routes = {r.path for r in app.routes}
for path in ["/plans", "/plans/create/{authorization_id}", "/plans/validate/{plan_id}",
             "/plans/{plan_id}/archive", "/plans/analytics", "/plans/mission/{mission_id}",
             "/plans/task/{task_id}", "/plans/inspect/{plan_id}", "/plans/{plan_id}"]:
    check(f"route {path}", path in routes)
_reset_all()
av = _auth(mission="m-api", task="t-api"); _mission("m-api", active=True, tasks=("t-api",))
check("GET /plans empty", client.get("/plans").json() == [])
cr = client.post(f"/plans/create/{av.authorization_id}")
check("create 200", cr.status_code == 200)
pid = cr.json()["plan_id"]
check("create plan_id", pid.startswith("plan-"))
check("create status DRAFT", cr.json()["status"] == "DRAFT")
check("create steps 3", len(cr.json()["steps"]) == 3)
check("create missing auth 404", client.post("/plans/create/no-auth").status_code == 404)
av_denied = make_authorization("ctr-1", False, "denied", "HIGH", time.time()+3600, mission_id="m-d")
auth_reg.add(av_denied)
check("create denied 409", client.post(f"/plans/create/{av_denied.authorization_id}").status_code == 409)
vr = client.post(f"/plans/validate/{pid}")
check("validate 200", vr.status_code == 200)
check("validate valid", vr.json()["valid"] is True)
check("validate ready", vr.json()["plan_status"] == "READY")
check("validate missing 404", client.post("/plans/validate/no-plan").status_code == 404)
check("GET /plans 1", len(client.get("/plans").json()) == 1)
check("filter mission", len(client.get("/plans?mission_id=m-api").json()) == 1)
check("filter status READY", len(client.get("/plans?status=READY").json()) == 1)
check("filter invalid 400", client.get("/plans?status=BOGUS").status_code == 400)
check("list omits steps", "steps" not in client.get("/plans").json()[0])
check("get by id 200", client.get(f"/plans/{pid}").status_code == 200)
check("get by id has steps", "steps" in client.get(f"/plans/{pid}").json())
check("get missing 404", client.get("/plans/no-plan").status_code == 404)
check("plans for mission", len(client.get("/plans/mission/m-api").json()) == 1)
check("plans for task", len(client.get("/plans/task/t-api").json()) == 1)
check("analytics 200", client.get("/plans/analytics").status_code == 200)
check("analytics created >=1", client.get("/plans/analytics").json()["plans_created"] >= 1)
check("inspect 200", client.get(f"/plans/inspect/{pid}").status_code == 200)
check("inspect missing 404", client.get("/plans/inspect/no-plan").status_code == 404)
arch = client.post(f"/plans/{pid}/archive")
check("archive 200", arch.status_code == 200)
check("archive status ABORTED", arch.json()["status"] == "ABORTED")
check("archive twice 409", client.post(f"/plans/{pid}/archive").status_code == 409)
check("archive missing 404", client.post("/plans/no-plan/archive").status_code == 404)
section_summary("21. REST API")

# ─────────────────────────────────────────────────────────────────────────────
# 22. Cross-layer integration
# ─────────────────────────────────────────────────────────────────────────────
section("22. Cross-Layer Integration")
_reset_all()
# Mission inspector gains execution_planning
av = _auth(mission="m-mi", task="t-mi"); _mission("m-mi", active=True, tasks=("t-mi",))
pid = client.post(f"/plans/create/{av.authorization_id}").json()["plan_id"]
client.post(f"/plans/validate/{pid}")
mi = client.get("/mission/m-mi/inspect")
check("mission inspect 200", mi.status_code == 200)
check("mission inspect has execution_planning", "execution_planning" in mi.json())
ep = mi.json()["execution_planning"]
check("ep not None", ep is not None)
for k in ["active_plan_id", "plan_readiness", "total_plans", "ready_plans",
          "estimated_steps", "estimated_duration_ms", "rollback_available"]:
    check(f"ep has {k}", k in ep)
check("ep total_plans >= 1", ep["total_plans"] >= 1)
check("ep estimated_steps 3", ep["estimated_steps"] == 3)
check("ep rollback_available", ep["rollback_available"] is True)
check("ep readiness READY", ep["plan_readiness"] == "READY")
# Authorization → plan linkage
check("plan tied to auth", preg.get_for_authorization(av.authorization_id).plan_id == pid)
# Runtime integration: plan uses runtime url
_reset_all()
av_rt = _auth(mission="m-rt", task="t-rt"); _mission("m-rt", active=True, tasks=("t-rt",))
client.post("/runtime/sync", json={"active_mission_id": "m-rt", "active_tab_id": "tab-1",
                                   "last_url": "http://runtime-url.com"})
plan_rt = client.post(f"/plans/create/{av_rt.authorization_id}").json()
check("plan uses runtime url", plan_rt["steps"][0]["parameters"]["url"] == "http://runtime-url.com")
section_summary("22. Cross-Layer Integration")

# ─────────────────────────────────────────────────────────────────────────────
# 23. Future Gateway Contract (Component 13) + Authorization-only (Component 10)
# ─────────────────────────────────────────────────────────────────────────────
section("23. Gateway Contract / Authorization-Only")
# Planner accepts ONLY ExecutionAuthorization
from app.approvals.models import make_approval_request, ApprovalSourceType, ApprovalRiskLevel
appr = make_approval_request(source_type=ApprovalSourceType.trust_engine, source_id="s",
                             title="t", description="d", risk_level=ApprovalRiskLevel.high,
                             priority="HIGH", mission_id="m-1")
try:
    pplanner.create_plan(appr)
    check("planner rejects ApprovalRequest", False)
except PlannerInputError:
    check("planner rejects ApprovalRequest", True)
try:
    pplanner.create_plan(gc)   # governance contract from section 7
    check("planner rejects GovernanceContract", False)
except PlannerInputError:
    check("planner rejects GovernanceContract", True)
# Gateway-only statuses never assigned by planning layer
_reset_all()
av = _auth(); _mission()
created_plan = pplanner.create_plan(av)
check("planner never sets EXECUTING", created_plan.status != PlanStatus.executing)
check("planner never sets COMPLETED", created_plan.status != PlanStatus.completed)
check("planner never sets FAILED", created_plan.status != PlanStatus.failed)
check("planner status is DRAFT", created_plan.status == PlanStatus.draft)
# READY is the only status a gateway should accept — verify validate produces READY only when valid
preg.add(created_plan)
vres = pvalidator.validate(created_plan)
check("valid plan can become READY", vres.valid is True)
# Source code contract checks
planner_src = pathlib.Path("app/execution_planning/planner.py").read_text(encoding="utf-8")
check("planner imports ExecutionAuthorization", "ExecutionAuthorization" in planner_src)
check("planner has type guard", "_assert_is_authorization" in planner_src)
check("planner forbids GovernanceContract (doc)", "GovernanceContract" in planner_src)
models_src = pathlib.Path("app/execution_planning/models.py").read_text(encoding="utf-8")
check("models document gateway-only statuses", "GATEWAY_ONLY_STATUSES" in models_src)
check("models document READY-only gateway contract", "ONLY status the Gateway may accept" in models_src)
section_summary("23. Gateway Contract / Authorization-Only")

# ─────────────────────────────────────────────────────────────────────────────
# 24. Safety — no forbidden patterns
# ─────────────────────────────────────────────────────────────────────────────
section("24. Safety — No Forbidden Patterns")
forbidden = [
    "subprocess", "os.system", "import webbrowser", "playwright", "selenium",
    "workflow_dispatch", "dispatch_workflow", "agent_swarm", "background worker",
    "execute_task(", "run_browser(", "click_element(", ".dispatch(",
    "anthropic", "openai", "llm_client", "call_llm", ".generate(",
    "requests.get", "requests.post", "httpx.get", "httpx.post", "urllib.request",
]
sources = list(pathlib.Path("app/execution_planning").rglob("*.py"))
check("package has >= 10 modules", len(sources) >= 10)
for src_path in sources:
    text = src_path.read_text(encoding="utf-8", errors="replace").lower()
    for fb in forbidden:
        check(f"NO '{fb}' in {src_path.name}", fb.lower() not in text)
route_src = pathlib.Path("app/api/routes/plans.py").read_text(encoding="utf-8").lower()
check("route no playwright", "playwright" not in route_src)
check("route no subprocess", "subprocess" not in route_src)
# main + mission integration present
main_src = pathlib.Path("app/main.py").read_text(encoding="utf-8")
check("main registers plans_router", "plans_router" in main_src)
mission_schema_src = pathlib.Path("app/schemas/mission.py").read_text(encoding="utf-8")
check("mission schema execution_planning", "execution_planning" in mission_schema_src)
mission_route_src = pathlib.Path("app/api/routes/mission.py").read_text(encoding="utf-8")
check("mission route execution_planning_summary", "execution_planning_summary" in mission_route_src)
persist_src = pathlib.Path("app/execution_planning/persistence.py").read_text(encoding="utf-8")
check("persistence flag default False", "execution_plan_persistence: bool = False" in persist_src)
section_summary("24. Safety — No Forbidden Patterns")

# ─────────────────────────────────────────────────────────────────────────────
# Final tally
# ─────────────────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"V9.0 VALIDATION: {PASS}/{total} checks passed")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL CHECKS PASSED")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
