from pydantic import BaseModel, Field
from typing import Any, Optional


class InteractiveElement(BaseModel):
    type: str
    text: str
    selector: str
    visible: bool
    input_type: Optional[str] = None
    placeholder: Optional[str] = None
    role: Optional[str] = None
    aria_label: Optional[str] = None
    accessibility_name: Optional[str] = None
    state: dict = Field(default_factory=dict)
    bounding_box: dict = Field(default_factory=dict)
    element_id: Optional[str] = None
    href: Optional[str] = None
    semantic_kind: Optional[str] = None
    selector_id: Optional[str] = None


class ContentBlock(BaseModel):
    text: str
    selector: str
    href: Optional[str] = None


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
    screenshot_base64: Optional[str] = None


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
    # V3.0 Cognitive Memory: enriched handoff context forwarded from AssistResponse.
    # Typed as Any to avoid a cross-schema import; callers pass WorkflowHandoffPayload.
    handoff_payload: Optional[Any] = Field(default=None)
