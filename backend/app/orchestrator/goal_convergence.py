"""Production Goal Convergence (GC-1).

Passive semantic stagnation detection for production workflows.

This module is intentionally observer-only. It never changes planner outcomes,
creates actions, triggers recovery, or changes prompts. It only returns whether
the current session has repeated unchanged semantic evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from benchmark.goal_convergence import ConvergenceEvidence, GoalConvergenceEngine

from app.schemas.request import PageContext
from app.schemas.response import AnalyzeResponse


@dataclass(frozen=True)
class ProductionConvergenceResult:
    goal_convergence: bool
    semantic_signature: str


_ENGINES: dict[str, GoalConvergenceEngine] = {}


def reset_goal_convergence(session_id: str) -> None:
    """Clear convergence state for a session."""
    _ENGINES.pop(session_id, None)


def semantic_signature(page_context: PageContext) -> str:
    """Build the production semantic signature from existing page evidence only."""
    semantic_basis = {
        "url": page_context.url,
        "title": page_context.title,
        "visible_text": page_context.visible_text,
        "headings": page_context.headings,
        "selected_text": page_context.selected_text,
        "content_blocks": [block.text for block in page_context.content_blocks],
        "interactive_elements": [
            _element_signature(element)
            for element in page_context.interactive_elements
        ],
    }
    raw = json.dumps(semantic_basis, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def assess_goal_convergence(
    *,
    session_id: str,
    page_context: PageContext,
    planner_response: AnalyzeResponse,
) -> ProductionConvergenceResult:
    """Return whether semantic progress has stalled for this session."""
    signature = semantic_signature(page_context)
    engine = _ENGINES.setdefault(session_id, GoalConvergenceEngine())

    decision = engine.assess(ConvergenceEvidence(
        outcome_kind=planner_response.outcome_kind,
        strategy_key=planner_response.outcome_kind,
        semantic_signature=signature,
        validation_signature=_validation_signature(planner_response),
        verified=planner_response.sgv_verified,
    ))
    return ProductionConvergenceResult(
        goal_convergence=decision.should_replan,
        semantic_signature=signature,
    )


def _validation_signature(planner_response: AnalyzeResponse) -> str:
    if planner_response.outcome_kind == "report":
        return f"report_verified={planner_response.sgv_verified}"
    return "validation=not_applicable"


def _element_signature(element) -> dict:
    state = element.state or {}
    input_type = (element.input_type or "").lower()

    value = state.get("value")
    if input_type == "password":
        value = "filled" if str(value or "").strip() else "empty"

    return {
        "type": element.type,
        "text": element.text,
        "selector": element.selector,
        "visible": element.visible,
        "input_type": element.input_type,
        "placeholder": element.placeholder,
        "role": element.role,
        "aria_label": element.aria_label,
        "accessibility_name": element.accessibility_name,
        "state": {
            "value": value,
            "selected_text": state.get("selected_text"),
            "checked": state.get("checked"),
            "aria_checked": state.get("aria-checked"),
            "aria_expanded": state.get("aria-expanded"),
        },
    }
