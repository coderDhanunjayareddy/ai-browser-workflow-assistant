from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from app.mission.v3.models import MissionAttempt, MissionSnapshot, MissionState, MissionStepRef


VALID_TRANSITIONS: dict[str, set[str]] = {
    "created": {"planning", "paused", "cancelled", "failed"},
    "planning": {"executing", "waiting", "replanning", "paused", "completed", "failed", "cancelled"},
    "executing": {"planning", "waiting", "replanning", "recovering", "paused", "failed", "cancelled"},
    "waiting": {"planning", "replanning", "paused", "completed", "failed", "cancelled"},
    "replanning": {"planning", "executing", "recovering", "paused", "failed", "cancelled"},
    "paused": {"planning", "cancelled", "failed"},
    "recovering": {"planning", "executing", "replanning", "paused", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


STATE_MODE = {
    "created": "INITIALIZE",
    "planning": "PLAN",
    "executing": "ACT",
    "waiting": "WAIT",
    "replanning": "REPLAN",
    "paused": "PAUSE",
    "recovering": "RECOVER",
    "completed": "REPORT",
    "failed": "STOP",
    "cancelled": "STOP",
}


class MissionStateMachine:
    def __init__(self, snapshot: MissionSnapshot):
        self.snapshot = snapshot
        self._started = time.perf_counter()

    @classmethod
    def create(cls, *, run_id: str, goal: str = "") -> "MissionStateMachine":
        return cls(
            MissionSnapshot(
                run_id=run_id,
                mission_id=run_id,
                goal=goal,
                current_objective=goal,
                remaining_objectives=[goal] if goal else [],
                progress_summary={"created": True},
                next_expected_action="observe_and_plan",
            )
        )

    def apply_event(
        self,
        *,
        event_type: str,
        payload: dict[str, Any] | None = None,
        event_id: str | None = None,
        step_index: int = 0,
    ) -> MissionSnapshot:
        payload = payload or {}
        if self.snapshot.is_terminal and event_type not in {"mission.replayed"}:
            return self.snapshot
        if event_type == "run.started":
            self._set_goal(payload.get("task") or payload.get("goal") or self.snapshot.goal)
            self.transition("planning")
            self.snapshot.next_expected_action = "planner_decision"
        elif event_type == "observation.captured":
            self.transition("planning")
            self.snapshot.next_expected_action = "planner_decision"
        elif event_type == "planner.responded":
            self._on_planner_response(payload)
        elif event_type == "grounding.resolved":
            self._on_grounding(payload, event_id=event_id, step_index=step_index)
        elif event_type == "execution.completed":
            self._on_execution(payload, event_id=event_id, step_index=step_index)
        elif event_type == "report.verified":
            self._on_report_verified(payload)
        elif event_type == "validation.completed":
            self._on_validation(payload, event_id=event_id, step_index=step_index)
        elif event_type == "goal_convergence.assessed":
            self._on_goal_convergence(payload, event_id=event_id, step_index=step_index)
        elif event_type == "strategy_context.prepared":
            if payload.get("prepared") is True:
                self.transition("recovering")
                self.snapshot.recovery_count += 1
        elif event_type == "planner_recovery.prepared":
            if payload.get("prepared") is True:
                self.transition("recovering")
                self.snapshot.recovery_count += 1
        elif event_type == "mission.paused":
            self.transition("paused")
            self.snapshot.paused = True
            self.snapshot.next_expected_action = "resume"
        elif event_type == "mission.resumed":
            self.snapshot.paused = False
            self.transition("planning")
            self.snapshot.next_expected_action = "planner_decision"
        elif event_type == "run.completed":
            self._complete_objective(self.snapshot.current_objective or self.snapshot.goal)
            self.transition("completed")
            self.snapshot.next_expected_action = "none"
        elif event_type == "run.failed":
            self.snapshot.failure_reason = str(payload.get("reason") or "run_failed")
            self.transition("failed")
            self.snapshot.next_expected_action = "none"
        elif event_type == "run.cancelled":
            self.transition("cancelled")
            self.snapshot.next_expected_action = "none"

        self._append_step(event_type, payload, event_id, step_index)
        self._refresh_progress()
        return self.snapshot

    def transition(self, to_state: MissionState) -> None:
        current = self.snapshot.state
        if current == to_state:
            return
        if to_state not in VALID_TRANSITIONS[current]:
            raise ValueError(f"Invalid mission transition {current} -> {to_state}")
        self.snapshot.state = to_state
        self.snapshot.mode = STATE_MODE[to_state]  # type: ignore[assignment]

    def pause(self) -> MissionSnapshot:
        return self.apply_event(event_type="mission.paused")

    def resume(self) -> MissionSnapshot:
        return self.apply_event(event_type="mission.resumed")

    def clone_snapshot(self) -> MissionSnapshot:
        return self.snapshot.model_validate(deepcopy(self.snapshot.model_dump(mode="json")))

    def _set_goal(self, goal: str) -> None:
        if not goal:
            return
        self.snapshot.goal = goal
        self.snapshot.current_objective = self.snapshot.current_objective or goal
        if goal not in self.snapshot.remaining_objectives and goal not in self.snapshot.completed_objectives:
            self.snapshot.remaining_objectives.append(goal)

    def _on_planner_response(self, payload: dict[str, Any]) -> None:
        self.snapshot.planner_iterations += 1
        outcome = payload.get("outcome_kind")
        if outcome == "act" and int(payload.get("suggested_actions") or 0) > 0:
            self.transition("executing")
            self.snapshot.next_expected_action = "execute_planner_action"
        elif outcome == "wait":
            self.transition("waiting")
            self.snapshot.next_expected_action = "wait_then_observe"
        elif outcome == "ask":
            self.transition("waiting")
            self.snapshot.next_expected_action = "await_user_input"
        elif outcome == "replan":
            self._request_replan("planner_requested_replan")
        elif outcome == "report":
            self.transition("waiting")
            self.snapshot.next_expected_action = "verify_report"
        else:
            self.transition("planning")
            self.snapshot.next_expected_action = "planner_decision"

    def _on_grounding(
        self,
        payload: dict[str, Any],
        *,
        event_id: str | None,
        step_index: int,
    ) -> None:
        status = payload.get("status")
        if status in {"ambiguous", "not_found"}:
            self._request_replan(f"grounding_{status}", event_id=event_id, step_index=step_index)
        elif status == "fallback" and payload.get("fallback_used"):
            self._request_replan("grounding_legacy_fallback", event_id=event_id, step_index=step_index)

    def _on_execution(
        self,
        payload: dict[str, Any],
        *,
        event_id: str | None,
        step_index: int,
    ) -> None:
        if payload.get("success") is True:
            self.snapshot.completed_steps += 1
            self.transition("planning")
            self.snapshot.next_expected_action = "refresh_observation"
            return
        self.snapshot.retry_count += 1
        self._request_replan("execution_failed", event_id=event_id, step_index=step_index)

    def _on_report_verified(self, payload: dict[str, Any]) -> None:
        if payload.get("sgv_verified") is True:
            self._complete_objective(self.snapshot.current_objective or self.snapshot.goal)
            self.transition("completed")
            self.snapshot.next_expected_action = "none"
        else:
            self.transition("planning")
            self.snapshot.next_expected_action = "planner_decision"

    def _on_validation(
        self,
        payload: dict[str, Any],
        *,
        event_id: str | None,
        step_index: int,
    ) -> None:
        status = payload.get("validation_status")
        if status == "satisfied":
            self.transition("planning")
            self.snapshot.next_expected_action = "planner_decision"
        elif status == "contradicted":
            self._request_replan("validation_contradicted", event_id=event_id, step_index=step_index)
        elif status == "not_satisfied":
            category = payload.get("failure_category") or "unknown"
            self._request_replan(f"validation_{category}", event_id=event_id, step_index=step_index)
        elif status == "uncertain":
            self.transition("waiting")
            self.snapshot.next_expected_action = "collect_more_evidence"

    def _on_goal_convergence(
        self,
        payload: dict[str, Any],
        *,
        event_id: str | None,
        step_index: int,
    ) -> None:
        if payload.get("goal_convergence") is True:
            self._request_replan("semantic_stagnation", event_id=event_id, step_index=step_index)

    def _request_replan(
        self,
        reason: str,
        *,
        event_id: str | None = None,
        step_index: int = 0,
    ) -> None:
        self.snapshot.replanning_requested = True
        if reason not in self.snapshot.replan_reasons:
            self.snapshot.replan_reasons.append(reason)
        self.snapshot.attempts.append(
            MissionAttempt(
                attempt=len(self.snapshot.attempts) + 1,
                reason=reason,
                event_id=event_id,
                step_index=step_index,
            )
        )
        self.transition("replanning")
        self.snapshot.next_expected_action = "planner_replan"

    def _complete_objective(self, objective: str) -> None:
        if not objective:
            return
        if objective not in self.snapshot.completed_objectives:
            self.snapshot.completed_objectives.append(objective)
        self.snapshot.remaining_objectives = [
            item for item in self.snapshot.remaining_objectives if item != objective
        ]

    def _append_step(
        self,
        event_type: str,
        payload: dict[str, Any],
        event_id: str | None,
        step_index: int,
    ) -> None:
        summary = _event_summary(event_type, payload)
        self.snapshot.step_history.append(
            MissionStepRef(
                event_id=event_id,
                event_type=event_type,
                step_index=step_index,
                summary=summary,
            )
        )
        self.snapshot.step_history = self.snapshot.step_history[-50:]
        self.snapshot.attempts = self.snapshot.attempts[-20:]

    def _refresh_progress(self) -> None:
        total = len(self.snapshot.completed_objectives) + len(self.snapshot.remaining_objectives)
        progress = len(self.snapshot.completed_objectives) / total if total else 0.0
        self.snapshot.elapsed_ms = int((time.perf_counter() - self._started) * 1000)
        self.snapshot.progress_summary = {
            "progress_estimate": round(progress, 3),
            "planner_iterations": self.snapshot.planner_iterations,
            "completed_steps": self.snapshot.completed_steps,
            "retry_count": self.snapshot.retry_count,
            "replanning_count": len(self.snapshot.replan_reasons),
            "step_history_count": len(self.snapshot.step_history),
        }


def _event_summary(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "planner.responded":
        return f"planner:{payload.get('outcome_kind')} actions={payload.get('suggested_actions', 0)}"
    if event_type == "grounding.resolved":
        return f"grounding:{payload.get('status')}"
    if event_type == "execution.completed":
        return f"execution:success={payload.get('success')}"
    if event_type == "report.verified":
        return f"report:verified={payload.get('sgv_verified')}"
    if event_type == "validation.completed":
        return f"validation:{payload.get('validation_status')}"
    if event_type == "goal_convergence.assessed":
        return f"convergence:{payload.get('goal_convergence')}"
    return event_type
