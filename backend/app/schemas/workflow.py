from typing import Literal

from pydantic import BaseModel

from app.schemas.response import SuggestedAction


class LogEventRequest(BaseModel):
    session_id: str
    event_type: Literal["approved", "rejected", "executed"]
    action: SuggestedAction
    tab_url: str = ""
    tab_title: str = ""
    execution_result: str | None = None  # Populated for event_type == "executed"


class LogEventResponse(BaseModel):
    logged: bool
    event_id: str
