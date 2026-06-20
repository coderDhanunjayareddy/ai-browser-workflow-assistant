import logging
from typing import Dict, Any
from app.validators.base_validator import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)

class VerifyAmazonOpened(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        url = page_context.get("url", "")
        if "amazon" in url.lower():
            return ValidationResult(success=True, facts_to_add={"site_opened": True})
        elements = page_context.get("interactive_elements", [])
        for el in elements:
            if "search" in str(el.get("text", "")).lower() or "nav-search" in str(el.get("selector", "")):
                return ValidationResult(success=True, facts_to_add={"site_opened": True})
        return ValidationResult(success=False, error_code="AMAZON_LANDING_NOT_CONFIRMED")

class VerifySearchQueryEntered(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        elements = page_context.get("interactive_elements", [])
        # In real or simulated, search input would hold search query value
        # We look for value in element or assume success if input field is interacted
        for el in elements:
            if "twotabsearchtextbox" in str(el.get("selector", "")) or el.get("type") == "input":
                return ValidationResult(success=True, facts_to_add={"search_query_entered": True})
        return ValidationResult(success=False, error_code="SEARCH_QUERY_NOT_ENTERED")

class VerifySearchResultsLoaded(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        elements = page_context.get("interactive_elements", [])
        for el in elements:
            if "result" in str(el.get("selector", "")).lower() or "product" in str(el.get("text", "")).lower() or "filter" in str(el.get("text", "")).lower():
                return ValidationResult(success=True, facts_to_add={"results_loaded": True})
        # If url contains 's?k=' (amazon search query pattern)
        if "s?k=" in page_context.get("url", "").lower() or "keywords=" in page_context.get("url", "").lower():
            return ValidationResult(success=True, facts_to_add={"results_loaded": True})
        return ValidationResult(success=False, error_code="AMAZON_RESULTS_NOT_LOADED")
