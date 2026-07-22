from __future__ import annotations

from app.contracts.capabilities import CapabilityDescriptor


def constraints_for(capability: CapabilityDescriptor) -> list[str]:
    return list(capability.constraints)


def is_destructive(capability: CapabilityDescriptor) -> bool:
    return "destructive" in set(capability.constraints)
