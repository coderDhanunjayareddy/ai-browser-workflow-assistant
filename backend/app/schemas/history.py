from pydantic import BaseModel


class EventHistory(BaseModel):
    id: str
    event_type: str              # approved | rejected | executed
    action_type: str | None
    description: str | None
    target_selector: str | None
    value: str | None
    execution_result: str | None
    safety_level: str | None
    confidence: float | None
    created_at: str


class SessionHistory(BaseModel):
    id: str
    tab_url: str
    tab_title: str
    status: str
    created_at: str
    events: list[EventHistory]


class HistoryResponse(BaseModel):
    sessions: list[SessionHistory]
    total: int
