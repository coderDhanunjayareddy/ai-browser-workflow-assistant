from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


SemanticKind = Literal[
    "input",
    "button",
    "link",
    "form",
    "dialog",
    "menu",
    "card",
    "table",
    "tab",
    "navigation",
    "pagination",
    "list",
    "widget",
    "search_result",
    "advertisement",
    "media",
    "ai_panel",
    "text",
    "unknown",
]

PageType = Literal[
    "search_engine",
    "documentation",
    "blog",
    "dashboard",
    "settings",
    "login",
    "signup",
    "checkout",
    "jobs",
    "spreadsheet",
    "email",
    "editor",
    "pdf",
    "canvas",
    "map",
    "media",
    "unknown",
]


@dataclass(frozen=True)
class SelectorCandidate:
    selector_id: str
    selector: str
    strategy: str
    confidence: float
    valid: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector_id": self.selector_id,
            "selector": self.selector,
            "strategy": self.strategy,
            "confidence": self.confidence,
            "valid": self.valid,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SemanticElement:
    element_id: str
    kind: SemanticKind
    label: str
    selector_id: str | None
    selector: str | None
    role: str | None = None
    href: str | None = None
    visible: bool = True
    confidence: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "element_id": self.element_id,
            "kind": self.kind,
            "label": self.label,
            "selector_id": self.selector_id,
            "selector": self.selector,
            "role": self.role,
            "href": self.href,
            "visible": self.visible,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class SearchResult:
    rank: int
    title: str
    description: str
    url: str
    displayed_url: str
    open_selector: str | None
    selector_id: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "displayed_url": self.displayed_url,
            "open_selector": self.open_selector,
            "selector_id": self.selector_id,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class PageClassification:
    page_type: PageType
    confidence: float
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_type": self.page_type,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class BrowserStateModel:
    current_url: str
    title: str
    page_type: str
    open_tabs: list[dict[str, Any]] = field(default_factory=list)
    active_tab: dict[str, Any] | None = None
    navigation_history: list[str] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    dialogs: list[dict[str, Any]] = field(default_factory=list)
    downloads: list[dict[str, Any]] = field(default_factory=list)
    uploads: list[dict[str, Any]] = field(default_factory=list)
    authentication_state: str = "unknown"
    scroll_state: dict[str, Any] = field(default_factory=dict)
    focused_element: str | None = None
    pending_actions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_url": self.current_url,
            "title": self.title,
            "page_type": self.page_type,
            "open_tabs": self.open_tabs,
            "active_tab": self.active_tab,
            "navigation_history": self.navigation_history,
            "frames": self.frames,
            "dialogs": self.dialogs,
            "downloads": self.downloads,
            "uploads": self.uploads,
            "authentication_state": self.authentication_state,
            "scroll_state": self.scroll_state,
            "focused_element": self.focused_element,
            "pending_actions": self.pending_actions,
        }


@dataclass(frozen=True)
class SemanticPageModel:
    schema_version: str
    url: str
    title: str
    classification: PageClassification
    adapter: str
    elements: list[SemanticElement]
    search_results: list[SearchResult] = field(default_factory=list)
    selector_candidates: list[SelectorCandidate] = field(default_factory=list)
    telemetry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "url": self.url,
            "title": self.title,
            "classification": self.classification.to_dict(),
            "adapter": self.adapter,
            "elements": [element.to_dict() for element in self.elements],
            "search_results": [result.to_dict() for result in self.search_results],
            "selector_candidates": [candidate.to_dict() for candidate in self.selector_candidates],
            "telemetry": self.telemetry,
        }


@dataclass(frozen=True)
class ActionExpectation:
    action_type: str
    expected: dict[str, Any]
    safety_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "expected": self.expected,
            "safety_notes": list(self.safety_notes),
        }


@dataclass(frozen=True)
class VerificationOutcome:
    action_type: str
    verified: bool
    checks: list[dict[str, Any]]
    latency_ms: int
    false_success_prevented: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "verified": self.verified,
            "checks": self.checks,
            "latency_ms": self.latency_ms,
            "false_success_prevented": self.false_success_prevented,
        }


