import logging
from typing import Dict, Any
from app.validators.base_validator import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)

class VerifyChatsLoaded(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        # WhatsApp contact panels usually have search bars or chat list role items
        elements = page_context.get("interactive_elements", [])
        for el in elements:
            if "search" in str(el.get("aria_label", "")).lower() or el.get("role") == "listitem":
                return ValidationResult(success=True, facts_to_add={"chats_loaded": True})
        return ValidationResult(success=False, error_code="CHATS_LIST_NOT_FOUND")

class VerifyChatOpened(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        elements = page_context.get("interactive_elements", [])
        # Active chat panels show the contact name at the top heading
        for el in elements:
            if el.get("role") == "heading" or "chat details" in str(el.get("aria_label", "")).lower():
                return ValidationResult(success=True, facts_to_add={"chat_opened": True})
        return ValidationResult(success=False, error_code="CHAT_HEADER_NOT_FOUND")

class VerifyMessageComposed(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        elements = page_context.get("interactive_elements", [])
        for el in elements:
            if "type a message" in str(el.get("placeholder", "")).lower() or el.get("role") == "textbox":
                # Textbox exists
                return ValidationResult(success=True, facts_to_add={"message_composed": True})
        return ValidationResult(success=False, error_code="MESSAGE_TEXTBOX_NOT_FOUND")

class VerifyMessageSent(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        # If the input text is cleared and send button is invisible, message was sent
        elements = page_context.get("interactive_elements", [])
        send_btn_visible = False
        for el in elements:
            if "send" in str(el.get("aria_label", "")).lower():
                send_btn_visible = True
                break
        if not send_btn_visible:
            return ValidationResult(success=True, facts_to_add={"message_sent": True})
        return ValidationResult(success=False, error_code="SEND_BUTTON_STILL_VISIBLE")
