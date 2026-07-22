from __future__ import annotations

from app.contracts.capabilities import CapabilityDescriptor


def required_permissions(capability: CapabilityDescriptor) -> list[str]:
    return list(capability.permissions)


def has_permission(capability: CapabilityDescriptor, granted: set[str]) -> bool:
    return set(capability.permissions).issubset(granted)
