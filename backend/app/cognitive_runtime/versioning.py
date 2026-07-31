from __future__ import annotations

from dataclasses import asdict, dataclass


SCHEMA_VERSION = "cognitive_runtime.v2.wave1"
RUNTIME_VERSION = "2.0.0-wave1"


@dataclass(frozen=True)
class RuntimeVersion:
    """Semantic version metadata for Cognitive Runtime V2."""

    runtime_version: str = RUNTIME_VERSION
    schema_version: str = SCHEMA_VERSION
    min_compatible_runtime: str = "2.0.0"
    migration_ready: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> RuntimeVersion:
        payload = dict(payload or {})
        return cls(
            runtime_version=str(payload.get("runtime_version") or RUNTIME_VERSION),
            schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
            min_compatible_runtime=str(payload.get("min_compatible_runtime") or "2.0.0"),
            migration_ready=bool(payload.get("migration_ready", True)),
        )

    def is_compatible_with(self, other: RuntimeVersion | str) -> bool:
        other_version = other.runtime_version if isinstance(other, RuntimeVersion) else str(other)
        return _major(other_version) == _major(self.runtime_version)


def validate_runtime_compatibility(current: RuntimeVersion, stored: RuntimeVersion) -> None:
    if current.schema_version != stored.schema_version:
        raise ValueError(f"Incompatible cognitive schema: {stored.schema_version}")
    if not current.is_compatible_with(stored):
        raise ValueError(f"Incompatible cognitive runtime: {stored.runtime_version}")


def _major(version: str) -> str:
    return str(version).split(".", 1)[0]
