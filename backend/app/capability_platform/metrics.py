from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CapabilityMetric:
    capability_id: str
    calls: int = 0
    failures: int = 0
    latency_ms: int = 0


class CapabilityMetrics:
    def __init__(self):
        self._metrics: dict[str, CapabilityMetric] = {}

    def record(self, capability_id: str, *, success: bool = True, latency_ms: int = 0) -> CapabilityMetric:
        metric = self._metrics.setdefault(capability_id, CapabilityMetric(capability_id))
        metric.calls += 1
        metric.latency_ms += max(0, latency_ms)
        if not success:
            metric.failures += 1
        return metric

    def snapshot(self) -> dict[str, dict[str, int | str]]:
        return {
            capability_id: {
                "capability_id": metric.capability_id,
                "calls": metric.calls,
                "failures": metric.failures,
                "latency_ms": metric.latency_ms,
            }
            for capability_id, metric in self._metrics.items()
        }
