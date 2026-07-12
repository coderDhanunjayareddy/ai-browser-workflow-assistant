"""Goal Convergence Engine.

Pure strategy-progress detection for the M0 loop. It consumes evidence the loop
already has and recommends an existing Planner Contract V2 replan when attempts
repeat without semantic progress.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConvergenceEvidence:
    outcome_kind: str
    strategy_key: str
    semantic_signature: str
    validation_signature: str
    verified: bool = False


@dataclass(frozen=True)
class ConvergenceDecision:
    should_replan: bool
    reason: str = ""


class GoalConvergenceEngine:
    """Detects repeated non-progress without planning or validating itself."""

    def __init__(self, *, repeated_attempt_threshold: int = 2) -> None:
        self.repeated_attempt_threshold = repeated_attempt_threshold
        self._last_progress_key: tuple[str, str] | None = None
        self._streak = 0

    def assess(self, evidence: ConvergenceEvidence) -> ConvergenceDecision:
        if evidence.verified:
            self.reset()
            return ConvergenceDecision(False)

        progress_key = (
            evidence.semantic_signature,
            evidence.validation_signature,
        )
        if progress_key == self._last_progress_key:
            self._streak += 1
        else:
            self._last_progress_key = progress_key
            self._streak = 1

        if self._streak >= self.repeated_attempt_threshold:
            return ConvergenceDecision(
                True,
                (
                    f"goal convergence stalled after {self._streak} repeated "
                    f"{evidence.outcome_kind} attempts with unchanged semantic "
                    "evidence and validation result"
                ),
            )
        return ConvergenceDecision(False)

    def reset(self) -> None:
        self._last_progress_key = None
        self._streak = 0
