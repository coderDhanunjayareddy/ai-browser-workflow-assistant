from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


LoopKind = Literal["none", "repeat_action", "oscillation", "repeated_url", "no_progress"]


@dataclass(frozen=True)
class Checkpoint:
    id: str
    description: str
    status: Literal["pending", "completed", "blocked", "failed"] = "pending"
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionProgress:
    original_mission: str
    current_objective: str
    completed_subtasks: list[str]
    remaining_subtasks: list[str]
    blocked_objectives: list[str]
    failed_objectives: list[str]
    retry_counts: dict[str, int]
    progress_percent: int
    checkpoints: list[Checkpoint] = field(default_factory=list)

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "current_objective": self.current_objective,
            "progress_percent": self.progress_percent,
            "completed": self.completed_subtasks[-6:],
            "remaining": self.remaining_subtasks[:6],
            "blocked": self.blocked_objectives[-4:],
            "failed": self.failed_objectives[-4:],
            "retry_counts": dict(list(self.retry_counts.items())[-6:]),
            "checkpoints": [checkpoint.to_dict() for checkpoint in self.checkpoints[:10]],
        }


@dataclass(frozen=True)
class ActionRecord:
    index: int
    action_type: str
    target: str
    value: str | None
    url: str | None
    selector_id: str | None
    semantic_target: str | None
    timestamp_ms: int
    result: str
    verification_result: str | None
    signature: str

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "i": self.index,
            "type": self.action_type,
            "target": self.target[:120],
            "value": (self.value or "")[:160] or None,
            "url": self.url,
            "result": self.result[:120],
            "verification": self.verification_result,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class BrowserTabSnapshot:
    tab_id: str
    url: str
    title: str
    purpose: str
    active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BrowserStateSnapshot:
    active_tab: BrowserTabSnapshot
    tabs: list[BrowserTabSnapshot]
    current_url: str
    previous_url: str | None
    navigation_history: list[str]
    visited_pages: list[str]
    extracted_entities: list[dict[str, str]]

    def to_compact_dict(self) -> dict[str, Any]:
        return {
            "current_url": self.current_url,
            "previous_url": self.previous_url,
            "active_tab": self.active_tab.to_dict(),
            "open_tabs": [tab.to_dict() for tab in self.tabs[:12]],
            "visited_urls": self.visited_pages[-12:],
            "navigation_history": self.navigation_history[-8:],
            "extracted_entities": self.extracted_entities[-8:],
        }


@dataclass(frozen=True)
class LoopSignal:
    kind: LoopKind
    confidence: float
    reason: str
    repeated_signature: str | None = None

    @property
    def detected(self) -> bool:
        return self.kind != "none"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProgressValidation:
    progress_increased: bool
    no_progress_count: int
    loop_signal: LoopSignal
    recommendation: Literal["continue", "retry", "recover", "replan"]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["loop_signal"] = self.loop_signal.to_dict()
        return data


@dataclass(frozen=True)
class ContinuityTelemetry:
    build_latency_ms: int
    action_count: int
    unique_action_count: int
    visited_url_count: int
    loop_detected: bool
    progress_percent: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayFrame:
    frame_id: str
    action_signature: str
    url: str | None
    result: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContinuitySnapshot:
    schema_version: str
    session_id: str
    mission: MissionProgress
    browser_state: BrowserStateSnapshot
    recent_actions: list[ActionRecord]
    progress_validation: ProgressValidation
    telemetry: ContinuityTelemetry
    replay_frames: list[ReplayFrame]

    def to_compact_context(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mission_progress": self.mission.to_compact_dict(),
            "browser_state": self.browser_state.to_compact_dict(),
            "recent_action_history": [record.to_compact_dict() for record in self.recent_actions[-8:]],
            "progress_validation": self.progress_validation.to_dict(),
            "replay": [frame.to_dict() for frame in self.replay_frames[-6:]],
        }
