from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class BaseState(BaseModel):
    """Base class for all verified session states."""
    session_id: str
    last_updated: Optional[str] = None
    variables: Dict[str, Any] = Field(default_factory=dict)

class MakeMyTripState(BaseState):
    """Verified state variables for MakeMyTrip workflows."""
    from_city: Optional[str] = None
    to_city: Optional[str] = None
    departure_date: Optional[str] = None
    search_clicked: bool = False
    results_loaded: bool = False
    selected_flight_id: Optional[str] = None
    price: Optional[float] = None
    direct_flight: bool = False

class WhatsAppState(BaseState):
    """Verified state variables for WhatsApp Web workflows."""
    active_chat_contact: Optional[str] = None
    chat_opened: bool = False
    message_content: Optional[str] = None
    message_composed: bool = False
    message_sent: bool = False
