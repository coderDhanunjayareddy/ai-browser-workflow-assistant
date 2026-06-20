from typing import List, Dict, Any
from app.adapters.base_adapter import BaseAdapter

class WhatsAppAdapter(BaseAdapter):
    """
    Component 5: WhatsApp Web Adapter
    Resolves obfuscated DOM nodes by leveraging accessibility properties.
    """
    def __init__(self):
        super().__init__("whatsapp")

    def identify_site(self, url: str) -> bool:
        return "web.whatsapp.com" in url.lower()

    def get_custom_validators(self, node_id: str) -> List[str]:
        mapping = {
            "open_whatsapp": ["verify_chats_loaded"],
            "select_chat": ["verify_chat_opened"],
            "compose_message": ["verify_message_composed"],
            "send_message": ["verify_message_sent"]
        }
        return mapping.get(node_id, [])
