from typing import List
from app.adapters.base_adapter import BaseAdapter

class GmailAdapter(BaseAdapter):
    """
    Component 5: Gmail Draft Workflow Adapter
    Coordinates inputs for draft compose and saving verification.
    """
    def __init__(self):
        super().__init__("gmail")

    def identify_site(self, url: str) -> bool:
        return "gmail.com" in url.lower() or "mail.google.com" in url.lower()

    def get_custom_validators(self, node_id: str) -> List[str]:
        mapping = {
            "open_site": ["verify_gmail_opened"],
            "click_compose": ["verify_compose_window_opened"],
            "input_recipient_and_subject": ["verify_recipient_subject_entered"],
            "input_body_text": ["verify_body_text_entered"]
        }
        return mapping.get(node_id, [])
