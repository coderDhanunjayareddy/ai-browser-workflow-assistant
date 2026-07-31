from __future__ import annotations

from app.validation.validation_service import ValidationService


class ValidationController:
    def __init__(self, service: ValidationService):
        self.service = service

    def benchmarks(self):
        return self.service.benchmarks()

    def benchmark(self, benchmark_id: str):
        return self.service.benchmark(benchmark_id)

    def report(self):
        return self.service.report()

    def metrics(self):
        return self.service.metrics()

    def diagnostics(self):
        return self.service.diagnostics()

    def migration(self):
        return self.service.migration()

    def readiness(self):
        return self.service.readiness()

    def quality(self):
        return self.service.quality()
