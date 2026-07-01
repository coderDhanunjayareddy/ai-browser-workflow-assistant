"""
M0.6 — Trace recorder.

Post-run, assembles ONE complete StepTrace per benchmark step by merging three sources,
correlated by trace_id + step order:
  1. M0TaskResult.steps  — executor + validation + observation artifact paths (already recorded)
  2. TracingAnalyzeClient exchanges — the exact request transmitted + parsed response
  3. <trace_dir>/backend/<trace_id>.json — the exact provider prompt + raw response (TRACE_MODE)

No-op when disabled. Never raises into the caller (diagnostics must not break a run).
"""
from __future__ import annotations

import json
import os
from typing import Optional

from benchmark.trace import schema


class TraceRecorder:
    def __init__(self, *, enabled: bool, artifacts_dir: str, out_dir: str, trace_dir: str,
                 run_id: str, session_prefix: str = "benchmark") -> None:
        self.enabled = enabled
        self.artifacts_dir = artifacts_dir
        self.out_dir = out_dir
        self.trace_dir = trace_dir
        self.run_id = run_id
        self.session_prefix = session_prefix

    # ── public ────────────────────────────────────────────────────────────────
    def build_task(self, result, exchanges: list) -> list[dict]:
        """Build + persist step traces for one task result. Returns the list of traces."""
        if not self.enabled:
            return []
        try:
            return self._build_task(result, exchanges)
        except Exception:
            return []   # diagnostics never break the run

    # ── internal ──────────────────────────────────────────────────────────────
    def _build_task(self, result, exchanges: list) -> list[dict]:
        traces: list[dict] = []
        prev_url = ""
        n_steps = len(result.steps)
        for i, step in enumerate(result.steps):
            ex = exchanges[i] if i < len(exchanges) else None
            trace_id = ex.trace_id if ex else f"notrace-{result.task_id}-{i:03d}"
            backend = self._read_backend(trace_id)
            sent_ctx = ex.page_context if ex else {}
            res = ex.result if ex else None

            url = step.url_after or sent_ctx.get("url", "")
            url_changed = bool(prev_url) and (url != prev_url)
            dom_changed = "dom_changed=True" in (step.validation_detail or "")

            obs = schema.observation(
                url=url, title=sent_ctx.get("title", ""),
                dom_snapshot=self._artifact("dom_snapshots", result.task_id, f"step_{i:03d}.json"),
                screenshot_before=self._shot(result.task_id, i - 1, "post_action") if i > 0
                                  else self._shot(result.task_id, 0, "baseline"),
                screenshot_after=self._shot(result.task_id, i, "post_action"),
                visible_text_summary=(sent_ctx.get("visible_text", "") or "")[:400],
                interactive_element_count=len(sent_ctx.get("interactive_elements", []) or []),
                elements_summary=self._elements_summary(sent_ctx))

            pin = schema.planner_input(
                task=ex.task if ex else result.task_id,
                page_context_sent=sent_ctx,
                prior_steps_sent=ex.prior_steps if ex else [],
                compressed_context=None,   # embedded inside the assembled prompt (provider_request)
                system_prompt_version=None,
                model=(backend or {}).get("request", {}).get("model") if backend else None,
                timestamp=ex.timestamp if ex else 0.0)

            preq = schema.provider_request(backend)
            action = res.first_action if res else None
            pres = schema.provider_response(
                backend,
                parsed={"analysis": res.analysis if res else "",
                        "suggested_actions": [a.__dict__ for a in (res.suggested_actions if res else [])],
                        "clarification_question": res.clarification_question if res else None},
                parse_error=ex.error if ex else None)

            pact = schema.parsed_action(
                analysis=res.analysis if res else "",
                action_type=action.action_type if action else step.action_type,
                target=action.target_selector if action else step.action_selector,
                value=action.value if action else step.action_value,
                reasoning=action.reasoning if action else None,
                confidence=action.confidence if action else None,
                clarification=res.clarification_question if res else None)

            exec_rec = schema.executor(
                locator_strategy=step.locator_strategy, selector_used=step.action_selector,
                locator_attempts=step.locator_attempts, start_ms=0.0, end_ms=step.execute_ms,
                duration_ms=step.execute_ms,
                result="success" if step.execution_success else "failed",
                browser_error=step.error_detail or None)

            val = schema.validation(
                validation_type="dom_signature+success_criteria",
                passed=step.validation_passed, reason=step.validation_detail or "",
                dom_changed=dom_changed, url_changed=url_changed,
                success_criteria_satisfied=(result.is_completed and i == n_steps - 1))

            decision = self._decision(step, i, n_steps, result)

            trace = schema.step_trace(
                trace_id=trace_id, run_id=self.run_id, task_id=result.task_id,
                session_id=f"{self.session_prefix}_{result.task_id}_{self.run_id}", step_index=i,
                observation=obs, planner_input=pin, provider_request=preq, provider_response=pres,
                parsed_action=pact, executor=exec_rec, validation=val, loop_decision=decision)
            traces.append(trace)
            self._write(result.task_id, i, trace)
            prev_url = url

        self._write_index(result.task_id, traces, result)
        return traces

    def _decision(self, step, i, n, result) -> dict:
        if i < n - 1:
            if step.is_recovery:
                return schema.loop_decision(decision="recovered",
                                            reason="executor reported failure; retrying (retry_budget)")
            return schema.loop_decision(decision="continue",
                                        reason="success criteria not yet satisfied; observe next state")
        # last recorded step → terminal decision mirrors the task status
        status = result.status.value if hasattr(result.status, "value") else str(result.status)
        reason = result.failure_detail or ""
        mapping = {
            "COMPLETED": ("completed", "all success criteria satisfied"),
            "STUCK":     ("stuck", reason or "3 consecutive identical (action,page-signature) steps"),
            "FAILED":    ("failed", reason or "recovery budget exhausted"),
            "TIMEOUT":   ("timeout", reason or "max_steps / timeout_ms reached"),
            "BLOCKED":   ("blocked", reason or "site defense / human-required"),
        }
        d, r = mapping.get(status, ("continue", reason))
        return schema.loop_decision(decision=d, reason=r)

    def _elements_summary(self, ctx: dict, cap: int = 12) -> list[dict]:
        out = []
        for el in (ctx.get("interactive_elements") or [])[:cap]:
            out.append({"selector": el.get("selector"), "text": (el.get("text") or "")[:60],
                        "role": el.get("role")})
        return out

    def _artifact(self, kind: str, task_id: str, name: str) -> Optional[str]:
        rel = os.path.join(kind, self.run_id, task_id, name)
        return rel if os.path.exists(os.path.join(self.artifacts_dir, rel)) else None

    def _shot(self, task_id: str, idx: int, event: str) -> Optional[str]:
        if idx < 0:
            return None
        return self._artifact("screenshots", task_id, f"step_{idx:03d}_{event}.png")

    def _read_backend(self, trace_id: str) -> Optional[dict]:
        path = os.path.join(self.trace_dir, "backend", f"{trace_id}.json")
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _write(self, task_id: str, i: int, trace: dict) -> None:
        d = os.path.join(self.out_dir, self.run_id, task_id)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"step_{i:03d}.trace.json"), "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)

    def _write_index(self, task_id: str, traces: list[dict], result) -> None:
        d = os.path.join(self.out_dir, self.run_id, task_id)
        os.makedirs(d, exist_ok=True)
        index = {
            "schema_version": schema.SCHEMA_VERSION,
            "run_id": self.run_id, "task_id": task_id,
            "status": result.status.value if hasattr(result.status, "value") else str(result.status),
            "failure_category": result.failure_category, "steps": len(traces),
            "step_files": [f"step_{i:03d}.trace.json" for i in range(len(traces))],
        }
        with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
