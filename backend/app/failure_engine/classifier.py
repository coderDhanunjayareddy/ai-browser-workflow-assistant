import logging
from typing import Optional

logger = logging.getLogger(__name__)

class FailureClassifier:
    """
    Component 8: Failure Classifier
    Classifies validation failures and DOM issues into standard error codes.
    """
    @staticmethod
    def classify_failure(execution_result: str, validator_error: Optional[str] = None, page_context: Optional[dict] = None) -> str:
        """
        Translates a raw failure description into a standard fault code.
        """
        if page_context:
            elements = page_context.get("interactive_elements", [])
            for el in elements:
                sel = str(el.get("selector", "")).lower()
                text = str(el.get("text", "")).lower()
                if "popup" in sel or "modal" in sel or "popup" in text or "modal" in text:
                    return "POPUP_BLOCKING"

        res_lower = execution_result.lower()
        
        # Check direct execution indicators
        if "not found" in res_lower or "selector" in res_lower:
            return "SELECTOR_STALE"
        if "timeout" in res_lower or "wait" in res_lower:
            return "RESULTS_NOT_LOADED"
            
        # Check validation indicators
        if validator_error:
            val_lower = validator_error.lower()
            if "chats" in val_lower or "landing" in val_lower:
                return "RESULTS_NOT_LOADED"
            if "close" in val_lower or "modal" in val_lower:
                return "POPUP_BLOCKING"
            return f"VALIDATION_MISMATCH_{validator_error.upper()}"
            
        return "UNKNOWN_FAILURE"
