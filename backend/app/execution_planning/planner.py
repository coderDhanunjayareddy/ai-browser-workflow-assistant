"""
V9.0 Execution Planning Layer — ExecutionPlanner.

Turns an ExecutionAuthorization (plus optional mission / runtime / workflow-graph
context) into a deterministic ExecutionPlan.

DETERMINISTIC. No LLM. No AI. No browser actions. No network.
Same inputs always yield the same plan structure (step ids / created_at aside).

CRITICAL CONTRACT (Component 10):
  The planner accepts ONLY an ExecutionAuthorization. It must NEVER be handed a
  GovernanceContract, ApprovalRequest, or TrustEvaluation. This is enforced by an
  explicit type/shape check.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.authorization.models import ExecutionAuthorization
from app.execution_planning import rollback as rollback_planner
from app.execution_planning.models import (
    ACTION_PROFILE,
    ActionType,
    ExecutionMode,
    ExecutionPlan,
    ExecutionStep,
    TargetType,
    ValidationStrategy,
    make_plan,
    make_step,
)


# Deterministic keyword → (ActionType, TargetType) inference for workflow nodes.
_ACTION_KEYWORDS: list[tuple[tuple[str, ...], ActionType, TargetType]] = [
    (("navigate", "go to", "open", "visit"), ActionType.navigate, TargetType.url),
    (("click", "press", "submit", "button", "tap"),  ActionType.click,    TargetType.element),
    (("type", "enter", "fill", "input"),             ActionType.input,    TargetType.form),
    (("extract", "scrape", "collect", "gather"),     ActionType.extract,  TargetType.region),
    (("read", "view"),                               ActionType.read,     TargetType.page),
    (("scroll",),                                    ActionType.scroll,   TargetType.page),
    (("wait", "pause", "delay"),                     ActionType.wait,     TargetType.page),
    (("verify", "validate", "check", "confirm"),     ActionType.validate, TargetType.page),
]


class PlannerInputError(TypeError):
    """Raised when the planner is handed anything other than an ExecutionAuthorization."""


class ExecutionPlanner:

    VERSION = "1.0"

    # ── public entry point ────────────────────────────────────────────────────

    def create_plan(
        self,
        authorization: ExecutionAuthorization,
        *,
        mission:          Any = None,
        runtime_context:  Any = None,
        workflow_graph:   Any = None,
        now:              Optional[float] = None,
    ) -> ExecutionPlan:
        self._assert_is_authorization(authorization)
        created_at = now if now is not None else time.time()

        target_url = self._resolve_target_url(runtime_context, mission)
        objective  = self._resolve_objective(mission)

        # 1. Build steps — from a workflow graph if given, else canonical template.
        if workflow_graph is not None and getattr(workflow_graph, "nodes", None):
            steps = self._steps_from_graph(workflow_graph, authorization, target_url, objective)
        else:
            steps = self._canonical_steps(authorization, target_url, objective)

        # 2. Rollback support across the plan.
        rollback_supported = rollback_planner.is_supported(steps)

        # 3. Deterministic estimates.
        duration_ms = sum(ACTION_PROFILE[s.action_type]["duration_ms"] for s in steps)

        # 4. Execution mode (deterministic rule).
        mode = self._choose_mode(authorization, steps, rollback_supported)

        # 5. Deterministic confidence.
        confidence = self._confidence(steps, runtime_context, rollback_supported)

        return make_plan(
            authorization_id      = authorization.authorization_id,
            mission_id            = authorization.mission_id,
            task_id               = authorization.task_id,
            created_at            = created_at,
            execution_mode        = mode,
            steps                 = steps,
            estimated_duration_ms = duration_ms,
            rollback_supported    = rollback_supported,
            confidence            = confidence,
            metadata              = {
                "risk_level":     authorization.risk_level,
                "target_url":     target_url,
                "objective":      objective,
                "source":         "workflow_graph" if (workflow_graph is not None and getattr(workflow_graph, "nodes", None)) else "canonical",
                "planner_version": self.VERSION,
            },
        )

    # ── guards ────────────────────────────────────────────────────────────────

    @staticmethod
    def _assert_is_authorization(obj: Any) -> None:
        if not isinstance(obj, ExecutionAuthorization):
            raise PlannerInputError(
                "ExecutionPlanner accepts ONLY ExecutionAuthorization; "
                f"got {type(obj).__name__}. GovernanceContract / ApprovalRequest / "
                "TrustEvaluation are forbidden inputs."
            )

    # ── step builders ─────────────────────────────────────────────────────────

    def _canonical_steps(
        self,
        auth:       ExecutionAuthorization,
        target_url: str,
        objective:  str,
    ) -> list[ExecutionStep]:
        scope = self._approval_scope(auth)
        steps = [
            make_step(
                1, ActionType.navigate, TargetType.url, target_url,
                parameters={"url": target_url},
                expected_result=f"page at {target_url} loaded",
                approval_scope=scope,
            ),
            make_step(
                2, ActionType.extract, TargetType.region, "primary content region",
                parameters={"objective": objective},
                expected_result=objective or "content extracted",
                approval_scope=scope,
            ),
            make_step(
                3, ActionType.validate, TargetType.page, "result page",
                parameters={"objective": objective},
                expected_result="objective satisfied",
                approval_scope=scope,
            ),
        ]
        return steps

    def _steps_from_graph(
        self,
        graph:      Any,
        auth:       ExecutionAuthorization,
        target_url: str,
        objective:  str,
    ) -> list[ExecutionStep]:
        scope = self._approval_scope(auth)
        steps: list[ExecutionStep] = []
        for idx, node in enumerate(graph.nodes, start=1):
            action_type, target_type = self._infer_action(getattr(node, "description", ""))
            desc = getattr(node, "description", f"node {idx}") or f"node {idx}"
            params: dict[str, Any] = {"node_id": getattr(node, "node_id", f"n{idx}")}
            prereq = getattr(node, "prerequisites", None)
            if prereq:
                params["prerequisites"] = list(prereq)
            if action_type == ActionType.navigate:
                params["url"] = target_url
            steps.append(make_step(
                idx, action_type, target_type, desc,
                parameters=params,
                expected_result=f"{desc} completed",
                approval_scope=scope,
            ))
        return steps

    @staticmethod
    def _infer_action(description: str) -> tuple[ActionType, TargetType]:
        d = (description or "").lower()
        for keywords, at, tt in _ACTION_KEYWORDS:
            if any(k in d for k in keywords):
                return at, tt
        return ActionType.read, TargetType.page

    # ── deterministic estimators ──────────────────────────────────────────────

    @staticmethod
    def _choose_mode(
        auth:               ExecutionAuthorization,
        steps:              list[ExecutionStep],
        rollback_supported: bool,
    ) -> ExecutionMode:
        if (auth.risk_level or "").upper() == "CRITICAL":
            return ExecutionMode.dry_run
        mutating = any(s.is_mutating for s in steps)
        if mutating and rollback_supported:
            return ExecutionMode.atomic
        return ExecutionMode.sequential

    @staticmethod
    def _confidence(
        steps:              list[ExecutionStep],
        runtime_context:    Any,
        rollback_supported: bool,
    ) -> float:
        score = 0.5
        has_url = bool(runtime_context is not None and getattr(runtime_context, "last_url", None))
        if has_url:
            score += 0.2
        if steps and all(s.validation_strategy != ValidationStrategy.none for s in steps):
            score += 0.2
        if rollback_supported:
            score += 0.1
        return round(max(0.0, min(1.0, score)), 4)

    # ── context resolvers ─────────────────────────────────────────────────────

    @staticmethod
    def _resolve_target_url(runtime_context: Any, mission: Any) -> str:
        if runtime_context is not None:
            url = getattr(runtime_context, "last_url", None)
            if url:
                return url
        if mission is not None:
            md = getattr(mission, "metadata", None) or {}
            if isinstance(md, dict) and md.get("target_url"):
                return md["target_url"]
        return "about:blank"

    @staticmethod
    def _resolve_objective(mission: Any) -> str:
        if mission is not None:
            obj = getattr(mission, "objective", None)
            if obj:
                return obj
        return ""

    @staticmethod
    def _approval_scope(auth: ExecutionAuthorization) -> str:
        return f"authorization:{auth.authorization_id}:{auth.risk_level}"


# ── Module-level singleton ────────────────────────────────────────────────────

_planner = ExecutionPlanner()


def create_plan(authorization: ExecutionAuthorization, **kwargs) -> ExecutionPlan:
    return _planner.create_plan(authorization, **kwargs)
