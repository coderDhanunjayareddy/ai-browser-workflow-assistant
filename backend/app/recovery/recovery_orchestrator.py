import logging
from typing import Dict, Any, Optional
from app.failure_engine.classifier import FailureClassifier
from app.failure_engine.remedy_db import RemedyDatabase

logger = logging.getLogger(__name__)

class RecoveryOrchestrator:
    """
    Component 11: Auto Recovery Engine
    Coordinates retries, popup closures, page refreshes, and user escalations.
    """
    def __init__(self, session_id: str, max_retries: int = 3, db=None):
        self.session_id = session_id
        self.max_retries = max_retries
        self.db = db

    def generate_recovery_action(self, error_code: str, retry_count: int) -> Dict[str, Any]:
        """
        Calculates recovery actions based on failure codes and retry attempts.
        """
        logger.info(f"Generating recovery action for {error_code} (attempt {retry_count}/{self.max_retries})")
        if self.db is not None:
            from app.budget_engine import BudgetManager
            manager = BudgetManager(self.db, self.session_id)
            manager.enforce()
            manager.consume(retries=1)
        
        if retry_count >= self.max_retries:
            logger.error("Max recovery attempts reached. Escolating to User Intervention.")
            return {
                "action_type": "user_intervention",
                "message": f"Automation failed: {error_code}. Please complete this step manually."
            }

        # Query remedy database
        remedy = RemedyDatabase.get_remedy(error_code)
        
        return {
            "action_type": remedy.get("action", "wait"),
            "target_selector": remedy.get("selector") or "",
            "value": remedy.get("value"),
            "description": remedy.get("description", "Retrying step...")
        }

    def explore_after_recovery_failure(
        self, failed_action: Dict[str, Any], relevant_elements: list[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Invoke bounded exploration only after the normal recovery path fails."""
        from app.exploration import ExplorationPlanner
        return ExplorationPlanner().explore(failed_action, relevant_elements)
