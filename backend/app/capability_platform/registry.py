from __future__ import annotations

from app.contracts.capabilities import CapabilityDescriptor, CapabilityHealth
from app.feature_flags import is_shadow_or_active
from app.capability_platform.manifest import load_capability_manifest


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
    for entry in load_capability_manifest():
        health = CapabilityHealth(run_id=run_id, status="available")
        registry.register(
            CapabilityDescriptor(
                run_id=run_id,
                id=entry["id"],
                version=entry["version"],
                provider="production",
                purpose=entry["purpose"],
                permissions=list(entry.get("permissions", [])),
                constraints=list(entry.get("constraints", [])),
                environments=list(entry.get("environments", [])),
                health=health,
                feature_flag=None,
            )
        )
    return registry
