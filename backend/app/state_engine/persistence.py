import logging
from datetime import datetime
from typing import Any, Dict, Optional
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

    def bootstrap_from_handoff(
        self, session_id: str, handoff_payload: Any
    ) -> Optional[WorkflowState]:
        """
        V3.0: Pre-populate WorkflowState.facts from a WorkflowHandoffPayload.
        Only applies when state does not yet have any facts (cold start).

        Accepts Any type to avoid circular imports; callers pass
        app.schemas.assist.WorkflowHandoffPayload.
        """
        if handoff_payload is None:
            return None
        existing = self.get_state(session_id)
        if existing and existing.facts:
            return existing  # already have facts — don't overwrite

        from app.cognitive_core.workflow_context import build_bootstrap_facts
        bootstrap = build_bootstrap_facts(handoff_payload)
        if not bootstrap:
            return existing

        logger.info(
            "Bootstrapping workflow state for session %s with %d facts from handoff",
            session_id, len(bootstrap),
        )
        return self.save_facts(session_id, bootstrap)

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
