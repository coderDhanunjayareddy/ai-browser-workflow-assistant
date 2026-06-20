import logging
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.db import WorkflowState

logger = logging.getLogger(__name__)

class StatePersistence:
    """
    Component 1: State Engine Persistence Layer
    Handles CRUD operations for verified session facts in PostgreSQL.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_state(self, session_id: str) -> Optional[WorkflowState]:
        """
        Loads the state row from the database.
        """
        return self.db.query(WorkflowState).filter(WorkflowState.session_id == session_id).first()

    def create_state(self, session_id: str, initial_facts: Optional[Dict[str, Any]] = None) -> WorkflowState:
        """
        Creates a new state entry for the session.
        """
        facts = initial_facts or {}
        db_state = WorkflowState(
            session_id=session_id,
            facts=facts,
            updated_at=datetime.utcnow()
        )
        self.db.add(db_state)
        self.db.commit()
        self.db.refresh(db_state)
        logger.info(f"Initialized verified state facts for session {session_id}")
        return db_state

    def save_facts(self, session_id: str, facts: Dict[str, Any]) -> WorkflowState:
        """
        Updates and persists state facts.
        """
        db_state = self.get_state(session_id)
        if not db_state:
            db_state = self.create_state(session_id, facts)
        else:
            # Merge facts
            merged_facts = dict(db_state.facts or {})
            merged_facts.update(facts)
            db_state.facts = merged_facts
            db_state.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(db_state)
            
        logger.info(f"Updated verified facts for session {session_id}: {db_state.facts}")
        return db_state
