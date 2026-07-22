from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricPoint:
    name: str
    value: float
    run_id: str
    tags: dict[str, str]


class InMemoryMetricSink:
    def __init__(self):
        self.points: list[MetricPoint] = []

    def record(self, name: str, value: float, *, run_id: str, tags: dict[str, str] | None = None) -> None:
        self.points.append(MetricPoint(name=name, value=value, run_id=run_id, tags=tags or {}))

    def snapshot(self) -> list[MetricPoint]:
        return list(self.points)


default_metric_sink = InMemoryMetricSink()
