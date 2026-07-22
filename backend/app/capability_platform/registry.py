from __future__ import annotations

from app.contracts.capabilities import CapabilityDescriptor, CapabilityHealth
from app.feature_flags import is_shadow_or_active


_BROWSER_CAPABILITY_IDS = [
    ("browser.click", "Activate a visible page control or link"),
    ("browser.fill", "Fill a text-compatible form field"),
    ("browser.select_option", "Select an option in a native or adapted control"),
    ("browser.choose_date", "Choose a date using existing widget support"),
    ("browser.scroll", "Scroll the active page or scroll container"),
    ("browser.navigate", "Navigate the active tab to a URL"),
    ("browser.wait", "Wait for a bounded duration"),
    ("browser.open_new_tab", "Open a new browser tab"),
    ("browser.switch_tab", "Switch to an existing browser tab"),
    ("browser.close_tab", "Close an eligible browser tab"),
    ("browser.focus_existing_tab", "Focus an existing browser tab"),
    ("browser.upload", "Upload an explicitly requested local file"),
    ("browser.download", "Detect and record browser downloads"),
    ("browser.extract_visible_fact", "Read visible page information"),
    ("browser.observe", "Capture current page observation"),
    ("user.ask", "Request clarification from the user"),
    ("user.handoff", "Hand off work to the user when required"),
]


class CapabilityRegistry:
    def __init__(self, run_id: str = "capability-platform"):
        self.run_id = run_id
        self._capabilities: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        self._capabilities[descriptor.id] = descriptor

    def get(self, capability_id: str) -> CapabilityDescriptor | None:
        return self._capabilities.get(capability_id)

    def list(self) -> list[CapabilityDescriptor]:
        return list(self._capabilities.values())

    def compact_manifest(self) -> list[dict[str, str]]:
        if not is_shadow_or_active("V3_CAPABILITY_PLATFORM"):
            return []
        return [
            {
                "id": capability.id,
                "version": capability.version,
                "purpose": capability.purpose,
                "health": capability.health.status if capability.health else "available",
            }
            for capability in self.list()
        ]


def default_registry(run_id: str = "capability-platform") -> CapabilityRegistry:
    registry = CapabilityRegistry(run_id=run_id)
    health = CapabilityHealth(run_id=run_id, status="available")
    for capability_id, purpose in _BROWSER_CAPABILITY_IDS:
        registry.register(
            CapabilityDescriptor(
                run_id=run_id,
                id=capability_id,
                version="1.0.0",
                provider="production",
                purpose=purpose,
                permissions=["page_interaction"] if capability_id.startswith("browser.") else ["user_interaction"],
                constraints=[],
                environments=["extension"],
                health=health,
                feature_flag=None,
            )
        )
    return registry
