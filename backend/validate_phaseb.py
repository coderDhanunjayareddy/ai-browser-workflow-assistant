"""
Phase B — Execution Gateway V1 — Validation Suite.

Minimum 900 checks across 28 sections.
Run: python validate_phaseb.py
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


# ── imports ───────────────────────────────────────────────────────────────────
from app.execution_gateway import (
    registry as ereg, analytics as eanal, timeline as etl, audit as eaudit,
    engine as gateway, inspector as einsp, dispatcher as edisp,
    validation as eval_engine, retry_engine, rollback_engine, runner as erunner,
)
from app.execution_gateway.models import (
    ExecutionState, CommandType, StepOutcome, TERMINAL_STATES, GATEWAY_VERSION,
    ExecutionCommand, AdapterResult, StepExecution, AuditEntry, RetryConfig,
    ExecutionRecord, make_command, make_audit_entry, make_execution,
)
from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.mock_adapter import MockBrowserAdapter, SIMULATED_DURATION_MS
from app.execution_gateway.contracts import (
    PlaywrightAdapter, ChromeCDPAdapter, NativeChromeExtensionAdapter, VisionAdapter,
    FUTURE_ADAPTERS, ADAPTER_OPERATIONS,
)
from app.execution_gateway.engine import GatewayError
from app.execution_gateway.dispatcher import ACTION_TO_COMMAND
from app.execution_planning import registry as plan_reg, planner
from app.execution_planning.registry import set_status
from app.execution_planning.models import (
    PlanStatus, ActionType, TargetType, ValidationStrategy, make_step, make_plan, ExecutionMode,
)
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState


def _reset_all():
    for m in [ereg, eanal, etl, eaudit, plan_reg, auth_reg, mission_store]:
        m._reset_for_testing()


def _ready_plan(mission="m-1", task="t-1", active=True, authorized=True):
    auth = make_authorization("ctr-1", authorized, "ok", "HIGH", time.time() + 3600,
                              mission_id=mission, task_id=task)
    auth_reg.add(auth)
    if mission:
        state = MissionState.active if active else MissionState.paused
        mission_store.put(Mission(mission, "t", "obj", state, task_ids=[task] if task else []))
    plan = planner.create_plan(auth)
    plan_reg.add(plan)
    set_status(plan.plan_id, PlanStatus.ready)
    return plan_reg.get(plan.plan_id)


def _cmd(ctype=CommandType.navigate, step_id="step-1", strategy="DOM_PRESENCE"):
    return make_command(ctype, step_id, 1, "target", validation_strategy=strategy,
                        rollback_action="NAVIGATE_BACK")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Package structure
# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
for f in [
    "app/execution_gateway/__init__.py", "app/execution_gateway/models.py",
    "app/execution_gateway/adapter.py", "app/execution_gateway/mock_adapter.py",
    "app/execution_gateway/contracts.py", "app/execution_gateway/dispatcher.py",
    "app/execution_gateway/validation.py", "app/execution_gateway/retry_engine.py",
    "app/execution_gateway/rollback_engine.py", "app/execution_gateway/audit.py",
    "app/execution_gateway/runner.py", "app/execution_gateway/registry.py",
    "app/execution_gateway/analytics.py", "app/execution_gateway/timeline.py",
    "app/execution_gateway/engine.py", "app/execution_gateway/inspector.py",
    "app/schemas/execution_gateway.py", "app/api/routes/gateway.py",
]:
    check(f"file exists: {f}", pathlib.Path(f).exists())
section_summary("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
# 2. ExecutionState
# ─────────────────────────────────────────────────────────────────────────────
section("2. ExecutionState")
check("6 states", len(ExecutionState) == 6)
for st, v in [(ExecutionState.pending, "PENDING"), (ExecutionState.running, "RUNNING"),
              (ExecutionState.paused, "PAUSED"), (ExecutionState.completed, "COMPLETED"),
              (ExecutionState.failed, "FAILED"), (ExecutionState.aborted, "ABORTED")]:
    check(f"state {v}", st.value == v)
    check(f"state from string {v}", ExecutionState(v) == st)
check("completed terminal", ExecutionState.completed in TERMINAL_STATES)
check("failed terminal", ExecutionState.failed in TERMINAL_STATES)
check("aborted terminal", ExecutionState.aborted in TERMINAL_STATES)
check("running not terminal", ExecutionState.running not in TERMINAL_STATES)
check("pending not terminal", ExecutionState.pending not in TERMINAL_STATES)
check("paused not terminal", ExecutionState.paused not in TERMINAL_STATES)
check("3 terminal states", len(TERMINAL_STATES) == 3)
check("gateway version 1.0", GATEWAY_VERSION == "1.0")
section_summary("2. ExecutionState")

# ─────────────────────────────────────────────────────────────────────────────
# 3. CommandType + StepOutcome
# ─────────────────────────────────────────────────────────────────────────────
section("3. CommandType + StepOutcome")
check("9 command types", len(CommandType) == 9)
for ct, v in [(CommandType.navigate, "NAVIGATE"), (CommandType.click, "CLICK"),
              (CommandType.type, "TYPE"), (CommandType.wait, "WAIT"),
              (CommandType.extract, "EXTRACT"), (CommandType.validate, "VALIDATE"),
              (CommandType.upload, "UPLOAD"), (CommandType.download, "DOWNLOAD"),
              (CommandType.custom, "CUSTOM")]:
    check(f"command {v}", ct.value == v)
    check(f"command from string {v}", CommandType(v) == ct)
check("5 step outcomes", len(StepOutcome) == 5)
for so, v in [(StepOutcome.success, "SUCCESS"), (StepOutcome.failed, "FAILED"),
              (StepOutcome.validation_failed, "VALIDATION_FAILED"),
              (StepOutcome.skipped, "SKIPPED"), (StepOutcome.rolled_back, "ROLLED_BACK")]:
    check(f"outcome {v}", so.value == v)
section_summary("3. CommandType + StepOutcome")

# ─────────────────────────────────────────────────────────────────────────────
# 4. ExecutionCommand
# ─────────────────────────────────────────────────────────────────────────────
section("4. ExecutionCommand")
c = make_command(CommandType.click, "step-1", 2, "btn", parameters={"x": 1},
                 expected_result="clicked", validation_strategy="DOM_PRESENCE",
                 rollback_action="MANUAL_REVIEW")
check("command id prefix", c.command_id.startswith("cmd-"))
check("command type", c.command_type == CommandType.click)
check("step_id", c.step_id == "step-1")
check("order", c.order == 2)
check("target", c.target_description == "btn")
check("parameters", c.parameters == {"x": 1})
check("expected_result", c.expected_result == "clicked")
check("validation_strategy", c.validation_strategy == "DOM_PRESENCE")
check("rollback_action", c.rollback_action == "MANUAL_REVIEW")
cd = c.to_dict()
for k in ["command_id", "command_type", "step_id", "order", "target_description",
          "parameters", "expected_result", "validation_strategy", "rollback_action"]:
    check(f"command.to_dict has {k}", k in cd)
check("command to_dict type string", cd["command_type"] == "CLICK")
check("command ids unique", make_command(CommandType.wait, "s", 1, "t").command_id !=
                            make_command(CommandType.wait, "s", 1, "t").command_id)
section_summary("4. ExecutionCommand")

# ─────────────────────────────────────────────────────────────────────────────
# 5. AdapterResult + RetryConfig
# ─────────────────────────────────────────────────────────────────────────────
section("5. AdapterResult + RetryConfig")
r = AdapterResult(success=True, duration_ms=5.0)
check("default validation passed", r.validation_passed is True)
check("default logs empty", r.logs == [])
check("default output empty", r.output == {})
rd = AdapterResult(success=False, duration_ms=1.0, logs=["x"], message="m").to_dict()
for k in ["success", "duration_ms", "logs", "output", "validation_passed", "message"]:
    check(f"adapter_result.to_dict has {k}", k in rd)
cfg = RetryConfig()
check("default max_retries 2", cfg.max_retries == 2)
check("default retry on validation", cfg.retry_on_validation_failure is True)
check("max_attempts = retries+1", RetryConfig(max_retries=3).max_attempts == 4)
check("max_attempts 0 retries = 1", RetryConfig(max_retries=0).max_attempts == 1)
cfgd = cfg.to_dict()
for k in ["max_retries", "retry_on_validation_failure", "max_attempts"]:
    check(f"retry_config.to_dict has {k}", k in cfgd)
section_summary("5. AdapterResult + RetryConfig")

# ─────────────────────────────────────────────────────────────────────────────
# 6. ExecutionRecord
# ─────────────────────────────────────────────────────────────────────────────
section("6. ExecutionRecord")
rec = make_execution("plan-1", "auth-1", mission_id="m-1", task_id="t-1",
                     total_steps=3, adapter_name="mock", created_at=100.0)
check("execution id prefix", rec.execution_id.startswith("exec-"))
check("plan_id", rec.plan_id == "plan-1")
check("authorization_id", rec.authorization_id == "auth-1")
check("mission_id", rec.mission_id == "m-1")
check("task_id", rec.task_id == "t-1")
check("initial pending", rec.state == ExecutionState.pending)
check("adapter mock", rec.adapter_name == "mock")
check("total_steps", rec.total_steps == 3)
check("retry config default", rec.retry_config.max_retries == 2)
check("not terminal", rec.is_terminal is False)
check("remaining = total initially", rec.remaining_steps == 3)
check("total_retries 0", rec.total_retries == 0)
check("total_duration 0", rec.total_duration_ms == 0.0)
rec.current_step_index = 1
check("remaining after 1", rec.remaining_steps == 2)
rec.state = ExecutionState.completed
check("terminal when completed", rec.is_terminal is True)
recd = rec.to_dict()
for k in ["execution_id", "plan_id", "authorization_id", "mission_id", "task_id",
          "state", "adapter_name", "created_at", "updated_at", "started_at", "finished_at",
          "current_step_index", "total_steps", "completed_steps", "failed_steps",
          "remaining_steps", "total_retries", "total_duration_ms", "rollback_history",
          "retry_config", "preflight", "metadata", "is_terminal", "step_executions"]:
    check(f"record.to_dict has {k}", k in recd)
check("record.to_dict state string", recd["state"] == "COMPLETED")
check("to_dict no steps when excluded", "step_executions" not in rec.to_dict(include_steps=False))
check("execution ids unique", make_execution("p", "a", mission_id="m", task_id="t",
        total_steps=1, adapter_name="mock", created_at=1.0).execution_id !=
        make_execution("p", "a", mission_id="m", task_id="t",
        total_steps=1, adapter_name="mock", created_at=1.0).execution_id)
section_summary("6. ExecutionRecord")

# ─────────────────────────────────────────────────────────────────────────────
# 7. Adapter Interface
# ─────────────────────────────────────────────────────────────────────────────
section("7. Adapter Interface")
try:
    ExecutionAdapter()
    check("abstract cannot instantiate", False)
except TypeError:
    check("abstract cannot instantiate", True)
check("9 adapter operations", len(ADAPTER_OPERATIONS) == 9)
for op in ["navigate", "click", "type", "wait", "extract", "validate", "upload", "download", "execute_custom"]:
    check(f"adapter op {op}", op in ADAPTER_OPERATIONS)
check("routing table complete", all(ct in ExecutionAdapter.COMMAND_ROUTING for ct in CommandType))
for ct in CommandType:
    check(f"routing has {ct.value}", ct in ExecutionAdapter.COMMAND_ROUTING)
section_summary("7. Adapter Interface")

# ─────────────────────────────────────────────────────────────────────────────
# 8. MockBrowserAdapter — operations
# ─────────────────────────────────────────────────────────────────────────────
section("8. MockBrowserAdapter — Operations")
a = MockBrowserAdapter()
check("name mock", a.name == "mock")
ops = [(CommandType.navigate, a.navigate), (CommandType.click, a.click), (CommandType.type, a.type),
       (CommandType.wait, a.wait), (CommandType.extract, a.extract), (CommandType.validate, a.validate),
       (CommandType.upload, a.upload), (CommandType.download, a.download), (CommandType.custom, a.execute_custom)]
for ct, method in ops:
    res = method(_cmd(ct))
    check(f"{ct.value} success", res.success is True)
    check(f"{ct.value} validation passed", res.validation_passed is True)
    check(f"{ct.value} has logs", len(res.logs) >= 1)
    check(f"{ct.value} duration matches profile", res.duration_ms == SIMULATED_DURATION_MS[ct])
    check(f"{ct.value} output simulated", res.output.get("simulated") is True)
check("dispatch routes navigate", a.dispatch(_cmd(CommandType.navigate)).success is True)
check("dispatch records command", len(a.dispatched) > 0)
section_summary("8. MockBrowserAdapter — Operations")

# ─────────────────────────────────────────────────────────────────────────────
# 9. MockBrowserAdapter — deterministic failure paths
# ─────────────────────────────────────────────────────────────────────────────
section("9. MockBrowserAdapter — Failure Paths")
af = MockBrowserAdapter(failure_steps={"bad"})
check("failure step fails", af.navigate(_cmd(step_id="bad")).success is False)
check("non-failure ok", af.navigate(_cmd(step_id="ok")).success is True)
av = MockBrowserAdapter(validation_fail_steps={"vbad"})
res_v = av.extract(_cmd(CommandType.extract, step_id="vbad"))
check("validation-fail dispatch ok", res_v.success is True)
check("validation-fail validation false", res_v.validation_passed is False)
afl = MockBrowserAdapter(flaky_steps={"flk"})
check("flaky first fails", afl.navigate(_cmd(step_id="flk")).success is False)
check("flaky second succeeds", afl.navigate(_cmd(step_id="flk")).success is True)
afl.reset()
check("flaky resets", afl.navigate(_cmd(step_id="flk")).success is False)
check("determinism: same failure repeated", MockBrowserAdapter(failure_steps={"x"}).navigate(_cmd(step_id="x")).success is False)
section_summary("9. MockBrowserAdapter — Failure Paths")

# ─────────────────────────────────────────────────────────────────────────────
# 10. Future adapters (interface only)
# ─────────────────────────────────────────────────────────────────────────────
section("10. Future Adapters")
check("4 future adapters", len(FUTURE_ADAPTERS) == 4)
for name in ["playwright", "chrome_cdp", "native_chrome_extension", "vision"]:
    check(f"future registry has {name}", name in FUTURE_ADAPTERS)
for cls, name in [(PlaywrightAdapter, "playwright"), (ChromeCDPAdapter, "chrome_cdp"),
                  (NativeChromeExtensionAdapter, "native_chrome_extension"), (VisionAdapter, "vision")]:
    inst = cls()
    check(f"{name} name", inst.name == name)
    for method in [inst.navigate, inst.click, inst.type, inst.wait, inst.extract,
                   inst.validate, inst.upload, inst.download, inst.execute_custom]:
        try:
            method(_cmd())
            check(f"{name}.{method.__name__} not implemented", False)
        except NotImplementedError:
            check(f"{name}.{method.__name__} not implemented", True)
section_summary("10. Future Adapters")

# ─────────────────────────────────────────────────────────────────────────────
# 11. Dispatcher — action mapping
# ─────────────────────────────────────────────────────────────────────────────
section("11. Dispatcher — Action Mapping")
check("all actions mapped", all(at in ACTION_TO_COMMAND for at in ActionType))
for at, ct in [(ActionType.navigate, CommandType.navigate), (ActionType.read, CommandType.extract),
               (ActionType.extract, CommandType.extract), (ActionType.input, CommandType.type),
               (ActionType.click, CommandType.click), (ActionType.scroll, CommandType.custom),
               (ActionType.wait, CommandType.wait), (ActionType.validate, CommandType.validate)]:
    check(f"map {at.value} -> {ct.value}", ACTION_TO_COMMAND[at] == ct)
step = make_step(1, ActionType.navigate, TargetType.url, "http://a", parameters={"url": "http://a"}, expected_result="ok")
cmd = edisp.to_command(step)
check("to_command type", cmd.command_type == CommandType.navigate)
check("to_command step_id", cmd.step_id == step.step_id)
check("to_command order", cmd.order == 1)
check("to_command params copied", cmd.parameters == {"url": "http://a"})
check("to_command validation string", cmd.validation_strategy == ValidationStrategy.url_match.value)
check("to_command rollback string", cmd.rollback_action == "NAVIGATE_BACK")
check("to_command expected", cmd.expected_result == "ok")
check("dispatch returns result", edisp.dispatch(cmd, MockBrowserAdapter()).success is True)
section_summary("11. Dispatcher — Action Mapping")

# ─────────────────────────────────────────────────────────────────────────────
# 12. Validation engine
# ─────────────────────────────────────────────────────────────────────────────
section("12. Validation Engine")
ok = eval_engine.validate(_cmd(), AdapterResult(success=True, duration_ms=5.0, validation_passed=True))
check("success passes", ok.passed is True)
for k in ["dispatch_succeeded", "strategy_passed", "rollback_metadata_present"]:
    check(f"check {k} present", k in ok.checks)
fail_dispatch = eval_engine.validate(_cmd(), AdapterResult(success=False, duration_ms=5.0))
check("dispatch fail fails", fail_dispatch.passed is False)
check("dispatch fail check", fail_dispatch.checks["dispatch_succeeded"] is False)
fail_val = eval_engine.validate(_cmd(strategy="URL_MATCH"), AdapterResult(success=True, duration_ms=5.0, validation_passed=False))
check("validation fail fails", fail_val.passed is False)
check("validation fail reason", "URL_MATCH" in fail_val.reason)
none_strategy = eval_engine.validate(_cmd(strategy="NONE"), AdapterResult(success=True, duration_ms=5.0, validation_passed=False))
check("none strategy passes despite validation false", none_strategy.passed is True)
check("rollback metadata present", ok.checks["rollback_metadata_present"] is True)
vd = ok.to_dict()
for k in ["passed", "checks", "reason"]:
    check(f"validation.to_dict has {k}", k in vd)
section_summary("12. Validation Engine")

# ─────────────────────────────────────────────────────────────────────────────
# 13. Retry engine
# ─────────────────────────────────────────────────────────────────────────────
section("13. Retry Engine")
cfg2 = RetryConfig(max_retries=2)
check("retry on dispatch fail", retry_engine.should_retry(1, cfg2, dispatch_failed=True, validation_failed=False) is True)
check("stop at max attempts", retry_engine.should_retry(3, cfg2, dispatch_failed=True, validation_failed=False) is False)
check("retry on validation when enabled", retry_engine.should_retry(1, cfg2, dispatch_failed=False, validation_failed=True) is True)
check("no retry on validation when disabled",
      retry_engine.should_retry(1, RetryConfig(max_retries=2, retry_on_validation_failure=False),
                                dispatch_failed=False, validation_failed=True) is False)
check("no retry on success", retry_engine.should_retry(1, cfg2, dispatch_failed=False, validation_failed=False) is False)
check("zero retries = one attempt", retry_engine.should_retry(1, RetryConfig(max_retries=0), dispatch_failed=True, validation_failed=False) is False)
check("bounded never infinite", retry_engine.should_retry(cfg2.max_attempts, cfg2, dispatch_failed=True, validation_failed=True) is False)
check("attempts allowed", retry_engine.attempts_allowed(RetryConfig(max_retries=3)) == 4)
# exhaustive bound check across attempt numbers
for attempt in range(1, 10):
    result = retry_engine.should_retry(attempt, RetryConfig(max_retries=2), dispatch_failed=True, validation_failed=False)
    check(f"attempt {attempt} bounded", result == (attempt < 3))
section_summary("13. Retry Engine")

# ─────────────────────────────────────────────────────────────────────────────
# 14. Rollback engine
# ─────────────────────────────────────────────────────────────────────────────
section("14. Rollback Engine")
def _se(order, sid=None):
    return StepExecution(step_id=sid or f"s{order}", order=order, action_type="NAVIGATE",
                         command_type="NAVIGATE", outcome=StepOutcome.success, attempts=1,
                         duration_ms=5.0, validation_passed=True)
steps3 = [_se(1), _se(2), _se(3)]
report = rollback_engine.simulate(steps3)
check("reverse order", [d["order"] for d in report] == [3, 2, 1])
check("marks performed", all(s.rollback_performed for s in steps3))
check("3 descriptors", len(report) == 3)
for k in ["step_id", "order", "action_type", "command_type", "simulated", "note"]:
    check(f"descriptor has {k}", k in report[0])
check("simulated true", report[0]["simulated"] is True)
check("no browser note", "no browser action" in report[0]["note"])
check("empty simulate", rollback_engine.simulate([]) == [])
section_summary("14. Rollback Engine")

# ─────────────────────────────────────────────────────────────────────────────
# 15. Audit trail
# ─────────────────────────────────────────────────────────────────────────────
section("15. Audit Trail")
eaudit._reset_for_testing()
e = make_audit_entry("exec-1", "step-1", 1, "NAVIGATE", 100.0, 5.0, "SUCCESS", True, 0)
check("audit entry id prefix", e.entry_id.startswith("audit-"))
ed = e.to_dict()
for k in ["entry_id", "execution_id", "step_id", "order", "command_type", "timestamp",
          "duration_ms", "outcome", "validation_passed", "retry_count", "rollback_performed", "message"]:
    check(f"audit.to_dict has {k}", k in ed)
eaudit.append(e)
check("count for execution", eaudit.count_for_execution("exec-1") == 1)
check("total", eaudit.total() == 1)
eaudit.append(make_audit_entry("exec-1", "step-2", 2, "EXTRACT", 101.0, 4.0, "SUCCESS", True, 0))
entries = eaudit.entries_for_execution("exec-1")
check("chronological order", entries[0].order == 1 and entries[1].order == 2)
eaudit.append(make_audit_entry("exec-2", "step-1", 1, "NAVIGATE", 102.0, 5.0, "SUCCESS", True, 0))
check("execution isolation", eaudit.count_for_execution("exec-2") == 1)
check("empty execution", eaudit.entries_for_execution("absent") == [])
check("recent global", len(eaudit.recent_global()) >= 1)
for k in ["total_entries", "execution_keys", "global_buffered"]:
    check(f"audit.stats has {k}", k in eaudit.stats())
section_summary("15. Audit Trail")

# ─────────────────────────────────────────────────────────────────────────────
# 16. Runner — happy path
# ─────────────────────────────────────────────────────────────────────────────
section("16. Runner — Happy Path")
_reset_all()
plan = _ready_plan()
rec = make_execution(plan.plan_id, plan.authorization_id, mission_id="m-1", task_id="t-1",
                     total_steps=len(plan.steps), adapter_name="mock", created_at=100.0)
done = erunner.run(rec, plan, MockBrowserAdapter())
check("completed", done.state == ExecutionState.completed)
check("3 completed steps", done.completed_steps == 3)
check("0 failed", done.failed_steps == 0)
check("all success", all(s.outcome == StepOutcome.success for s in done.step_executions))
check("index advanced", done.current_step_index == 3)
check("started set", done.started_at is not None)
check("finished set", done.finished_at is not None)
check("command types", [s.command_type for s in done.step_executions] == ["NAVIGATE", "EXTRACT", "VALIDATE"])
check("audit per step", eaudit.count_for_execution(done.execution_id) == 3)
check("duration positive", done.total_duration_ms > 0)
section_summary("16. Runner — Happy Path")

# ─────────────────────────────────────────────────────────────────────────────
# 17. Runner — failure / retry / rollback
# ─────────────────────────────────────────────────────────────────────────────
section("17. Runner — Failure / Retry / Rollback")
_reset_all()
plan = _ready_plan()
rec = make_execution(plan.plan_id, plan.authorization_id, mission_id="m-1", task_id="t-1",
                     total_steps=len(plan.steps), adapter_name="mock", created_at=100.0)
bad = plan.steps[1].step_id
failed = erunner.run(rec, plan, MockBrowserAdapter(failure_steps={bad}))
check("failed state", failed.state == ExecutionState.failed)
check("stops at failure", failed.current_step_index == 2)
check("2 step execs", len(failed.step_executions) == 2)
check("rollback 1 step", len(failed.rollback_history) == 1)
check("failed step counted", failed.failed_steps == 1)
# retry: flaky succeeds
_reset_all()
plan = _ready_plan()
rec = make_execution(plan.plan_id, plan.authorization_id, mission_id="m-1", task_id="t-1",
                     total_steps=len(plan.steps), adapter_name="mock", created_at=100.0)
flaky = plan.steps[0].step_id
retried = erunner.run(rec, plan, MockBrowserAdapter(flaky_steps={flaky}))
check("flaky completes", retried.state == ExecutionState.completed)
check("flaky 2 attempts", retried.step_executions[0].attempts == 2)
check("total retries 1", retried.total_retries == 1)
# retry exhausted
_reset_all()
plan = _ready_plan()
rec = make_execution(plan.plan_id, plan.authorization_id, mission_id="m-1", task_id="t-1",
                     total_steps=len(plan.steps), adapter_name="mock", created_at=100.0,
                     retry_config=RetryConfig(max_retries=2))
hardbad = plan.steps[0].step_id
exhausted = erunner.run(rec, plan, MockBrowserAdapter(failure_steps={hardbad}))
check("exhausted 3 attempts", exhausted.step_executions[0].attempts == 3)
check("exhausted failed", exhausted.state == ExecutionState.failed)
# validation failure terminal with no retry
_reset_all()
plan = _ready_plan()
rec = make_execution(plan.plan_id, plan.authorization_id, mission_id="m-1", task_id="t-1",
                     total_steps=len(plan.steps), adapter_name="mock", created_at=100.0,
                     retry_config=RetryConfig(max_retries=0))
vbad = plan.steps[0].step_id
valfail = erunner.run(rec, plan, MockBrowserAdapter(validation_fail_steps={vbad}))
check("validation fail state failed", valfail.state == ExecutionState.failed)
check("validation_failed outcome", valfail.step_executions[0].outcome == StepOutcome.validation_failed)
section_summary("17. Runner — Failure / Retry / Rollback")

# ─────────────────────────────────────────────────────────────────────────────
# 18. ExecutionRegistry
# ─────────────────────────────────────────────────────────────────────────────
section("18. ExecutionRegistry")
ereg._reset_for_testing()
def _r(plan="p-1", mission="m-1", created=None):
    return make_execution(plan, "a-1", mission_id=mission, task_id="t-1", total_steps=3,
                          adapter_name="mock", created_at=created if created is not None else time.time())
r1 = _r(); ereg.add(r1)
check("get", ereg.get(r1.execution_id) is not None)
check("get missing", ereg.get("absent") is None)
ereg.add(_r()); check("count 2", ereg.count() == 2)
check("list_all 2", len(ereg.list_all()) == 2)
ereg._reset_for_testing()
ereg.add(_r(mission="m-A")); ereg.add(_r(mission="m-A")); ereg.add(_r(mission="m-B"))
check("list_for_mission m-A", len(ereg.list_for_mission("m-A")) == 2)
ereg._reset_for_testing()
ereg.add(_r(plan="p-A")); ereg.add(_r(plan="p-B"))
check("list_for_plan", len(ereg.list_for_plan("p-A")) == 1)
ereg._reset_for_testing()
rc = _r(mission="m-S"); rc.state = ExecutionState.completed; ereg.add(rc)
rf = _r(mission="m-S"); rf.state = ExecutionState.failed; ereg.add(rf)
s = ereg.summary_for_mission("m-S")
for k in ["total_executions", "running_executions", "completed_executions",
          "failed_executions", "aborted_executions", "latest_execution_id", "latest_state", "execution_ids"]:
    check(f"summary has {k}", k in s)
check("summary completed 1", s["completed_executions"] == 1)
check("summary failed 1", s["failed_executions"] == 1)
check("count_by_state completed", ereg.count_by_state(ExecutionState.completed) == 1)
check("empty summary", ereg.summary_for_mission("absent")["total_executions"] == 0)
for k in ["cached_executions", "total_added", "total_evicted", "running_count", "mission_keys", "plan_keys"]:
    check(f"stats has {k}", k in ereg.stats())
section_summary("18. ExecutionRegistry")

# ─────────────────────────────────────────────────────────────────────────────
# 19. GatewayAnalytics
# ─────────────────────────────────────────────────────────────────────────────
section("19. GatewayAnalytics")
eanal._reset_for_testing()
a0 = eanal.get_analytics()
for k in ["executions_started", "executions_completed", "executions_failed", "executions_aborted",
          "steps_executed", "steps_failed", "total_retries", "rollbacks_performed",
          "total_duration_ms", "avg_steps_per_execution", "avg_duration_ms", "success_rate"]:
    check(f"analytics has {k}", k in a0)
    check(f"analytics {k} initial 0", a0[k] == 0 or a0[k] == 0.0)
eanal.record_started()
check("started 1", eanal.get_analytics()["executions_started"] == 1)
eanal.record_finished(state="COMPLETED", steps_executed=3, steps_failed=0, retries=1, rollbacks=0, duration_ms=15.0)
a1 = eanal.get_analytics()
check("completed 1", a1["executions_completed"] == 1)
check("steps_executed 3", a1["steps_executed"] == 3)
check("retries 1", a1["total_retries"] == 1)
eanal.record_finished(state="FAILED", steps_executed=1, steps_failed=1, retries=0, rollbacks=1, duration_ms=5.0)
a2 = eanal.get_analytics()
check("failed 1", a2["executions_failed"] == 1)
check("rollbacks 1", a2["rollbacks_performed"] == 1)
check("success rate 0.5", a2["success_rate"] == 0.5)
eanal.record_finished(state="ABORTED", steps_executed=0, steps_failed=0, retries=0, rollbacks=1, duration_ms=0.0)
check("aborted 1", eanal.get_analytics()["executions_aborted"] == 1)
eanal._reset_for_testing()
check("reset", eanal.get_analytics()["executions_started"] == 0)
section_summary("19. GatewayAnalytics")

# ─────────────────────────────────────────────────────────────────────────────
# 20. GatewayTimeline
# ─────────────────────────────────────────────────────────────────────────────
section("20. GatewayTimeline")
etl._reset_for_testing()
for et in ["started", "completed", "failed", "paused", "resumed", "aborted", "rolled_back"]:
    etl.record("exec-1", et, mission_id="m-tl")
evs = etl.get("m-tl")
check("7 events", len(evs) == 7)
check("newest first", evs[0]["event_type"] == "rolled_back")
types = {e["event_type"] for e in evs}
for et in ["started", "completed", "failed", "paused", "resumed", "aborted", "rolled_back"]:
    check(f"event {et}", et in types)
for k in ["execution_id", "event_type", "mission_id", "plan_id", "state", "timestamp"]:
    check(f"event has {k}", k in evs[0])
check("get empty", etl.get("absent") == [])
sm = etl.summary("m-tl")
check("summary count 7", sm["event_count"] == 7)
check("summary latest", sm["latest_event"] is not None)
check("missions with executions", "m-tl" in etl.missions_with_executions())
check("recent global", len(etl.recent_global()) >= 7)
section_summary("20. GatewayTimeline")

# ─────────────────────────────────────────────────────────────────────────────
# 21. Gateway preflight
# ─────────────────────────────────────────────────────────────────────────────
section("21. Gateway Preflight")
_reset_all()
plan = _ready_plan()
pf = gateway.preflight(plan)
check("ready plan passes", pf["passed"] is True)
for k in ["plan_ready", "authorization_valid", "mission_active",
          "governance_present", "approval_present", "runtime_present", "browser_sync_present"]:
    check(f"preflight check {k}", k in pf["checks"])
check("plan_ready true", pf["checks"]["plan_ready"] is True)
check("authorization_valid true", pf["checks"]["authorization_valid"] is True)
check("mission_active true", pf["checks"]["mission_active"] is True)
# draft plan fails
set_status(plan.plan_id, PlanStatus.draft)
pf_draft = gateway.preflight(plan_reg.get(plan.plan_id))
check("draft fails", pf_draft["passed"] is False)
check("draft plan_ready false", pf_draft["checks"]["plan_ready"] is False)
# paused mission fails
_reset_all()
plan_paused = _ready_plan(active=False)
check("paused mission fails", gateway.preflight(plan_paused)["checks"]["mission_active"] is False)
# revoked authorization fails
_reset_all()
plan_rev = _ready_plan()
auth_reg.revoke(plan_rev.authorization_id, reason="t")
check("revoked auth fails", gateway.preflight(plan_rev)["checks"]["authorization_valid"] is False)
section_summary("21. Gateway Preflight")

# ─────────────────────────────────────────────────────────────────────────────
# 22. Gateway start
# ─────────────────────────────────────────────────────────────────────────────
section("22. Gateway Start")
_reset_all()
plan = _ready_plan()
rec = gateway.start(plan.plan_id)
check("completes", rec.state == ExecutionState.completed)
check("3 completed", rec.completed_steps == 3)
check("stored", ereg.get(rec.execution_id) is not None)
check("analytics started", eanal.get_analytics()["executions_started"] == 1)
check("analytics completed", eanal.get_analytics()["executions_completed"] == 1)
check("preflight attached", rec.preflight["passed"] is True)
check("adapter mock", rec.adapter_name == "mock")
# missing plan
try:
    gateway.start("no-plan")
    check("missing plan raises", False)
except GatewayError as ge:
    check("missing plan raises", ge.status_code == 404)
# draft plan
_reset_all()
plan2 = _ready_plan()
set_status(plan2.plan_id, PlanStatus.draft)
try:
    gateway.start(plan2.plan_id)
    check("draft raises", False)
except GatewayError as ge:
    check("draft raises 409", ge.status_code == 409)
# auto_run false
_reset_all()
plan3 = _ready_plan()
rec3 = gateway.start(plan3.plan_id, auto_run=False)
check("no autorun pending", rec3.state == ExecutionState.pending)
# failure path
_reset_all()
plan4 = _ready_plan()
bad = plan4.steps[1].step_id
rec4 = gateway.start(plan4.plan_id, adapter=MockBrowserAdapter(failure_steps={bad}))
check("failure path failed", rec4.state == ExecutionState.failed)
check("failure analytics", eanal.get_analytics()["executions_failed"] == 1)
check("failure rollback", len(rec4.rollback_history) == 1)
section_summary("22. Gateway Start")

# ─────────────────────────────────────────────────────────────────────────────
# 23. Gateway pause / resume / abort
# ─────────────────────────────────────────────────────────────────────────────
section("23. Gateway Pause / Resume / Abort")
_reset_all()
plan = _ready_plan()
rec = gateway.start(plan.plan_id, auto_run=False)
paused = gateway.pause(rec.execution_id)
check("pause pending -> paused", paused.state == ExecutionState.paused)
resumed = gateway.resume(rec.execution_id)
check("resume -> completed", resumed.state == ExecutionState.completed)
# pause completed -> error
try:
    gateway.pause(rec.execution_id)
    check("pause completed raises", False)
except GatewayError as ge:
    check("pause completed 409", ge.status_code == 409)
# resume from pending
_reset_all()
plan = _ready_plan()
rec = gateway.start(plan.plan_id, auto_run=False)
check("resume from pending", gateway.resume(rec.execution_id).state == ExecutionState.completed)
# abort pending
_reset_all()
plan = _ready_plan()
rec = gateway.start(plan.plan_id, auto_run=False)
aborted = gateway.abort(rec.execution_id)
check("abort -> aborted", aborted.state == ExecutionState.aborted)
check("abort analytics", eanal.get_analytics()["executions_aborted"] == 1)
# abort completed -> error
_reset_all()
plan = _ready_plan()
rec = gateway.start(plan.plan_id)
try:
    gateway.abort(rec.execution_id)
    check("abort completed raises", False)
except GatewayError as ge:
    check("abort completed 409", ge.status_code == 409)
# missing exec
try:
    gateway.pause("no-exec")
    check("pause missing raises", False)
except GatewayError as ge:
    check("pause missing 404", ge.status_code == 404)
section_summary("23. Gateway Pause / Resume / Abort")

# ─────────────────────────────────────────────────────────────────────────────
# 24. Inspector
# ─────────────────────────────────────────────────────────────────────────────
section("24. Inspector")
_reset_all()
plan = _ready_plan()
rec = gateway.start(plan.plan_id)
ins = einsp.inspect(rec.execution_id)
check("missing none", einsp.inspect("absent") is None)
for k in ["execution_id", "state", "adapter_used", "plan_id", "authorization_id",
          "current_step", "total_steps", "completed_steps", "failed_steps", "remaining_steps",
          "execution_history", "retry_history", "rollback_history", "validation_results",
          "audit_trail", "preflight", "mission_context", "total_retries", "total_duration_ms",
          "analytics", "registry_stats", "audit_stats", "latency_ms"]:
    check(f"inspect has {k}", k in ins)
check("adapter used", ins["adapter_used"] == "mock")
check("state completed", ins["state"] == "COMPLETED")
check("history 3", len(ins["execution_history"]) == 3)
check("validation results 3", len(ins["validation_results"]) == 3)
check("all validations pass", all(v["validation_passed"] for v in ins["validation_results"]))
check("audit 3", len(ins["audit_trail"]) == 3)
check("current_step none when done", ins["current_step"] is None)
check("remaining 0", ins["remaining_steps"] == 0)
check("latency >= 0", ins["latency_ms"] >= 0.0)
check("mission context active", ins["mission_context"]["state"] == "ACTIVE")
# flaky retry history
_reset_all()
plan = _ready_plan()
flaky = plan.steps[0].step_id
rec = gateway.start(plan.plan_id, adapter=MockBrowserAdapter(flaky_steps={flaky}))
check("retry history populated", len(einsp.inspect(rec.execution_id)["retry_history"]) == 1)
section_summary("24. Inspector")

# ─────────────────────────────────────────────────────────────────────────────
# 25. Schemas
# ─────────────────────────────────────────────────────────────────────────────
section("25. Schemas (Pydantic)")
from app.schemas.execution_gateway import (
    StepExecutionSchema, ExecutionRecordSchema, GatewayAnalyticsSchema,
    GatewayInspectorSchema, GatewaySummarySchema,
)
check("step schema", StepExecutionSchema(step_id="s", order=1, action_type="NAVIGATE",
        command_type="NAVIGATE", outcome="SUCCESS", attempts=1, duration_ms=5.0,
        validation_passed=True).outcome == "SUCCESS")
check("record schema", ExecutionRecordSchema(execution_id="e", plan_id="p",
        authorization_id="a", state="PENDING", adapter_name="mock").state == "PENDING")
check("analytics schema", GatewayAnalyticsSchema().executions_started == 0)
check("inspector schema", GatewayInspectorSchema(execution_id="e", state="COMPLETED",
        adapter_used="mock", plan_id="p", authorization_id="a").adapter_used == "mock")
check("summary schema", GatewaySummarySchema().total_executions == 0)
check("record schema success_rate default", GatewayAnalyticsSchema().success_rate == 0.0)
section_summary("25. Schemas (Pydantic)")

# ─────────────────────────────────────────────────────────────────────────────
# 26. REST API
# ─────────────────────────────────────────────────────────────────────────────
section("26. REST API")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
routes = {r.path for r in app.routes}
for path in ["/gateway/start/{plan_id}", "/gateway/pause/{execution_id}",
             "/gateway/resume/{execution_id}", "/gateway/abort/{execution_id}",
             "/gateway/status/{execution_id}", "/gateway/history/{execution_id}",
             "/gateway/analytics", "/gateway/inspect/{execution_id}"]:
    check(f"route {path}", path in routes)
_reset_all()
plan = _ready_plan(mission="m-api", task="t-api")
start = client.post(f"/gateway/start/{plan.plan_id}")
check("start 200", start.status_code == 200)
eid = start.json()["execution_id"]
check("start completed", start.json()["state"] == "COMPLETED")
check("start adapter mock", start.json()["adapter_name"] == "mock")
check("start steps 3", len(start.json()["step_executions"]) == 3)
check("start missing 404", client.post("/gateway/start/no-plan").status_code == 404)
check("status 200", client.get(f"/gateway/status/{eid}").status_code == 200)
check("status missing 404", client.get("/gateway/status/no-exec").status_code == 404)
hist = client.get(f"/gateway/history/{eid}")
check("history 200", hist.status_code == 200)
check("history audit 3", len(hist.json()["audit_trail"]) == 3)
check("history missing 404", client.get("/gateway/history/no-exec").status_code == 404)
check("analytics 200", client.get("/gateway/analytics").status_code == 200)
check("analytics started", client.get("/gateway/analytics").json()["executions_started"] >= 1)
check("inspect 200", client.get(f"/gateway/inspect/{eid}").status_code == 200)
check("inspect missing 404", client.get("/gateway/inspect/no-exec").status_code == 404)
# draft 409
set_status(plan.plan_id, PlanStatus.draft)
check("start draft 409", client.post(f"/gateway/start/{plan.plan_id}").status_code == 409)
set_status(plan.plan_id, PlanStatus.ready)
# pause/resume/abort
eid2 = client.post(f"/gateway/start/{plan.plan_id}?auto_run=false").json()["execution_id"]
check("pause 200", client.post(f"/gateway/pause/{eid2}").json()["state"] == "PAUSED")
check("resume 200", client.post(f"/gateway/resume/{eid2}").json()["state"] == "COMPLETED")
check("pause completed 409", client.post(f"/gateway/pause/{eid2}").status_code == 409)
eid3 = client.post(f"/gateway/start/{plan.plan_id}?auto_run=false").json()["execution_id"]
check("abort 200", client.post(f"/gateway/abort/{eid3}").json()["state"] == "ABORTED")
check("abort missing 404", client.post("/gateway/abort/no-exec").status_code == 404)
section_summary("26. REST API")

# ─────────────────────────────────────────────────────────────────────────────
# 27. End-to-End + cross-layer + mission integration
# ─────────────────────────────────────────────────────────────────────────────
section("27. End-to-End + Cross-Layer")
_reset_all()
plan = _ready_plan(mission="m-e2e", task="t-e2e")
start = client.post(f"/gateway/start/{plan.plan_id}")
eid = start.json()["execution_id"]
check("e2e plan consumed", start.json()["plan_id"] == plan.plan_id)
check("e2e auth consumed", start.json()["authorization_id"] == plan.authorization_id)
check("e2e completed", start.json()["state"] == "COMPLETED")
cmds = [s["command_type"] for s in start.json()["step_executions"]]
check("e2e dispatch commands", cmds == ["NAVIGATE", "EXTRACT", "VALIDATE"])
check("e2e preflight chain", start.json()["preflight"]["checks"]["plan_ready"] is True)
# mission integration
mi = client.get("/mission/m-e2e/inspect")
check("mission inspect 200", mi.status_code == 200)
check("mission has execution_gateway", "execution_gateway" in mi.json())
eg = mi.json()["execution_gateway"]
check("eg not None", eg is not None)
check("eg total >= 1", eg["total_executions"] >= 1)
check("eg completed >= 1", eg["completed_executions"] >= 1)
for k in ["total_executions", "running_executions", "completed_executions",
          "failed_executions", "aborted_executions", "latest_execution_id", "latest_state"]:
    check(f"eg has {k}", k in eg)
# audit ties full chain
audit_resp = client.get(f"/gateway/history/{eid}").json()
check("e2e audit complete", len(audit_resp["audit_trail"]) == 3)
# revoked authorization blocks (cross-layer enforcement)
_reset_all()
plan_rev = _ready_plan()
auth_reg.revoke(plan_rev.authorization_id, reason="t")
check("revoked auth blocks start", client.post(f"/gateway/start/{plan_rev.plan_id}").status_code == 409)
# timeline lifecycle
_reset_all()
plan_tl = _ready_plan(mission="m-tl-e2e")
client.post(f"/gateway/start/{plan_tl.plan_id}")
tl_events = {e["event_type"] for e in etl.get("m-tl-e2e")}
check("timeline started", "started" in tl_events)
check("timeline completed", "completed" in tl_events)
section_summary("27. End-to-End + Cross-Layer")

# ─────────────────────────────────────────────────────────────────────────────
# 28. Safety — no browser code anywhere
# ─────────────────────────────────────────────────────────────────────────────
section("28. Safety — No Browser Code")
contracts_src = pathlib.Path("app/execution_gateway/contracts.py").read_text(encoding="utf-8")
# Real-usage signals only: actual imports + actual browser/automation API calls.
# (Bare library names like "playwright" legitimately appear in the "NO Playwright"
#  constraint docstrings and as future-adapter STUB class names, so we never forbid
#  the bare substring — we forbid importing or calling them.)
forbidden = [
    "import playwright", "from playwright", "import pyppeteer", "from pyppeteer",
    "import selenium", "from selenium", "import webdriver", "from webdriver",
    "playwright.sync_api", "playwright.async_api", "sync_playwright", "async_playwright",
    "page.goto", "page.click", "page.fill", "page.type(", "browser.new_page",
    "document.queryselector", "element.click(", ".send_keys(",
    "import subprocess", "os.system(", "import webbrowser",
    "requests.get(", "requests.post(", "httpx.get(", "httpx.post(", "urllib.request",
    "import anthropic", "import openai", "llm_client", "call_llm", ".generate(",
    "import pytesseract", "import cv2", "cv2.imread",
]
sources = list(pathlib.Path("app/execution_gateway").rglob("*.py"))
check("package has >= 16 modules", len(sources) >= 16)
for src_path in sources:
    text = src_path.read_text(encoding="utf-8", errors="replace").lower()
    for fb in forbidden:
        check(f"NO '{fb}' in {src_path.name}", fb.lower() not in text)
# Positive: every future adapter is declared (interface) but NOT runnable.
check("PlaywrightAdapter declared as stub", "class PlaywrightAdapter" in contracts_src)
check("VisionAdapter declared as stub", "class VisionAdapter" in contracts_src)
check("ChromeCDPAdapter declared as stub", "class ChromeCDPAdapter" in contracts_src)
check("NativeChromeExtensionAdapter declared as stub", "class NativeChromeExtensionAdapter" in contracts_src)
# route + integration wiring
main_src = pathlib.Path("app/main.py").read_text(encoding="utf-8")
check("main registers gateway_router", "gateway_router" in main_src)
mission_schema_src = pathlib.Path("app/schemas/mission.py").read_text(encoding="utf-8")
check("mission schema execution_gateway", "execution_gateway" in mission_schema_src)
mission_route_src = pathlib.Path("app/api/routes/mission.py").read_text(encoding="utf-8")
check("mission route execution_gateway_summary", "execution_gateway_summary" in mission_route_src)
# contracts: future adapters not implemented
check("contracts NotImplementedError", "NotImplementedError" in contracts_src)
check("contracts documents mock-only", "mock-only" in contracts_src or "Phase B" in contracts_src)
# mock adapter declares no real browser
mock_src = pathlib.Path("app/execution_gateway/mock_adapter.py").read_text(encoding="utf-8")
check("mock declares deterministic", "DETERMINISTIC" in mock_src or "deterministic" in mock_src.lower())
section_summary("28. Safety — No Browser Code")

# ─────────────────────────────────────────────────────────────────────────────
# Final tally
# ─────────────────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"PHASE B VALIDATION: {PASS}/{total} checks passed")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL CHECKS PASSED")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
