from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.capability_platform.manifest import load_v4_browser_capability_manifest
from app.feature_flags import get_flag_state


MaturityLevel = Literal[0, 1, 2, 3, 4, 5]
RolloutStatus = Literal["experimental", "internal", "shadow", "beta", "production", "ga"]
CertificationStatus = Literal["blocked", "experimental", "beta", "certified", "production_ready"]


@dataclass(frozen=True)
class BrowserCapabilityRecord:
    capability_id: str
    version: str
    category: str
    description: str
    dependencies: tuple[str, ...]
    feature_flag: str
    maturity_level: MaturityLevel
    target_maturity_level: MaturityLevel
    supported_browsers: tuple[str, ...]
    supported_websites: tuple[str, ...]
    site_adapters: tuple[str, ...]
    benchmarks: tuple[str, ...]
    metrics: tuple[str, ...]
    known_limitations: tuple[str, ...]
    rollout_status: RolloutStatus
    safety_constraints: tuple[str, ...]
    failure_classes: tuple[str, ...]
    owner: str

    @classmethod
    def from_manifest(cls, entry: dict[str, Any]) -> "BrowserCapabilityRecord":
        return cls(
            capability_id=str(entry["capability_id"]),
            version=str(entry["version"]),
            category=str(entry["category"]),
            description=str(entry["description"]),
            dependencies=tuple(str(v) for v in entry["dependencies"]),
            feature_flag=str(entry["feature_flag"]),
            maturity_level=_maturity(entry["maturity_level"]),
            target_maturity_level=_maturity(entry["target_maturity_level"]),
            supported_browsers=tuple(str(v) for v in entry["supported_browsers"]),
            supported_websites=tuple(str(v) for v in entry["supported_websites"]),
            site_adapters=tuple(str(v) for v in entry.get("site_adapters", [])),
            benchmarks=tuple(str(v) for v in entry["benchmarks"]),
            metrics=tuple(str(v) for v in entry["metrics"]),
            known_limitations=tuple(str(v) for v in entry["known_limitations"]),
            rollout_status=_rollout(entry["rollout_status"]),
            safety_constraints=tuple(str(v) for v in entry["safety_constraints"]),
            failure_classes=tuple(str(v) for v in entry["failure_classes"]),
            owner=str(entry["owner"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "version": self.version,
            "category": self.category,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "feature_flag": self.feature_flag,
            "feature_flag_state": get_flag_state(self.feature_flag).value,
            "maturity_level": self.maturity_level,
            "target_maturity_level": self.target_maturity_level,
            "supported_browsers": list(self.supported_browsers),
            "supported_websites": list(self.supported_websites),
            "site_adapters": list(self.site_adapters),
            "benchmarks": list(self.benchmarks),
            "metrics": list(self.metrics),
            "known_limitations": list(self.known_limitations),
            "rollout_status": self.rollout_status,
            "safety_constraints": list(self.safety_constraints),
            "failure_classes": list(self.failure_classes),
            "owner": self.owner,
            "certification_status": certification_status(self),
        }


def list_browser_capabilities() -> list[BrowserCapabilityRecord]:
    return [
        BrowserCapabilityRecord.from_manifest(entry)
        for entry in load_v4_browser_capability_manifest()
    ]


def get_browser_capability(capability_id: str) -> BrowserCapabilityRecord | None:
    return next(
        (capability for capability in list_browser_capabilities() if capability.capability_id == capability_id),
        None,
    )


def browser_capability_manifest() -> list[dict[str, Any]]:
    return [capability.to_dict() for capability in list_browser_capabilities()]


def certification_status(capability: BrowserCapabilityRecord) -> CertificationStatus:
    flag_state = get_flag_state(capability.feature_flag).value
    if flag_state == "off" and capability.rollout_status not in {"experimental", "shadow"}:
        return "blocked"
    if capability.maturity_level >= 5 and capability.rollout_status in {"production", "ga"}:
        return "production_ready"
    if capability.maturity_level >= 4 and capability.rollout_status in {"beta", "production", "ga"}:
        return "certified"
    if capability.maturity_level >= 3 and capability.rollout_status in {"beta", "shadow", "internal"}:
        return "beta"
    if capability.maturity_level >= 1:
        return "experimental"
    return "blocked"


def certification_report() -> dict[str, Any]:
    capabilities = list_browser_capabilities()
    statuses: dict[str, int] = {}
    rollout: dict[str, int] = {}
    maturity: dict[str, int] = {}
    records = []
    for capability in capabilities:
        status = certification_status(capability)
        statuses[status] = statuses.get(status, 0) + 1
        rollout[capability.rollout_status] = rollout.get(capability.rollout_status, 0) + 1
        maturity[str(capability.maturity_level)] = maturity.get(str(capability.maturity_level), 0) + 1
        records.append(capability.to_dict())
    return {
        "schema_version": "browser_capability_certification.v1",
        "wave": "v4_wave_1_control_bedrock",
        "capability_count": len(capabilities),
        "status_counts": statuses,
        "rollout_counts": rollout,
        "maturity_counts": maturity,
        "capabilities": records,
    }


def _maturity(raw: Any) -> MaturityLevel:
    value = int(raw)
    if value not in {0, 1, 2, 3, 4, 5}:
        raise ValueError(f"invalid maturity level: {raw!r}")
    return value  # type: ignore[return-value]


def _rollout(raw: Any) -> RolloutStatus:
    value = str(raw).lower()
    allowed = {"experimental", "internal", "shadow", "beta", "production", "ga"}
    if value not in allowed:
        raise ValueError(f"invalid rollout status: {raw!r}")
    return value  # type: ignore[return-value]
