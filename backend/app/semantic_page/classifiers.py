from __future__ import annotations

from app.schemas.request import InteractiveElement, PageContext


def normalize_text(value: str | None, *, max_length: int = 160) -> str:
    return " ".join((value or "").split())[:max_length]


def classify_page_type(page_context: PageContext) -> str:
    text = f"{page_context.title} {page_context.visible_text}".lower()
    if "404" in text or "not found" in text:
        return "error"
    if "search" in text or len(page_context.content_blocks) >= 3:
        return "search_results"
    if any(_is_field(element) for element in page_context.interactive_elements):
        return "form"
    if any((element.role or "").lower() == "dialog" for element in page_context.interactive_elements):
        return "dialog"
    return "page"


def classify_element_node_type(element: InteractiveElement) -> str:
    element_type = (element.type or "").lower()
    role = (element.role or "").lower()
    input_type = (element.input_type or "").lower()
    text = f"{element.text} {element.aria_label} {element.accessibility_name}".lower()
    if role in {"navigation", "menu", "menubar"}:
        return "navigation"
    if role == "dialog":
        return "dialog"
    if element_type in {"input", "textarea"} or input_type in {"text", "email", "password", "search", "number"}:
        return "field"
    if element_type == "select" or role in {"combobox", "listbox"}:
        return "field"
    if input_type == "file" or "upload" in text:
        return "upload"
    if "download" in text:
        return "download"
    return "control"


def classify_target_role(element: InteractiveElement) -> str:
    element_type = (element.type or "").lower()
    role = (element.role or "").lower()
    input_type = (element.input_type or "").lower()
    text = f"{element.text} {element.placeholder} {element.aria_label} {element.accessibility_name}".lower()
    if element_type == "a" or role == "link":
        return "navigate_link"
    if input_type == "file" or "upload" in text:
        return "upload_file"
    if "download" in text:
        return "download_file"
    if "search" in text:
        return "search_field" if element_type in {"input", "textarea"} else "search_control"
    if element_type in {"input", "textarea"}:
        return "form_field"
    if element_type == "select" or role in {"combobox", "listbox"}:
        return "select_control"
    if "submit" in text:
        return "submit_control"
    return "activate_control"


def _is_field(element: InteractiveElement) -> bool:
    return classify_element_node_type(element) == "field"
