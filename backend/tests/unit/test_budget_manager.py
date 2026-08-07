from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.budget_engine.budget_manager import BudgetManager
from app.core.database import Base


def test_budget_manager_uses_configured_workflow_limits(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr("app.budget_engine.budget_manager.settings.workflow_max_steps", 91)
    monkeypatch.setattr("app.budget_engine.budget_manager.settings.workflow_max_tokens", 222_000)
    monkeypatch.setattr("app.budget_engine.budget_manager.settings.workflow_max_retries", 11)
    monkeypatch.setattr("app.budget_engine.budget_manager.settings.workflow_max_duration_seconds", 1200)

    with SessionLocal() as db:
        budget = BudgetManager(db, "configured-budget-session").snapshot()

    assert budget.max_steps == 91
    assert budget.max_tokens == 222_000
    assert budget.max_retries == 11
    assert budget.max_duration_seconds == 1200

    Base.metadata.drop_all(bind=engine)
