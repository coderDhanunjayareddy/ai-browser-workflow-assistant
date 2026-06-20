from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ValidationResult:
    """
    Result returned by any step validator.
    """
    def __init__(self, success: bool, error_code: Optional[str] = None, facts_to_add: Optional[Dict[str, Any]] = None):
        self.success = success
        self.error_code = error_code
        self.facts_to_add = facts_to_add or {}

class BaseValidator(ABC):
    """
    Component 3: Base Validator
    All step outcome checkers must inherit from this class.
    """
    @abstractmethod
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        """
        Takes page DOM/A11y/screenshot data and determines if the active step succeeded.
        """
        pass
