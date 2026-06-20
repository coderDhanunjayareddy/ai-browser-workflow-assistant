from contextlib import contextmanager
from typing import Iterator

from app.budget_engine.budget_manager import BudgetManager
from app.budget_engine.budget_models import BudgetCheckpoint, WorkflowBudget


@contextmanager
def enforce_budget(manager: BudgetManager, checkpoint: BudgetCheckpoint) -> Iterator[WorkflowBudget]:
    """Reusable guard for planning, execution, and recovery boundaries."""
    budget = manager.enforce()
    yield budget
    if checkpoint == BudgetCheckpoint.EXECUTION:
        manager.consume(steps=1)
    elif checkpoint == BudgetCheckpoint.RECOVERY:
        manager.consume(retries=1)
