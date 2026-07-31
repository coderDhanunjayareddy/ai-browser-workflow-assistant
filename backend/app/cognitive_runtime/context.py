from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CognitiveExecutionContext:
    """Read-only aggregate of mission subsystems for future Cognitive Runtime waves."""

    mission_id: str
    mission_blueprint: Any | None = None
    mission_ledger: Any | None = None
    mission_completion: Any | None = None
    knowledge_extraction: Any | None = None
    runtime_state: Any | None = None
    browser_intelligence: Any | None = None
    semantic_kernel: Any | None = None
    validation: Any | None = None

    def available_sources(self) -> list[str]:
        return [
            name
            for name, value in {
                "mission_blueprint": self.mission_blueprint,
                "mission_ledger": self.mission_ledger,
                "mission_completion": self.mission_completion,
                "knowledge_extraction": self.knowledge_extraction,
                "runtime_state": self.runtime_state,
                "browser_intelligence": self.browser_intelligence,
                "semantic_kernel": self.semantic_kernel,
                "validation": self.validation,
            }.items()
            if value is not None
        ]
