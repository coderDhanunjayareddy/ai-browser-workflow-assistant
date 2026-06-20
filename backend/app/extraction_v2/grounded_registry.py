import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class GroundedElement:
    def __init__(self, element_id: str, selector: str, text: str, role: Optional[str] = None, bounding_box: Optional[Dict[str, float]] = None):
        self.element_id = element_id
        self.selector = selector
        self.text = text
        self.role = role
        self.bounding_box = bounding_box or {}

class GroundedElementRegistry:
    """
    Component 6.5: Grounded Element ID Registry
    Generates and maintains active page mappings from generated runtime stable element IDs
    to actual DOM selectors, texts, roles, and bounding box coordinates.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.elements: Dict[str, GroundedElement] = {}

    def register_elements(self, raw_elements: List[Dict[str, Any]]) -> None:
        """
        Populates registry with the current page's interactive elements.
        """
        self.elements.clear()
        for idx, el in enumerate(raw_elements):
            element_id = el.get("element_id") or f"el_{self.session_id[-4:]}_{idx:03d}"
            
            grounded_el = GroundedElement(
                element_id=element_id,
                selector=el.get("selector", ""),
                text=el.get("text", ""),
                role=el.get("role"),
                bounding_box=el.get("bounding_box")
            )
            self.elements[element_id] = grounded_el
            
        logger.info(f"Registered {len(self.elements)} elements for session {self.session_id}")

    def get_element(self, element_id: str) -> Optional[GroundedElement]:
        return self.elements.get(element_id)

    def resolve_selector(self, element_id: str) -> Optional[str]:
        el = self.get_element(element_id)
        if el:
            return el.selector
        return None
