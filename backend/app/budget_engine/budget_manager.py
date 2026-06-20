from datetime import datetime

from sqlalchemy.orm import Session

from app.budget_engine.budget_models import BudgetExceededError, WorkflowBudget
from app.models.db import WorkflowBudgetRecord, WorkflowSession


class BudgetManager:
    """Persistent, atomic-enough budget accounting for a workflow session."""

    def __init__(self, db: Session, session_id: str):
        self.db = db
        self.session_id = session_id

    def get_or_create(self) -> WorkflowBudgetRecord:
        record = self.db.get(WorkflowBudgetRecord, self.session_id)
        if record is None:
            record = WorkflowBudgetRecord(session_id=self.session_id)
            self.db.add(record)
            self.db.flush()
        return record

    def snapshot(self) -> WorkflowBudget:
        row = self.get_or_create()
        return WorkflowBudget.model_validate({
            key: getattr(row, key) for key in WorkflowBudget.model_fields
        })

    def enforce(self) -> WorkflowBudget:
        budget = self.snapshot()
        reason = budget.exhausted_reason()
        if reason:
            session = self.db.get(WorkflowSession, self.session_id)
            if session:
                session.status = "BUDGET_EXCEEDED"
            self.db.commit()
            raise BudgetExceededError(reason, budget)
        return budget

    def consume(self, *, steps: int = 0, tokens: int = 0, retries: int = 0) -> WorkflowBudget:
        row = self.get_or_create()
        row.steps_used += max(0, steps)
        row.tokens_used += max(0, tokens)
        row.retries_used += max(0, retries)
        row.updated_at = datetime.utcnow()
        self.db.commit()
        return self.enforce()