@dataclass(frozen=True)
class DomMutationSignal:
    mutation_id: str
    mutation_type: str
    target_hint: str
    impact_score: float
    requires_refresh: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "mutation_type": self.mutation_type,
            "target_hint": self.target_hint,
            "impact_score": self.impact_score,
            "requires_refresh": self.requires_refresh,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class SemanticWaitPlan:
    wait_type: str
    ready: bool
    reason: str
    recommended_poll_ms: int
    timeout_ms: int
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "wait_type": self.wait_type,
            "ready": self.ready,
            "reason": self.reason,
            "recommended_poll_ms": self.recommended_poll_ms,
            "timeout_ms": self.timeout_ms,
            "signals": self.signals,
        }


@dataclass(frozen=True)
class BrowserMemorySnapshot:
    previous_pages: list[dict[str, Any]]
    navigation_chain: list[str]
    redirects: list[dict[str, str]]
    login_transitions: list[dict[str, str]]
    workflow_checkpoints: list[dict[str, Any]]
    recently_interacted_elements: list[dict[str, Any]]
    recent_search_results: list[dict[str, Any]]
    recently_opened_tabs: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "previous_pages": self.previous_pages,
            "navigation_chain": self.navigation_chain,
            "redirects": self.redirects,
            "login_transitions": self.login_transitions,
            "workflow_checkpoints": self.workflow_checkpoints,
            "recently_interacted_elements": self.recently_interacted_elements,
            "recent_search_results": self.recent_search_results,
            "recently_opened_tabs": self.recently_opened_tabs,
        }


@dataclass(frozen=True)
class RecoveryDecision:
    recovered: bool
    strategy: str
    selector: str | None
    selector_id: str | None
    confidence: float
    attempts: list[dict[str, Any]]
    replay_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovered": self.recovered,
            "strategy": self.strategy,
            "selector": self.selector,
            "selector_id": self.selector_id,
            "confidence": self.confidence,
            "attempts": self.attempts,
            "replay_metadata": self.replay_metadata,
        }


@dataclass(frozen=True)
class VisualGroundingTarget:
    target_id: str
    source: str
    label: str
    selector_id: str | None
    selector: str | None
    confidence: float
    region: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "source": self.source,
            "label": self.label,
            "selector_id": self.selector_id,
            "selector": self.selector,
            "confidence": self.confidence,
            "region": self.region,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class BrowserHealthSnapshot:
    health_score: float
    stale_model: bool
    repeated_failures: int
    selector_instability: float
    excessive_retries: bool
    infinite_loop_risk: bool
    navigation_failures: int
    responsive: bool
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": self.health_score,
            "stale_model": self.stale_model,
            "repeated_failures": self.repeated_failures,
            "selector_instability": self.selector_instability,
            "excessive_retries": self.excessive_retries,
            "infinite_loop_risk": self.infinite_loop_risk,
            "navigation_failures": self.navigation_failures,
            "responsive": self.responsive,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class BrowserIntelligenceArtifact:
    page_model: SemanticPageModel
    browser_state: BrowserStateModel
    replay: dict[str, Any]
    capability_report: dict[str, Any]
    mutation_signals: list[DomMutationSignal] = field(default_factory=list)
    wait_plan: SemanticWaitPlan | None = None
    memory: BrowserMemorySnapshot | None = None
    recovery: RecoveryDecision | None = None
    visual_targets: list[VisualGroundingTarget] = field(default_factory=list)
    health: BrowserHealthSnapshot | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_model": self.page_model.to_dict(),
            "browser_state": self.browser_state.to_dict(),
            "replay": self.replay,
            "capability_report": self.capability_report,
            "mutation_signals": [signal.to_dict() for signal in self.mutation_signals],
            "wait_plan": self.wait_plan.to_dict() if self.wait_plan else None,
            "memory": self.memory.to_dict() if self.memory else None,
            "recovery": self.recovery.to_dict() if self.recovery else None,
            "visual_targets": [target.to_dict() for target in self.visual_targets],
            "health": self.health.to_dict() if self.health else None,
        }
