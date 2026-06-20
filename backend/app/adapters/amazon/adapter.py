from typing import List
from app.adapters.base_adapter import BaseAdapter

class AmazonAdapter(BaseAdapter):
    """
    Component 5: Amazon Product Search Adapter
    Coordinates inputs for search bar queries and results verification.
    """
    def __init__(self):
        super().__init__("amazon")

    def identify_site(self, url: str) -> bool:
        return "amazon.com" in url.lower() or "amazon.in" in url.lower()

    def get_custom_validators(self, node_id: str) -> List[str]:
        mapping = {
            "open_site": ["verify_amazon_opened"],
            "input_search_query": ["verify_search_query_entered"],
            "execute_search": ["verify_search_results_loaded"]
        }
        return mapping.get(node_id, [])
