import pytest
from app.state_engine.state_models import MakeMyTripState, WhatsAppState
from app.state_engine.state_transitions import StateFSM, StateFSMError

def test_makemytrip_state_validation():
    state = MakeMyTripState(session_id="test_session")
    assert state.session_id == "test_session"
    assert state.search_clicked is False
    assert state.results_loaded is False

def test_whatsapp_state_validation():
    state = WhatsAppState(session_id="test_session")
    assert state.session_id == "test_session"
    assert state.chat_opened is False

def test_fsm_valid_transition():
    # Valid: search_clicked is set to True, or was already True
    current = {"search_clicked": False}
    updates = {"search_clicked": True}
    # Should compile without exception
    StateFSM.validate_transition(current, updates)

def test_fsm_invalid_transition():
    # Invalid: results_loaded is True but search_clicked is False
    current = {"search_clicked": False}
    updates = {"results_loaded": True}
    with pytest.raises(StateFSMError):
        StateFSM.validate_transition(current, updates)
