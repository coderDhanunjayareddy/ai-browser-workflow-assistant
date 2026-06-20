from typing import List, Dict, Any
from app.adapters.base_adapter import BaseAdapter

class MakeMyTripAdapter(BaseAdapter):
    """
    Component 5: MakeMyTrip Site Adapter
    Coordinates inputs for search origin, destinations, and calendar select days.
    """
    def __init__(self):
        super().__init__("makemytrip")

    def identify_site(self, url: str) -> bool:
        return "makemytrip.com" in url.lower()

    def get_custom_validators(self, node_id: str) -> List[str]:
        mapping = {
            "open_site": ["verify_site_opened"],
            "set_origin": ["verify_origin_selected"],
            "set_destination": ["verify_destination_selected"],
            "set_date": ["verify_date_selected"],
            "execute_search": ["verify_search_clicked"],
            "extract_flights": ["verify_flights_loaded"]
        }
        return mapping.get(node_id, [])
