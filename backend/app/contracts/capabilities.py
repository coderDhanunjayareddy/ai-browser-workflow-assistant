from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.contracts.base import VersionedContract
from app.contracts.versions import CAPABILITY_DESCRIPTOR_V1, CAPABILITY_HEALTH_V1


CapabilityStatus = Literal["available", "degraded", "unavailable"]


class CapabilityHealth(VersionedContract):
    schema_version: str = CAPABILITY_HEALTH_V1
    producer: str = "backend.capability_platform"
    status: CapabilityStatus = "available"
    checked_at: str | None = None
    latency_ms: int | None = None
    error_rate: float = 0.0
    reason: str | None = None


class CapabilityDescriptor(VersionedContract):
    schema_version: str = CAPABILITY_DESCRIPTOR_V1
    producer: str = "backend.capability_platform"
    id: str
    version: str
    provider: str
    purpose: str
    inputs_schema: dict[str, Any] = Field(default_factory=dict)
    outputs_schema: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    environments: list[str] = Field(default_factory=list)
    health: CapabilityHealth | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    feature_flag: str | None = None
