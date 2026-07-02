"""
M0 — Task runner (the observe -> analyze -> gate -> execute -> validate loop for one task).

Drives a single M0TaskDefinition through the live loop against a Driver until the task
completes, times out, gets blocked, gets stuck, or fails. Completion is detected by
re-evaluating the task's success_criteria after every step (there is no `task_complete`
action in the live system). Each iteration is recorded as an M0StepRecord; the task ends
with an M0TaskResult.

This module is driver-agnostic and client-agnostic: pass any Driver and any object with an
`analyze(...)` method. Unit tests inject fakes, so the whole loop is testable with no
browser and no network.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Optional

from benchmark.m0_models import (
    M0TaskDefinition, M0TaskResult, M0StepRecord, TaskStatus, FailureCategory,
)
from benchmark.analyze_client import AnalyzeError, classify_risk, gate_decision
from benchmark.criteria import EvalContext, evaluate_success, evaluate_failure, all_passed
from benchmark.failure_classifier import FailureSignal, classify
from benchmark.m0_executor import Driver, ExecResult


# task_ids whose targets are canvas/coordinate-only (no DOM equivalent) — used to tag
# the failure as VISION_REQUIRED rather than GROUNDING when the agent cannot proceed.
_VISUAL_TASKS = {"docs_google_com__create_type", "sheets_google_com__enter_data"}


class TaskRunner:
    def __init__(self, *, driver: Driver, client, executor_mode: str,
                 run_id: str, artifacts_dir: str, session_prefix: str = "benchmark",
                 auto_approve: bool = True) -> None:
        self.driver = driver
        self.client = client
        self.executor_mode = executor_mode
        self.run_id = run_id
        self.artifacts_dir = artifacts_dir
        self.session_prefix = session_prefix
        self.auto_approve = auto_approve

    # ── public entry ──────────────────────────────────────────────────────────
    def run(self, task: M0TaskDefinition) -> M0TaskResult:
        result = M0TaskResult(
            task_id=task.task_id, website=task.website, difficulty=task.difficulty.value,
            category=task.category.value, executor_mode=self.executor_mode,
            expect_failure=task.expect_failure, started_at=time.time(),
        )
        t_start = time.perf_counter()
        sess_id = f"{self.session_prefix}_{task.task_id}_{self.run_id}"

        # ── SETUP ──────────────────────────────────────────────────────────────
        try:
            if task.preconditions.pre_navigation:
                self.driver.navigate(task.preconditions.pre_navigation)
            self.driver.navigate(task.start_url)
            self.driver.wait_stable()
            self._shot(task, result, 0, "baseline")
        except Exception as e:
            return self._finalize_error(task, result, t_start, e, phase="setup")

        prior_steps: list[dict] = []
        analysis_texts: list[str] = []
        last_sig: Optional[str] = None
        same_streak = 0
        recoveries_used = 0
        deadline = t_start + task.timeout_ms / 1000.0

        # ── LOOP ─────────────────────────────────────────────────────────────--
        while len(result.steps) < task.max_steps:
            if time.perf_counter() > deadline:
                return self._finalize_timeout(task, result, t_start, "timeout_ms exceeded")

            # captcha / block pre-check
            if self.driver.detect_captcha():
                return self._finalize_blocked(task, result, t_start, FailureCategory.blocked_captcha,
                                               "captcha challenge detected")

            step = M0StepRecord(index=len(result.steps))

            # OBSERVE
            page_context, step.observe_ms = self._timed(self.driver.capture)
            self._save_dom(task, result, step.index, page_context)
            step.url_after = self.driver.current_url()

            ctx = self._ctx(page_context, analysis_texts, len(result.steps))

            # failure-criteria gate (site error / rate-limit / auth redirect)
            trip = evaluate_failure(task.failure_criteria, ctx)
            if trip is not None:
                result.steps.append(step)
                cat = self._classify_block_or_fail(task, trip, page_context, ctx)
                return self._finalize_with_category(task, result, t_start, cat, trip.observed)

            # completion can be satisfied with zero further actions (e.g. navigation-only)
            pre = evaluate_success(task.success_criteria, ctx)
            if all_passed(pre):
                result.criteria_results = pre
                return self._finalize_status(task, result, t_start, TaskStatus.completed)

            # ANALYZE (real /analyze)
            try:
                ar, step.analyze_ms = self._timed(
                    lambda: self.client.analyze(session_id=sess_id, task=task.goal,
                                                page_context=page_context, prior_steps=prior_steps))
            except AnalyzeError as e:
                step.ai_called = True
                step.error_detail = str(e)
                result.steps.append(step)
                cat = (FailureCategory.blocked_rate_limit if e.status_code == 429
                       else FailureCategory.infrastructure)
                return self._finalize_with_category(task, result, t_start, cat, str(e))

            step.ai_called = True
            step.prompt_tokens = ar.prompt_tokens
            step.completion_tokens = ar.completion_tokens
            if ar.analysis:
                analysis_texts.append(ar.analysis)
            action = ar.first_action

            if action is None:
                # nothing to do: maybe already complete (recheck with fresh analysis), else gave up
                recheck = evaluate_success(task.success_criteria,
                                           self._ctx(page_context, analysis_texts, len(result.steps)))
                result.steps.append(step)
                if all_passed(recheck):
                    result.criteria_results = recheck
                    return self._finalize_status(task, result, t_start, TaskStatus.completed)
                step.failure_category = FailureCategory.planning.value
                return self._finalize_with_category(
                    task, result, t_start, FailureCategory.planning,
                    "no action suggested" + (f"; clarification={ar.clarification_question!r}"
                                             if ar.clarification_question else ""))

            step.action_type = action.action_type
            step.action_selector = action.target_selector
            step.action_value = action.value

            # GATE (trust + approval)
            risk = classify_risk(action)
            step.safety_level = risk
            decision = gate_decision(risk, task.human_intervention_rules)
            if decision in ("human", "block"):
                step.human_intervention = True
                interventions = sum(1 for s in result.steps if s.human_intervention) + 1
                if decision == "block" or interventions > task.human_intervention_rules.max_human_interventions:
                    result.steps.append(step)
                    return self._finalize_human_required(
                        result, t_start, f"requires human approval for {risk} action")

            # EXECUTE
            action_dict = {
                "action_id": action.action_id, "action_type": action.action_type,
                "target_selector": action.target_selector, "value": action.value,
                "description": action.description,
            }
            before_url = self.driver.current_url()
            before_sig = self._signature(page_context)
            ex, step.execute_ms = self._timed(lambda: self._execute(action_dict))
            step.executed = True
            step.execution_success = ex.success
            step.locator_strategy = ex.locator_strategy
            step.locator_attempts = ex.locator_attempts
            if not ex.success:
                step.error_detail = ex.message
            # M2: executor-level (DOM-diagnosed) recovery is distinct from the loop's own
            # LLM-retry recovery below — it happens transparently within this one step.
            if ex.recovery_attempted:
                step.is_recovery = True
                step.recovery_success = ex.success

            # WAIT + re-observe for validation
            self.driver.wait_stable(max_ms=3000)
            self._shot(task, result, step.index, "post_action")
            after_context, _ = self._timed(self.driver.capture)
            after_url = self.driver.current_url()
            after_sig = self._signature(after_context)
            step.url_after = after_url
            dom_changed = (after_url != before_url) or (after_sig != before_sig)

            # VALIDATE (step-level): action had observable effect AND/OR criteria moving
            ctx2 = self._ctx(after_context, analysis_texts, len(result.steps) + 1)
            succ2 = evaluate_success(task.success_criteria, ctx2)
            t_val = time.perf_counter()
            step.validation_passed = bool(ex.success and (dom_changed or all_passed(succ2)))
            step.validation_detail = f"exec={ex.success} dom_changed={dom_changed}"
            step.validate_ms = (time.perf_counter() - t_val) * 1000

            # record prior step for the next /analyze call
            prior_steps.append({
                "action_type": action.action_type, "description": action.description,
                "target_selector": action.target_selector, "value": action.value,
                "execution_result": "success" if ex.success else ex.message,
                "page_url": after_url, "page_title": after_context.get("title", ""),
            })

            result.steps.append(step)

            # COMPLETION
            if all_passed(succ2):
                result.criteria_results = succ2
                return self._finalize_status(task, result, t_start, TaskStatus.completed)

            # RECOVERY: retry only when the executor itself reported failure. A successful
            # action with no net DOM-signature change (a fill, an equal-length text swap,
            # a state toggle) is NOT a failure — completion is governed by success_criteria
            # and the step budget, with STUCK detection as the backstop. (RC-1)
            if not ex.success:
                if recoveries_used < task.retry_budget:
                    recoveries_used += 1
                    step.is_recovery = True       # this step's failure triggers a recovery next iter
                    # leave a breadcrumb so the model re-grounds
                    prior_steps[-1]["execution_result"] = (
                        f"FAILED: {ex.message or 'no effect'} — try a different element or wait")
                else:
                    cat = self._classify_step_failure(task, step, after_context, ex,
                                                       dom_changed, recovered=True)
                    return self._finalize_with_category(task, result, t_start, cat, ex.message or "no effect")

            # STUCK detection: identical observation + same action repeatedly
            sig_action = f"{after_sig}|{action.action_type}|{action.target_selector}"
            if last_sig == sig_action:
                same_streak += 1
            else:
                same_streak = 0
            last_sig = sig_action
            if same_streak >= 2:
                return self._finalize_status(task, result, t_start, TaskStatus.stuck,
                                             failure=FailureCategory.planning,
                                             detail="no progress across repeated identical steps")

        # budget exhausted without completion
        return self._finalize_timeout(task, result, t_start, "max_steps reached")

    # ── execution dispatch ──────────────────────────────────────────────────--
    def _execute(self, action_dict: dict) -> ExecResult:
        if self.executor_mode == "synthetic":
            return self.driver.execute_synthetic(action_dict)
        return self.driver.execute_playwright(action_dict)

    # ── context + signatures ──────────────────────────────────────────────────
    def _ctx(self, page_context: dict, analysis_texts: list[str], steps_taken: int) -> EvalContext:
        status = self.driver.last_navigation_status()
        http_errors = [str(status)] if status and status >= 400 else []
        return EvalContext(
            final_url=page_context.get("url", "") or self.driver.current_url(),
            page_text=page_context.get("visible_text", ""),
            analysis_texts=list(analysis_texts),
            steps_taken=steps_taken,
            http_errors=http_errors,
            rate_limited=(status == 429),
            element_present=self.driver.element_present,
        )

    @staticmethod
    def _signature(page_context: dict) -> str:
        basis = (page_context.get("url", "") + "|"
                 + str(len(page_context.get("visible_text", ""))) + "|"
                 + str(len(page_context.get("interactive_elements", []))))
        return hashlib.md5(basis.encode("utf-8")).hexdigest()

    # ── classification helpers ──────────────────────────────────────────────--
    def _classify_block_or_fail(self, task, trip, page_context, ctx) -> FailureCategory:
        sig = FailureSignal(phase="loop", page_text=page_context.get("visible_text", ""),
                            final_url=ctx.final_url,
                            http_status=self.driver.last_navigation_status(),
                            is_cross_site=(task.category.value == "CROSS_SITE"))
        return classify(sig)

    def _classify_step_failure(self, task, step, page_context, ex: ExecResult,
                               dom_changed: bool, recovered: bool) -> FailureCategory:
        locator_all_failed = (ex.locator_strategy is None and step.action_type
                              not in ("navigate", "wait", "scroll", "keyboard_shortcut"))
        sig = FailureSignal(
            phase="execute", error_type=ex.error_type, error_message=ex.message,
            page_text=page_context.get("visible_text", ""),
            final_url=self.driver.current_url(),
            http_status=self.driver.last_navigation_status(),
            locator_all_failed=locator_all_failed,
            executed=step.executed, dom_changed=dom_changed,
            element_in_dom=True, recovery_attempted=recovered,
            is_cross_site=(task.category.value == "CROSS_SITE"),
            needs_visual=(task.task_id in _VISUAL_TASKS),
        )
        return classify(sig)

    # ── finalizers ──────────────────────────────────────────────────────────--
    def _finalize_status(self, task, result, t_start, status: TaskStatus,
                         failure: Optional[FailureCategory] = None, detail: str = "") -> M0TaskResult:
        result.status = status
        if failure is not None:
            result.failure_category = failure.value
            result.failure_detail = detail
        if not result.criteria_results:
            result.criteria_results = evaluate_success(
                task.success_criteria, self._ctx({"url": self.driver.current_url(),
                                                  "visible_text": ""}, [], result.steps_taken))
        return self._stamp(result, t_start)

    def _finalize_with_category(self, task, result, t_start, cat: FailureCategory,
                                detail: str) -> M0TaskResult:
        from benchmark.m0_models import BLOCKED_CATEGORIES
        result.failure_category = cat.value
        result.failure_detail = detail
        result.status = TaskStatus.blocked if cat in BLOCKED_CATEGORIES else TaskStatus.failed
        return self._stamp(result, t_start)

    def _finalize_blocked(self, task, result, t_start, cat: FailureCategory,
                          detail: str) -> M0TaskResult:
        result.status = TaskStatus.blocked
        result.failure_category = cat.value
        result.failure_detail = detail
        return self._stamp(result, t_start)

    def _finalize_human_required(self, result, t_start, detail: str) -> M0TaskResult:
        # human approval needed in an unattended run => BLOCKED (not an agent failure)
        result.status = TaskStatus.blocked
        result.failure_category = "HUMAN_REQUIRED"
        result.failure_detail = detail
        return self._stamp(result, t_start)

    def _finalize_timeout(self, task, result, t_start, detail: str) -> M0TaskResult:
        result.status = TaskStatus.timeout
        result.failure_category = FailureCategory.timeout.value
        result.failure_detail = detail
        return self._stamp(result, t_start)

    def _finalize_error(self, task, result, t_start, exc: Exception, phase: str) -> M0TaskResult:
        sig = FailureSignal(phase=phase, error_type=type(exc).__name__, error_message=str(exc),
                            final_url=self._safe_url())
        cat = classify(sig)
        from benchmark.m0_models import BLOCKED_CATEGORIES
        result.failure_category = cat.value
        result.failure_detail = f"{type(exc).__name__}: {str(exc)[:200]}"
        result.status = TaskStatus.blocked if cat in BLOCKED_CATEGORIES else TaskStatus.error
        return self._stamp(result, t_start)

    def _stamp(self, result: M0TaskResult, t_start: float) -> M0TaskResult:
        result.duration_ms = (time.perf_counter() - t_start) * 1000
        result.final_url = self._safe_url()
        return result

    def _safe_url(self) -> str:
        try:
            return self.driver.current_url()
        except Exception:
            return ""

    # ── artifacts ──────────────────────────────────────────────────────────--
    def _shot(self, task, result: M0TaskResult, idx: int, event: str) -> None:
        path = os.path.join(self.artifacts_dir, "screenshots", self.run_id, task.task_id,
                            f"step_{idx:03d}_{event}.png")
        saved = self.driver.screenshot(path)
        if saved:
            result.screenshots.append(os.path.relpath(saved, self.artifacts_dir))

    def _save_dom(self, task, result: M0TaskResult, idx: int, page_context: dict) -> None:
        path = os.path.join(self.artifacts_dir, "dom_snapshots", self.run_id, task.task_id,
                            f"step_{idx:03d}.json")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(page_context, f, ensure_ascii=False)
            result.dom_snapshots.append(os.path.relpath(path, self.artifacts_dir))
        except Exception:
            pass

    @staticmethod
    def _timed(fn):
        t0 = time.perf_counter()
        out = fn()
        return out, (time.perf_counter() - t0) * 1000
