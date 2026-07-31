from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.models.db import MissionIntentRecord, ValidationBenchmarkRunRecord
from app.validation.benchmark_catalog import benchmark_catalog, get_benchmark
from app.validation.benchmark_diagnostics import diagnose_benchmark
from app.validation.benchmark_metrics import compute_benchmark_metrics
from app.validation.benchmark_models import BenchmarkRunInput
from app.validation.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.validation.benchmark_report import BenchmarkReportBuilder
from app.validation.benchmark_runner import BenchmarkRunner
from app.validation.migration_readiness import MigrationReadinessEvaluator
from app.validation.quality_gates import QualityGateEvaluator
from app.validation.validation_service import ValidationService


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setattr(settings, "cognitive_runtime_v2", "shadow")


def _healthy_snapshot():
    return {
        "mission_completed": True,
        "completion_accuracy": 1.0,
        "planner_calls": 1,
        "ledger": {"intent_count": 4, "browser_intents": 2, "completed": True},
        "providers": {"browser_control": 2, "knowledge_extraction": 1, "validation": 1},
        "evidence": {"coverage": 0.95, "confidence": 0.91},
        "blueprint": {"readiness": 0.9, "expansion_efficiency": 1.0, "nodes": ["a", "b", "c"]},
        "validation_accuracy": 0.92,
        "runtime_stability": 1.0,
        "failure_recovery_rate": 0.85,
        "comparisons": [
            {"runtime_decision": "CONTINUE", "cognitive_decision": "CONTINUE", "agreement": "exact", "confidence": 0.92},
            {"runtime_decision": "COMPLETE", "cognitive_decision": "COMPLETE", "agreement": "semantic", "confidence": 0.88},
        ],
    }


def test_catalog_contains_required_categories():
    catalog = benchmark_catalog()
    categories = {item.category for item in catalog}

    assert len(catalog) == 16
    assert "research" in categories
    assert "cross_system_workflow" in categories
    assert get_benchmark("benchmark_research") is not None


def test_benchmark_runner_produces_passive_result():
    benchmark = get_benchmark("benchmark_research")
    result = BenchmarkRunner().run(
        BenchmarkRunInput(
            benchmark=benchmark,
            mission_id="mission-validation",
            runtime_snapshot=_healthy_snapshot(),
            comparison_snapshot={"comparisons": _healthy_snapshot()["comparisons"]},
        )
    )

    assert result.status == "evaluated"
    assert result.score > 0.8
    assert result.report["regression_summary"]["runtime_v1_unchanged"] is True
    assert result.metrics["planner_calls"] == 1


def test_metrics_diagnostics_quality_and_migration_readiness():
    metrics = compute_benchmark_metrics(_healthy_snapshot())
    diagnostics = diagnose_benchmark(metrics, _healthy_snapshot())
    quality = QualityGateEvaluator().evaluate(metrics)
    readiness = MigrationReadinessEvaluator().evaluate(metrics, _healthy_snapshot()["comparisons"])

    assert metrics["mission_success_rate"] == 1.0
    assert diagnostics["root_cause"] == "none"
    assert quality["gates"]["100_percent_mission_integrity"] is True
    assert readiness["CONTINUE"]["readiness"] > 0.8


def test_report_generation_is_structured():
    metrics = compute_benchmark_metrics(_healthy_snapshot())
    diagnostics = diagnose_benchmark(metrics, _healthy_snapshot())
    report = BenchmarkReportBuilder().build(
        benchmark=get_benchmark("benchmark_research").to_dict(),
        metrics=metrics,
        diagnostics=diagnostics,
        comparisons=_healthy_snapshot()["comparisons"],
    )

    assert "mission_report" in report
    assert "subsystem_report" in report
    assert "migration_report" in report
    assert "readiness_report" in report


def test_repository_and_service_store_passive_runs(db_session):
    service = ValidationService(SqlAlchemyBenchmarkRepository(db_session))
    results = service.evaluate_catalog()

    assert len(results) == 16
    assert db_session.query(ValidationBenchmarkRunRecord).count() == 16
    assert db_session.query(MissionIntentRecord).count() == 0
    assert service.metrics()["benchmark_runs"] == 16
    assert service.report()["regression_summary"]["execution_impact"] == "none"


def test_validation_api_is_read_only_and_feature_flagged(db_session, monkeypatch):
    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        paths = [
            "/validation/benchmarks",
            "/validation/benchmark/benchmark_research",
            "/validation/report",
            "/validation/metrics",
            "/validation/diagnostics",
            "/validation/migration",
            "/validation/readiness",
            "/validation/quality",
        ]
        responses = [client.get(path) for path in paths]
        monkeypatch.setattr(settings, "cognitive_runtime_v2", "off")
        disabled = client.get("/validation/benchmarks")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert all(response.status_code == 200 for response in responses)
    assert len(responses[0].json()["benchmarks"]) == 16
    assert responses[1].json()["benchmark_id"] == "benchmark_research"
    assert responses[5].json()["migration_readiness"]["WAIT"]["risk"] in {"low", "medium", "high"}
    assert disabled.status_code == 404
    assert db_session.query(MissionIntentRecord).count() == 0


def test_runtime_isolation_no_execution_side_effects(db_session):
    before = db_session.query(MissionIntentRecord).count()
    ValidationService(SqlAlchemyBenchmarkRepository(db_session)).evaluate_catalog()
    after = db_session.query(MissionIntentRecord).count()

    assert before == after == 0
