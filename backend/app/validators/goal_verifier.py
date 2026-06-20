import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class GoalVerificationResult:
    def __init__(self, success: bool, missing_constraints: List[str] = None):
        self.success = success
        self.missing_constraints = missing_constraints or []

class GoalVerifier:
    """
    Component 3.5: Goal Verification Engine
    Verifies overall high-level goals and constraints before finishing a workflow.
    """
    @staticmethod
    def verify_goal(verified_facts: Dict[str, Any], constraints: Dict[str, Any]) -> GoalVerificationResult:
        """
        Compares final accumulated facts against the task's user-specified constraints.
        Example constraints:
            {"origin": "Hyderabad", "destination": "Goa", "direct_only": True, "price_limit": 5000}
        """
        logger.info(f"Running goal verification against constraints: {constraints}")
        missing = []

        for key, expected_val in constraints.items():
            actual_val = verified_facts.get(key)
            
            # Simple check logic (can be expanded for ranges or semantic equality)
            if actual_val is None:
                missing.append(f"Constraint '{key}' was not found in verified facts.")
                continue

            if key == "price_limit":
                if float(actual_val) > float(expected_val):
                    missing.append(f"Price constraint violated: actual {actual_val} is above limit {expected_val}")
            else:
                if str(actual_val).lower() != str(expected_val).lower():
                    missing.append(f"Constraint '{key}' mismatch: expected '{expected_val}', got '{actual_val}'")

        if missing:
            logger.warning(f"Goal verification failed: {missing}")
            return GoalVerificationResult(success=False, missing_constraints=missing)
            
        logger.info("Goal verification passed successfully.")
        return GoalVerificationResult(success=True)
