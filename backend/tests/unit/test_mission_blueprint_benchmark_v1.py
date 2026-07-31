from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base
from app.mission.blueprint.expansion import BlueprintExpansionEngine
from app.mission.blueprint.models import validate_blueprint
from app.mission.blueprint.readiness import BlueprintReadinessEvaluator
from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository
from app.mission.intelligence.blueprint_builder import MissionBlueprintBuilder
from app.models.db import MissionIntentRecord


@dataclass(frozen=True)
class BlueprintBenchmark:
    benchmark_id: str
    category: str
    user_goal: str
    expected_classification: str
    expected_capabilities: set[str]
    expected_nodes: list[str]
    expected_dependency_edges: set[tuple[str, str]]
    expected_ready_nodes: set[str]
    expected_blocked_nodes: set[str] = field(default_factory=set)
    expected_clarifications: set[str] = field(default_factory=set)
    expected_risks: set[str] = field(default_factory=set)
    expected_expanded_nodes: set[str] = field(default_factory=set)
    expected_min_ledger_intents: int = 0


RESEARCH_NODES = [
    "define_research_target",
    "discover_sources",
    "collect_candidates",
    "select_sources",
    "read_sources",
    "extract_information",
    "validate_coverage",
    "create_report",
]
RESEARCH_WITH_CLARIFICATION = ["clarify_requirements", *RESEARCH_NODES]
NAVIGATION_NODES = ["define_target_state", "reach_target_state", "verify_target_state"]
NAVIGATION_WITH_CLARIFICATION = ["clarify_requirements", *NAVIGATION_NODES]
EXTRACTION_NODES = ["define_schema", "locate_source", "read_source", "extract_records", "validate_records", "deliver_artifact"]
FILE_NODES = ["define_file_requirement", "access_file", "process_file", "validate_file_result", "deliver_file_result"]


