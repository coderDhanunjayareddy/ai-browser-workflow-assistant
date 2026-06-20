import logging
import re
from typing import Dict, Any
from app.validators.base_validator import BaseValidator, ValidationResult

logger = logging.getLogger(__name__)


def _all_page_text(page_context: Dict[str, Any]) -> str:
    chunks = [
        str(page_context.get("title", "")),
        str(page_context.get("visible_text", "")),
    ]
    chunks.extend(str(h) for h in page_context.get("headings", []))
    chunks.extend(str(block.get("text", "")) for block in page_context.get("content_blocks", []))
    for el in page_context.get("interactive_elements", []):
        chunks.extend([
            str(el.get("text", "")),
            str(el.get("placeholder", "")),
            str(el.get("aria_label", "")),
            str(el.get("accessibility_name", "")),
        ])
    return " ".join(chunks).lower()


def _expected(page_context: Dict[str, Any], key: str) -> str:
    return str(page_context.get("_expected", {}).get(key, "")).strip().lower()


def _contains_expected(page_context: Dict[str, Any], key: str) -> bool:
    expected = _expected(page_context, key)
    if not expected:
        return False
    return expected in _all_page_text(page_context)

class VerifySiteOpened(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        elements = page_context.get("interactive_elements", [])
        for el in elements:
            if "search" in str(el.get("text", "")).lower() or "flight" in str(el.get("text", "")).lower():
                return ValidationResult(success=True, facts_to_add={"site_opened": True})
        return ValidationResult(success=False, error_code="SITE_LANDING_NOT_CONFIRMED")

class VerifyOriginSelected(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        expected_origin = _expected(page_context, "origin")
        if expected_origin:
            if _contains_expected(page_context, "origin"):
                return ValidationResult(success=True, facts_to_add={"origin_selected": True, "origin": expected_origin.title()})
            return ValidationResult(success=False, error_code="ORIGIN_VALUE_NOT_SELECTED")

        elements = page_context.get("interactive_elements", [])
        for el in elements:
            label = " ".join([str(el.get("text", "")), str(el.get("aria_label", "")), str(el.get("accessibility_name", ""))]).lower()
            if "from" in label and el.get("type") != "input":
                return ValidationResult(success=True, facts_to_add={"origin_selected": True})
        return ValidationResult(success=False, error_code="ORIGIN_NOT_SELECTED")

class VerifyDestinationSelected(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        expected_destination = _expected(page_context, "destination")
        if expected_destination:
            if _contains_expected(page_context, "destination"):
                return ValidationResult(success=True, facts_to_add={"destination_selected": True, "destination": expected_destination.title()})
            return ValidationResult(success=False, error_code="DESTINATION_VALUE_NOT_SELECTED")

        elements = page_context.get("interactive_elements", [])
        for el in elements:
            label = " ".join([str(el.get("text", "")), str(el.get("aria_label", "")), str(el.get("accessibility_name", ""))]).lower()
            if "to" in label and el.get("type") != "input":
                return ValidationResult(success=True, facts_to_add={"destination_selected": True})
        return ValidationResult(success=False, error_code="DESTINATION_NOT_SELECTED")

class VerifyDateSelected(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        expected_date = _expected(page_context, "date_text")
        if expected_date and _contains_expected(page_context, "date_text"):
            return ValidationResult(success=True, facts_to_add={"date_selected": True, "date_text": expected_date})

        elements = page_context.get("interactive_elements", [])
        for el in elements:
            label = " ".join([str(el.get("text", "")), str(el.get("aria_label", "")), str(el.get("accessibility_name", ""))]).lower()
            if "departure" in label or "date" in label or re.search(r"\b\d{1,2}\s+[a-z]{3,9}", label):
                return ValidationResult(success=True, facts_to_add={"date_selected": True})
        return ValidationResult(success=False, error_code="DATE_NOT_SELECTED")

class VerifySearchClicked(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        # After clicking search, url matches '/flight/search' or loading triggers
        url = page_context.get("url", "")
        if "search" in url.lower() and "flight" in url.lower():
            return ValidationResult(success=True, facts_to_add={"search_clicked": True})
        return ValidationResult(success=False, error_code="SEARCH_NOT_CLICKED")

class VerifyFlightsLoaded(BaseValidator):
    def validate(self, page_context: Dict[str, Any]) -> ValidationResult:
        text = _all_page_text(page_context)
        has_price = bool(re.search(r"(?:₹|rs\.?\s*)\s*\d[\d,]*", text, re.IGNORECASE))
        has_flight_signal = any(term in text for term in ["non stop", "non-stop", "direct", "airline", "departure", "arrival", "duration", "filter"])
        if has_price and has_flight_signal:
            prices = [int(p.replace(",", "")) for p in re.findall(r"(?:₹|rs\.?\s*)\s*(\d[\d,]*)", text, re.IGNORECASE)]
            facts = {"results_loaded": True}
            if prices:
                facts["price_limit"] = min(prices)
            if "direct" in text or "non stop" in text or "non-stop" in text:
                facts["direct_only"] = True
            return ValidationResult(success=True, facts_to_add=facts)
        return ValidationResult(success=False, error_code="FLIGHTS_LIST_NOT_LOADED")
