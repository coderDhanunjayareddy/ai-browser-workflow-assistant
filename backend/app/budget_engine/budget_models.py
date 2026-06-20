from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class BudgetCheckpoint(str, Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    RECOVERY = "recovery"


class WorkflowBudget(BaseModel):
    max_steps: int = Field(default=50, gt=0)
    max_tokens: int = Field(default=50_000, gt=0)
    max_retries: int = Field(default=5, ge=0)
    max_duration_seconds: int = Field(default=300, gt=0)
    steps_used: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)
    retries_used: int = Field(default=0, ge=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def elapsed_seconds(self) -> float:
        started = self.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())

    def exhausted_reason(self) -> str | None:
        if self.steps_used >= self.max_steps:
            return "maximum workflow steps reached"
        if self.tokens_used >= self.max_tokens:
            return "maximum planner tokens reached"
        if self.retries_used >= self.max_retries:
            return "maximum retries reached"
        if self.elapsed_seconds >= self.max_duration_seconds:
            return "maximum workflow duration reached"
        return None


class BudgetExceededError(RuntimeError):
    def __init__(self, reason: str, budget: WorkflowBudget):
        self.reason = reason
        self.budget = budget
        super().__init__(reason)