BENCHMARKS = [
    BlueprintBenchmark(
        benchmark_id="research_ai_browser_tools",
        category="Research",
        user_goal=(
            "Research best AI browser automation tools 2026 and return a clean comparison table only "
            "with tool, purpose, pricing, limitation, and url."
        ),
        expected_classification="research",
        expected_capabilities={"Search", "Browser", "Knowledge Extraction", "Validation", "Report Generation"},
        expected_nodes=RESEARCH_WITH_CLARIFICATION,
        expected_dependency_edges={("clarify_requirements", "define_research_target"), ("define_research_target", "discover_sources")},
        expected_ready_nodes={"clarify_requirements"},
        expected_clarifications={"clarify_ranking_or_relevance_policy"},
        expected_risks={"missing_information"},
        expected_expanded_nodes={"clarify_requirements"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="shopping_price_comparison",
        category="Shopping",
        user_goal="Compare prices for noise cancelling headphones and create a short buying table.",
        expected_classification="research",
        expected_capabilities={"Search", "Browser", "Knowledge Extraction", "Validation", "Report Generation"},
        expected_nodes=RESEARCH_NODES,
        expected_dependency_edges={("define_research_target", "discover_sources"), ("validate_coverage", "create_report")},
        expected_ready_nodes={"define_research_target"},
        expected_risks={"payment", "privacy"},
        expected_expanded_nodes={"define_research_target"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="booking_hotel_page",
        category="Booking",
        user_goal="Book a refundable hotel in Hyderabad for next Friday and verify the booking page.",
        expected_classification="navigation",
        expected_capabilities={"Browser", "Validation"},
        expected_nodes=NAVIGATION_NODES,
        expected_dependency_edges={("define_target_state", "reach_target_state"), ("reach_target_state", "verify_target_state")},
        expected_ready_nodes={"define_target_state"},
        expected_risks={"payment"},
        expected_expanded_nodes={"define_target_state"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="authentication_dashboard",
        category="Authentication",
        user_goal="Sign in to my account and open the billing dashboard.",
        expected_classification="navigation",
        expected_capabilities={"Browser", "Validation"},
        expected_nodes=NAVIGATION_WITH_CLARIFICATION,
        expected_dependency_edges={("clarify_requirements", "define_target_state"), ("define_target_state", "reach_target_state")},
        expected_ready_nodes=set(),
        expected_blocked_nodes={"clarify_requirements"},
        expected_clarifications={"clarify_account_or_authentication_context"},
        expected_risks={"authentication", "missing_information"},
    ),
    BlueprintBenchmark(
        benchmark_id="navigation_pricing_page",
        category="Navigation",
        user_goal="Open the pricing page for Example CRM and verify the pricing page is visible.",
        expected_classification="navigation",
        expected_capabilities={"Browser", "Validation"},
        expected_nodes=NAVIGATION_NODES,
        expected_dependency_edges={("define_target_state", "reach_target_state"), ("reach_target_state", "verify_target_state")},
        expected_ready_nodes={"define_target_state"},
        expected_risks={"low"},
        expected_expanded_nodes={"define_target_state"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="file_upload_resume",
        category="File Upload",
        user_goal="Upload the provided resume PDF to the application form and verify the upload.",
        expected_classification="file_processing",
        expected_capabilities={"File Processing", "Validation", "Report Generation"},
        expected_nodes=FILE_NODES,
        expected_dependency_edges={("define_file_requirement", "access_file"), ("validate_file_result", "deliver_file_result")},
        expected_ready_nodes={"define_file_requirement"},
        expected_risks={"privacy"},
        expected_expanded_nodes={"define_file_requirement"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="file_download_invoice",
        category="File Download",
        user_goal="Download the latest invoice PDF to the downloads folder.",
        expected_classification="file_processing",
        expected_capabilities={"File Processing", "Validation", "Report Generation"},
        expected_nodes=FILE_NODES,
        expected_dependency_edges={("define_file_requirement", "access_file"), ("process_file", "validate_file_result")},
        expected_ready_nodes={"define_file_requirement"},
        expected_risks={"low"},
        expected_expanded_nodes={"define_file_requirement"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="form_filling_contact",
        category="Form Filling",
        user_goal="Fill the contact form with name, email, and message but do not submit.",
        expected_classification="navigation",
        expected_capabilities={"Browser", "Validation"},
        expected_nodes=NAVIGATION_NODES,
        expected_dependency_edges={("define_target_state", "reach_target_state"), ("reach_target_state", "verify_target_state")},
        expected_ready_nodes={"define_target_state"},
        expected_risks={"privacy", "irreversible_action"},
        expected_expanded_nodes={"define_target_state"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="directory_data_extraction",
        category="Data Extraction",
        user_goal="Extract records from this directory table with columns name, pricing, and url.",
        expected_classification="data_extraction",
        expected_capabilities={"Browser", "Knowledge Extraction", "Validation", "Report Generation"},
        expected_nodes=EXTRACTION_NODES,
        expected_dependency_edges={("define_schema", "locate_source"), ("extract_records", "validate_records")},
        expected_ready_nodes={"define_schema"},
        expected_risks={"low"},
        expected_expanded_nodes={"define_schema"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="multi_tab_research",
        category="Multi-tab Research",
        user_goal="Open the top 5 relevant results for best AI browser automation tools 2026, read each page, and create a comparison table.",
        expected_classification="research",
        expected_capabilities={"Search", "Browser", "Knowledge Extraction", "Validation", "Report Generation"},
        expected_nodes=RESEARCH_WITH_CLARIFICATION,
        expected_dependency_edges={("clarify_requirements", "define_research_target"), ("read_sources", "extract_information")},
        expected_ready_nodes={"clarify_requirements"},
        expected_clarifications={"clarify_ranking_or_relevance_policy"},
        expected_risks={"missing_information"},
        expected_expanded_nodes={"clarify_requirements"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="dashboard_analysis",
        category="Dashboard Analysis",
        user_goal="Open the sales dashboard and summarize revenue trends in a report.",
        expected_classification="research",
        expected_capabilities={"Search", "Browser", "Knowledge Extraction", "Validation", "Report Generation"},
        expected_nodes=RESEARCH_NODES,
        expected_dependency_edges={("define_research_target", "discover_sources"), ("extract_information", "validate_coverage")},
        expected_ready_nodes={"define_research_target"},
        expected_risks={"low"},
        expected_expanded_nodes={"define_research_target"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="job_application",
        category="Job Application",
        user_goal="Apply to the selected job using my resume and personal email.",
        expected_classification="navigation",
        expected_capabilities={"Browser", "Validation"},
        expected_nodes=NAVIGATION_NODES,
        expected_dependency_edges={("define_target_state", "reach_target_state"), ("reach_target_state", "verify_target_state")},
        expected_ready_nodes={"define_target_state"},
        expected_risks={"privacy", "irreversible_action"},
        expected_expanded_nodes={"define_target_state"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="email_drafting",
        category="Email Drafting",
        user_goal="Draft an email to the vendor requesting pricing details.",
        expected_classification="navigation",
        expected_capabilities={"Browser", "Validation"},
        expected_nodes=NAVIGATION_NODES,
        expected_dependency_edges={("define_target_state", "reach_target_state"), ("reach_target_state", "verify_target_state")},
        expected_ready_nodes={"define_target_state"},
        expected_risks={"privacy"},
        expected_expanded_nodes={"define_target_state"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="calendar_scheduling",
        category="Calendar Scheduling",
        user_goal="Schedule a calendar meeting with the sales team for next Tuesday.",
        expected_classification="navigation",
        expected_capabilities={"Browser", "Validation"},
        expected_nodes=NAVIGATION_NODES,
        expected_dependency_edges={("define_target_state", "reach_target_state"), ("reach_target_state", "verify_target_state")},
        expected_ready_nodes={"define_target_state"},
        expected_risks={"low"},
        expected_expanded_nodes={"define_target_state"},
        expected_min_ledger_intents=1,
    ),
    BlueprintBenchmark(
        benchmark_id="cross_system_invoice_email",
        category="Cross-System Workflow",
        user_goal="Download the latest invoice, extract the total, and draft an email summary.",
        expected_classification="data_extraction",
        expected_capabilities={"Browser", "Knowledge Extraction", "Validation", "Report Generation"},
        expected_nodes=EXTRACTION_NODES,
        expected_dependency_edges={("define_schema", "locate_source"), ("validate_records", "deliver_artifact")},
        expected_ready_nodes={"define_schema"},
        expected_risks={"privacy"},
        expected_expanded_nodes={"define_schema"},
        expected_min_ledger_intents=1,
    ),
]


@pytest.fixture(autouse=True)
def blueprint_flag(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)(), engine


@pytest.mark.parametrize("benchmark", BENCHMARKS, ids=[case.benchmark_id for case in BENCHMARKS])
def test_mission_blueprint_benchmark_catalog_quality(benchmark: BlueprintBenchmark):
    result = MissionBlueprintBuilder().build(
        mission_id=f"benchmark-{benchmark.benchmark_id}",
        user_goal=benchmark.user_goal,
    )
    blueprint = result.blueprint
    readiness = BlueprintReadinessEvaluator().evaluate(blueprint)
    failures = _analyze_failures(benchmark, result, readiness)

    assert failures == []
    validate_blueprint(blueprint)


@pytest.mark.parametrize("benchmark", BENCHMARKS, ids=[case.benchmark_id for case in BENCHMARKS])
def test_mission_blueprint_benchmark_expansion_and_ledger_provenance(benchmark: BlueprintBenchmark):
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        result = MissionBlueprintBuilder().build(
            mission_id=f"benchmark-ledger-{benchmark.benchmark_id}",
            user_goal=benchmark.user_goal,
        )
        repository.create(result.blueprint, reason="benchmark catalog validation", created_by="benchmark_suite")
        readiness = BlueprintReadinessEvaluator().evaluate(result.blueprint)
        repository.save_readiness_snapshot(readiness)

        expansion = BlueprintExpansionEngine(db=db, repository=repository).expand_ready_nodes(
            mission_id=result.blueprint.mission_id,
            readiness=readiness,
        )
        second_expansion = BlueprintExpansionEngine(db=db, repository=repository).expand_ready_nodes(
            mission_id=result.blueprint.mission_id,
            readiness=readiness,
        )
        records = db.query(MissionIntentRecord).filter(
            MissionIntentRecord.mission_id == result.blueprint.mission_id
        ).all()
        failures = _analyze_expansion_failures(benchmark, result.blueprint, expansion, second_expansion, records)

        assert failures == []
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_mission_blueprint_benchmark_catalog_coverage_and_scoring():
    categories = {case.category for case in BENCHMARKS}
    assert categories == {
        "Research",
        "Shopping",
        "Booking",
        "Authentication",
        "Navigation",
        "File Upload",
        "File Download",
        "Form Filling",
        "Data Extraction",
        "Multi-tab Research",
        "Dashboard Analysis",
        "Job Application",
        "Email Drafting",
        "Calendar Scheduling",
        "Cross-System Workflow",
    }

    scores = [_score_benchmark(case) for case in BENCHMARKS]
    assert min(scores) >= 0.85
    assert sum(scores) / len(scores) >= 0.95


def _analyze_failures(benchmark: BlueprintBenchmark, result, readiness) -> list[str]:
    blueprint = result.blueprint
    node_ids = [node.node_id for node in blueprint.nodes]
    dependency_edges = {(dependency.from_node_id, dependency.to_node_id) for dependency in blueprint.dependencies}
    capabilities = set(result.capabilities.capabilities)
    clarifications = {
        item["clarification_id"]
        for item in blueprint.metadata.get("clarification_requirements", [])
    }
    risks = set(result.risks.risks)
    failures: list[str] = []

    if result.mission_type.value != benchmark.expected_classification:
        failures.append(
            f"incorrect classification: expected={benchmark.expected_classification} actual={result.mission_type.value}"
        )
    missing_capabilities = benchmark.expected_capabilities - capabilities
    if missing_capabilities:
        failures.append(f"incorrect capabilities: missing={sorted(missing_capabilities)} actual={sorted(capabilities)}")
    if node_ids != benchmark.expected_nodes:
        failures.append(f"missing or reordered nodes: expected={benchmark.expected_nodes} actual={node_ids}")
    missing_dependencies = benchmark.expected_dependency_edges - dependency_edges
    if missing_dependencies:
        failures.append(f"incorrect dependencies: missing={sorted(missing_dependencies)}")
    if set(readiness.ready_nodes) != benchmark.expected_ready_nodes:
        failures.append(f"incorrect READY nodes: expected={sorted(benchmark.expected_ready_nodes)} actual={readiness.ready_nodes}")
    if not benchmark.expected_blocked_nodes.issubset(set(readiness.blocked_nodes)):
        failures.append(
            f"incorrect blocked nodes: expected_subset={sorted(benchmark.expected_blocked_nodes)} actual={readiness.blocked_nodes}"
        )
    missing_clarifications = benchmark.expected_clarifications - clarifications
    if missing_clarifications:
        failures.append(f"unnecessary or missing clarifications: missing={sorted(missing_clarifications)} actual={sorted(clarifications)}")
    unexpected_required_clarifications = [
        item["clarification_id"]
        for item in blueprint.metadata.get("clarification_requirements", [])
        if item.get("required") and item["clarification_id"] not in benchmark.expected_clarifications
    ]
    if unexpected_required_clarifications:
        failures.append(f"unnecessary clarifications: {unexpected_required_clarifications}")
    missing_risks = benchmark.expected_risks - risks
    if missing_risks:
        failures.append(f"incorrect risk annotation: missing={sorted(missing_risks)} actual={sorted(risks)}")
    if readiness.unreachable_nodes:
        failures.append(f"unreachable nodes: {readiness.unreachable_nodes}")
    if not result.dependencies.critical_path:
        failures.append("invalid critical path: empty")
    return failures


def _analyze_expansion_failures(benchmark, blueprint, expansion, second_expansion, records) -> list[str]:
    failures: list[str] = []
    if set(expansion.expanded_nodes) != benchmark.expected_expanded_nodes:
        failures.append(
            f"incorrect expansion: expected={sorted(benchmark.expected_expanded_nodes)} actual={expansion.expanded_nodes}"
        )
    if len(records) < benchmark.expected_min_ledger_intents:
        failures.append(f"missing ledger intents: expected_min={benchmark.expected_min_ledger_intents} actual={len(records)}")
    if len({record.intent_id for record in records}) != len(records):
        failures.append("duplicate expansion: duplicate ledger intent ids")
    if len(second_expansion.generated_intent_ids) != len(expansion.generated_intent_ids):
        failures.append("duplicate expansion: idempotent expansion returned a different generated intent set")
    for record in records:
        if record.blueprint_id != blueprint.blueprint_id:
            failures.append(f"ledger provenance missing blueprint_id for intent={record.intent_id}")
        if record.blueprint_node_id not in benchmark.expected_expanded_nodes:
            failures.append(f"ledger provenance has unexpected node={record.blueprint_node_id}")
        if record.blueprint_revision != blueprint.revision:
            failures.append(f"ledger provenance has wrong revision for intent={record.intent_id}")
        if record.status != "QUEUED":
            failures.append(f"runtime execution changed during benchmark expansion: status={record.status}")
    return failures


def _score_benchmark(benchmark: BlueprintBenchmark) -> float:
    result = MissionBlueprintBuilder().build(
        mission_id=f"benchmark-score-{benchmark.benchmark_id}",
        user_goal=benchmark.user_goal,
    )
    readiness = BlueprintReadinessEvaluator().evaluate(result.blueprint)
    checks = [
        result.mission_type.value == benchmark.expected_classification,
        benchmark.expected_capabilities.issubset(set(result.capabilities.capabilities)),
        [node.node_id for node in result.blueprint.nodes] == benchmark.expected_nodes,
        benchmark.expected_dependency_edges.issubset(
            {(dependency.from_node_id, dependency.to_node_id) for dependency in result.blueprint.dependencies}
        ),
        set(readiness.ready_nodes) == benchmark.expected_ready_nodes,
        benchmark.expected_blocked_nodes.issubset(set(readiness.blocked_nodes)),
        benchmark.expected_clarifications.issubset(
            {
                item["clarification_id"]
                for item in result.blueprint.metadata.get("clarification_requirements", [])
            }
        ),
        benchmark.expected_risks.issubset(set(result.risks.risks)),
    ]
    return sum(1 for item in checks if item) / len(checks)
