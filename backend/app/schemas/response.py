from pydantic import BaseModel
from typing import Literal, Optional


class SuggestedAction(BaseModel):
    action_id: str
    action_type: Literal[
        'click',
        'fill',
        'scroll',
        'navigate',
        'wait',
        'select_option',
        'choose_date',
        'hover',
        'keyboard_shortcut',
    ]
    target_selector: str
    value: Optional[str] = None
    description: str
    reasoning: str
    confidence: float
    safety_level: Literal['safe', 'caution', 'danger']


class AnalyzeResponse(BaseModel):
    session_id: str
    analysis: str
    suggested_actions: list[SuggestedAction]
    clarification_question: Optional[str] = None
