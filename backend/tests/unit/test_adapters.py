import pytest
from app.adapters.makemytrip.adapter import MakeMyTripAdapter
from app.adapters.whatsapp.adapter import WhatsAppAdapter

def test_makemytrip_adapter_rules():
    adapter = MakeMyTripAdapter()
    
    assert adapter.identify_site("https://www.makemytrip.com/") is True
    assert adapter.identify_site("https://web.whatsapp.com/") is False
    
    # Check knowledge JSON metadata loaded
    assert adapter.knowledge.get("version") == "2.2"
    assert "from_city" in adapter.knowledge.get("critical_fields", [])
    
    # Check node mapping
    assert "verify_flights_loaded" in adapter.get_custom_validators("extract_flights")

def test_whatsapp_adapter_rules():
    adapter = WhatsAppAdapter()
    
    assert adapter.identify_site("https://web.whatsapp.com/") is True
    assert adapter.identify_site("https://www.makemytrip.com/") is False
    assert adapter.knowledge.get("version") == "2.2"
    assert "active_chat_contact" in adapter.knowledge.get("critical_fields", [])
