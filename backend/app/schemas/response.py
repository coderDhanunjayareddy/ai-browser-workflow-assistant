from pydantic import BaseModel
from typing import Literal, Optional


class SuggestedAction(BaseModel):
    action_id: str
    action_type: Literal[
        'click',
        'fill',
        'scroll',
        'navigate',
        'wait',
        'select_option',
        'choose_date',
        'hover',
        'keyboard_shortcut',
        'open_new_tab',
        'switch_tab',
        'close_tab',
        'focus_existing_tab',
    ]
    target_selector: str
    value: Optional[str] = None
    description: str
    reasoning: str
    confidence: float
    safety_level: Literal['safe', 'caution', 'danger']


class ReportOutcome(BaseModel):
    """Planner Contract V2: a claim that the goal (or active sub-goal) is already
    satisfied from what is currently known — never self-certifying. The orchestrator
    verifies this against real success criteria before treating it as completion."""
    answer: Optional[str] = None
    claim: str


class ReplanOutcome(BaseModel):
    """Planner Contract V2: the planner's own real-time judgment that the current
    approach needs to change, distinct from Reflection's after-the-fact veto."""
    reason: str


class AnalyzeResponse(BaseModel):
    session_id: str
    analysis: str
    # Planner Contract V2: which kind of turn this is. Defaults to 'act' so every
    # existing caller/construction site (which never sets this) is unaffected.
    outcome_kind: Literal['act', 'report', 'wait', 'ask', 'replan'] = 'act'
    suggested_actions: list[SuggestedAction]
    clarification_question: Optional[str] = None
    report: Optional[ReportOutcome] = None
    replan: Optional[ReplanOutcome] = None
    # Production SGV Phase 1: set by WorkflowOrchestrator after validating a
    # report claim against live page evidence.  False by default so every existing
    # caller is unaffected.  outcome_kind is never changed by SGV.
    sgv_verified: bool = False
    # Production Goal Convergence GC-1: passive semantic stagnation signal.
    # This never changes planner intent, actions, prompts, or recovery behavior.
    goal_convergence: bool = False
