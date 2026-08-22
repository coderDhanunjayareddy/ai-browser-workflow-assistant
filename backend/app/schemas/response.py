from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal, Optional

from app.intent_dispatcher.models import IntentDispatchDirective, IntentQueueResult


class SuggestedAction(BaseModel):
    """Compatibility DTO for UI/browser handoff.

    Runtime execution uses IntentDispatchDirective. This model remains as an
    open, intent-shaped facade for older policy/grounding/UI code while avoiding
    a closed browser action vocabulary.
    """

    action_id: str
    intent_id: Optional[str] = None
    mission_id: Optional[str] = None
    action_type: str
    target_selector: str
    value: Optional[str] = None
    description: str
    reasoning: str
    confidence: float
    safety_level: Literal['safe', 'caution', 'danger']
    # Sources that influenced this proposal. The browser-side enforcement gate
    # independently validates these labels before any privileged operation.
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    # Observation-time geometry for the final screenshot/coordinate fallback.
    # The policy digest binds this data to the approved action.
    grounding: dict[str, Any] = Field(default_factory=dict)
    # Generic content-insertion declaration preserved by the canonical action
    # contract. Provider, entity and file identities remain runtime data.
    content_insertion: Optional[dict[str, Any]] = None
    # Generic declaration for an irreversible external submission. The
    # destination and content identities are runtime values; providers are
    # adapters and are never encoded in this contract.
    consequential_submission: Optional[dict[str, Any]] = None


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


class IntentQueueDirective(BaseModel):
    """Execution Orchestrator-owned deterministic work for the active phase.

    This is a queue of runtime intents, not a separate browser action model.
    """
    schema_version: str = "intent_runtime.phase_queue.v1"
    active_phase: str
    should_replan: bool = False
    reason: str
    continuation_actions: list[IntentDispatchDirective] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

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
    # Backend-owned deterministic report artifacts are produced from validated
    # pipeline evidence, not a planner claim against only the current page.
    backend_authoritative_report: bool = False
    # Backend-owned planner intent routed by the runtime. Browser Control must
    # only receive suggested_actions; this directive never crosses that boundary
    # as an executable browser command.
    intent_dispatch: Optional[IntentDispatchDirective] = None
    # Structured evidence produced when a backend-owned intent is executed by
    # its registered owner.
    intent_execution: Optional[IntentQueueResult] = None
    # Execution Orchestrator phase work is ingested into the Mission Ledger
    # before browser handoff. It is not an extension-owned execution queue.
    execution_orchestrator: Optional[IntentQueueDirective] = None
    # Domain-independent capability contracts compiled at the final backend
    # boundary. During migration, violations are observable instead of allowing
    # an uncontracted action path to remain invisible.
    capability_contracts: list[dict[str, Any]] = Field(default_factory=list)
    capability_contract_violations: list[dict[str, str]] = Field(default_factory=list)
    # Typed, domain-independent handoff for browser work that only a person may
    # complete (authentication, MFA, CAPTCHA, privileged UI, or confirmation).
    human_intervention: Optional[dict[str, Any]] = None
