from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SemanticActionType = Literal[
    "SEARCH_WEB",
    "COLLECT_RESULTS",
    "OPEN_ENTITY",
    "FOCUS_TAB",
    "READ_PAGE",
    "EXTRACT_FIELDS",
    "FILL_FORM",
    "UPLOAD_FILE",
    "DOWNLOAD_FILE",
    "CLICK_ENTITY",
    "WAIT_FOR_STATE",
    "MARK_COMPLETE",
    "SKIP_ENTITY",
]


@dataclass(frozen=True)
class MissionGoal:
    id: str
    description: str
    status: Literal["pending", "running", "completed", "failed", "blocked", "skipped"] = "pending"
    evidence: list[str] = field(default_factory=list)
    retries: int = 0
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionState:
    mission: str
    goals: list[MissionGoal]
    current_goal_id: str | None
    blocked: bool = False
    failure_reason: str | None = None

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "current_goal_id": self.current_goal_id,
            "blocked": self.blocked,
            "failure_reason": self.failure_reason,
            "goals": [goal.to_dict() for goal in self.goals[:12]],
        }


@dataclass(frozen=True)
class BrowserBinding:
    selector: str | None = None
    selector_id: str | None = None
    href: str | None = None
    tab_id: str | None = None
    frame_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticEntity:
    id: str
    semantic_type: str
    title: str
    url: str | None
    confidence: float
    source_page: str
    metadata: dict[str, str]
    browser_bindings: BrowserBinding
    lifecycle_status: Literal["discovered", "opened", "read", "completed", "failed", "skipped"] = "discovered"

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.semantic_type,
            "title": self.title[:140],
            "url": self.url,
            "confidence": self.confidence,
            "source_page": self.source_page,
            "bindings": self.browser_bindings.to_dict(),
            "status": self.lifecycle_status,
        }


@dataclass(frozen=True)
class BrowserContext:
    focused_tab_id: str
    tabs: list[dict[str, str]]
    current_url: str
    navigation_history: list[str]
    redirects: list[dict[str, str]]
    page_purpose: str

    def to_compact_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticActionDefinition:
    action_type: SemanticActionType
    required_state: list[str]
    required_entities: list[str]
    validation_rules: list[str]
    retry_policy: dict[str, int]
    success_evidence: list[str]
    failure_transitions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SemanticActionProposal:
    action_type: SemanticActionType
    entity_id: str | None
    parameters: dict[str, str]
    source_action_type: str
    source_description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reason: str
    failures: list[str]
    retry_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GroundingResult:
    grounded: bool
    action_type: str | None
    target_selector: str | None
    value: str | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgressLedgerEntry:
    semantic_action: str
    entity_id: str | None
    status: Literal["pending", "running", "completed", "failed", "blocked", "skipped"]
    evidence: list[str]
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RecoveryDecision:
    strategy: Literal["none", "resolve_entity_again", "fallback_capability", "url_navigation", "refresh", "reextract_entities", "skip_entity", "escalate"]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KernelSnapshot:
    schema_version: str
    session_id: str
    mission_state: MissionState
    entities: list[SemanticEntity]
    browser_context: BrowserContext
    legal_actions: list[SemanticActionDefinition]
    proposal: SemanticActionProposal | None
    eligibility: EligibilityResult | None
    grounding: GroundingResult | None
    ledger: list[ProgressLedgerEntry]
    loop_prevention: dict[str, Any]
    recovery: RecoveryDecision
    telemetry: dict[str, Any]
    replay: list[dict[str, Any]]

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mission_state": self.mission_state.to_compact_dict(),
            "entities": [entity.to_compact_dict() for entity in self.entities[:20]],
            "browser_context": self.browser_context.to_compact_dict(),
            "legal_semantic_actions": [action.to_dict() for action in self.legal_actions],
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "eligibility": self.eligibility.to_dict() if self.eligibility else None,
            "grounding": self.grounding.to_dict() if self.grounding else None,
            "progress_ledger": [entry.to_dict() for entry in self.ledger[-12:]],
            "loop_prevention": self.loop_prevention,
            "recovery": self.recovery.to_dict(),
        }
