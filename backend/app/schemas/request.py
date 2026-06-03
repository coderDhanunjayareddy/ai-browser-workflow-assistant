from pydantic import BaseModel, Field
from typing import Optional


class InteractiveElement(BaseModel):
    type: str
    text: str
    selector: str
    visible: bool
    input_type: Optional[str] = None
    placeholder: Optional[str] = None


class ContentBlock(BaseModel):
    text: str
    selector: str


class PageContext(BaseModel):
    url: str
    title: str
    metadata: dict[str, str] = Field(default_factory=dict, max_length=20)
    interactive_elements: list[InteractiveElement] = Field(default_factory=list, max_length=150)
    content_blocks: list[ContentBlock] = Field(default_factory=list, max_length=50)
    headings: list[str] = Field(default_factory=list, max_length=10)
    selected_text: str
    visible_text: str
    images: list[str] = Field(default_factory=list, max_length=50)


class PriorStep(BaseModel):
    """One already-executed step sent back to the AI for context."""
    action_type: str
    description: str
    target_selector: Optional[str] = None
    value: Optional[str] = None
    execution_result: str  # "success" or the error message
    page_analysis: Optional[str] = None
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    page_metadata: dict[str, str] = Field(default_factory=dict, max_length=20)


class AnalyzeRequest(BaseModel):
    session_id: str
    task: str = Field(min_length=1, max_length=100000)
    page_context: PageContext
    prior_steps: list[PriorStep] = Field(default_factory=list)
    supplemental_context: str = Field(default="", max_length=3000)
