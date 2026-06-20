import logging
from typing import Dict, Any, List
from app.extraction_v2.semantic_models import SemanticPageModel, FlightCard, ProductCard

logger = logging.getLogger(__name__)

class AccessibilityNode:
    def __init__(self, role: str, name: str, state: Dict[str, Any], bounds: Dict[str, float]):
        self.role = role
        self.name = name
        self.state = state
        self.bounds = bounds

class ExtractorV2:
    """
    Component 6: Semantic Extraction Engine
    Parses A11y Tree nodes and structured page contexts.
    """
    @staticmethod
    def extract_accessibility_nodes(raw_a11y_tree: List[Dict[str, Any]]) -> List[AccessibilityNode]:
        nodes = []
        for item in raw_a11y_tree:
            nodes.append(AccessibilityNode(
                role=item.get("role", "unknown"),
                name=item.get("name", ""),
                state=item.get("state", {}),
                bounds=item.get("bounds", {})
            ))
        return nodes

    @staticmethod
    def parse_semantic_cards(page_text: str, url: str) -> SemanticPageModel:
        """
        Parses visible page listings (e.g. flight rows, product grids) into semantic Pydantic objects.
        In production, this integrates simple regex/layout pattern matchers or fast LLM parsers.
        """
        logger.info(f"Running semantic card parser for domain: {url}")
        flights = []
        products = []

        # Simple layout mock patterns to demonstrate extraction
        if "makemytrip.com" in url.lower():
            # Mock extracted flight card
            flights.append(FlightCard(
                airline="IndiGo",
                price=4850.0,
                departure_time="06:30",
                arrival_time="08:15",
                stops=0,
                duration="1h 45m",
                element_id="flightCard-indigo-001"
            ))
        elif "amazon" in url.lower() or "flipkart" in url.lower():
            # Mock extracted product card
            products.append(ProductCard(
                title="Wireless Headphone Noise Cancelling",
                price=3499.0,
                rating=4.3,
                reviews_count=210,
                element_id="productCard-headphone-001"
            ))

        return SemanticPageModel(flights=flights, products=products)
