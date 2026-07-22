from __future__ import annotations

from app.capability_platform.registry import CapabilityRegistry, default_registry


def discover_capabilities(registry: CapabilityRegistry | None = None) -> list[str]:
    source = registry or default_registry()
    return [capability.id for capability in source.list()]
