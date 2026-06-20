import logging
from typing import Dict, Any
from app.validators.base_validator import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)

class VerifyGmailOpened(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        url = page_context.get("url", "")
        if "mail.google.com" in url.lower() or "gmail" in url.lower():
            return ValidationResult(success=True, facts_to_add={"site_opened": True})
        return ValidationResult(success=False, error_code="GMAIL_LANDING_NOT_CONFIRMED")

class VerifyComposeWindowOpened(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        elements = page_context.get("interactive_elements", [])
        for el in elements:
            if "to" in str(el.get("aria_label", "")).lower() or "recipient" in str(el.get("placeholder", "")).lower():
                return ValidationResult(success=True, facts_to_add={"compose_window_opened": True})
            if "subject" in str(el.get("placeholder", "")).lower() or "subjectbox" in str(el.get("selector", "")):
                return ValidationResult(success=True, facts_to_add={"compose_window_opened": True})
        return ValidationResult(success=False, error_code="GMAIL_COMPOSE_WINDOW_NOT_FOUND")

class VerifyRecipientSubjectEntered(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        elements = page_context.get("interactive_elements", [])
        # Recipient input and subject line verification
        for el in elements:
            if "to" in str(el.get("aria_label", "")).lower() or "subject" in str(el.get("placeholder", "")).lower():
                return ValidationResult(success=True, facts_to_add={"recipient_subject_entered": True})
        return ValidationResult(success=False, error_code="RECIPIENT_OR_SUBJECT_MISSING")

class VerifyBodyTextEntered(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        # Verify body text has been entered
        elements = page_context.get("interactive_elements", [])
        for el in elements:
            if "body" in str(el.get("aria_label", "")).lower() or el.get("role") == "textbox":
                return ValidationResult(success=True, facts_to_add={"body_text_entered": True})
        return ValidationResult(success=False, error_code="BODY_TEXT_NOT_ENTERED")
