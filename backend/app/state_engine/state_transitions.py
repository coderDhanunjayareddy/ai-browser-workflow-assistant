import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StateFSMError(ValueError):
    """Raised when an invalid state transition is attempted."""
    pass

class StateFSM:
    """
    Component 1: State transitions manager (FSM rules).
    Verifies that state updates match expected sequencing.
    """
    @staticmethod
    def validate_transition(current_state: Dict[str, Any], updates: Dict[str, Any]) -> None:
        """
        Validates state updates against hardcoded transition rules.
        """
        # Rule: results_loaded requires search_clicked to be True
        if updates.get("results_loaded") and not (current_state.get("search_clicked") or updates.get("search_clicked")):
            raise StateFSMError("FSM Violation: results_loaded cannot be True unless search_clicked is True")

        # Rule: message_sent requires message_composed or chat_opened to be True
        if updates.get("message_sent") and not (current_state.get("chat_opened") or updates.get("chat_opened")):
            raise StateFSMError("FSM Violation: message_sent cannot be True unless chat_opened is True")

        logger.info("State transition validated successfully.")
