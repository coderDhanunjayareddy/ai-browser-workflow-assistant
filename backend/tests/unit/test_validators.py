import pytest
from app.validators.mmt_validators import VerifyFlightsLoaded
from app.validators.whatsapp_validators import VerifyChatOpened

def test_mmt_flights_loaded_validator():
    validator = VerifyFlightsLoaded()
    
    # Failure case: no elements match
    fail_context = {"interactive_elements": [{"text": "Login", "selector": "#login"}]}
    res = validator.validate(fail_context)
    assert res.success is False
    assert res.error_code == "FLIGHTS_LIST_NOT_LOADED"
    
    # Success case: element matches
    # A filter control alone can exist before results load. Require both a
    # flight-results signal and a visible price to avoid false success.
    success_context = {
        "interactive_elements": [
            {"text": "Filter flights - Rs. 4,500", "selector": "#filter"}
        ]
    }
    res = validator.validate(success_context)
    assert res.success is True
    assert res.facts_to_add.get("results_loaded") is True

def test_whatsapp_chat_opened_validator():
    validator = VerifyChatOpened()
    
    # Success case
    success_context = {"interactive_elements": [{"role": "heading", "text": "Rahul"}]}
    res = validator.validate(success_context)
    assert res.success is True
    assert res.facts_to_add.get("chat_opened") is True
