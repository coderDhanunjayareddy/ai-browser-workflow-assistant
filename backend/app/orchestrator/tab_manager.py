import logging
from typing import Dict, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class TabInfo(BaseModel):
    tab_id: str
    url: str
    title: str
    parent_tab_id: Optional[str] = None
    is_active: bool = False

class MultiTabManager:
    """
    Gap 1: Multi-Tab Manager
    Tracks and coordinates interactions across multiple browser tabs and popups.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.tabs: Dict[str, TabInfo] = {}
        self.active_tab_id: Optional[str] = None

    def register_tab(self, tab_id: str, url: str, title: str, parent_tab_id: Optional[str] = None) -> None:
        self.tabs[tab_id] = TabInfo(tab_id=tab_id, url=url, title=title, parent_tab_id=parent_tab_id)
        if not self.active_tab_id:
            self.set_active_tab(tab_id)
        logger.info(f"Registered tab {tab_id} ({url}) for session {self.session_id}")

    def set_active_tab(self, tab_id: str) -> None:
        if self.active_tab_id in self.tabs:
            self.tabs[self.active_tab_id].is_active = False
        if tab_id in self.tabs:
            self.tabs[tab_id].is_active = True
            self.active_tab_id = tab_id
            logger.info(f"Switched active tab to {tab_id}")
