"""Phase F — Unit tests: certification framework (deterministic, browser-free)."""
import pytest

from app.certification import (
    models, fixtures, scenarios, reliability, failure_catalog, report, trace,
)
from app.certification.models import (
    ScenarioCategory, OutcomeStatus, CriterionKind, SuccessCriterion, CertificationResult,
    CriterionResult, WorkflowOutcome,
)
from app.certification.failure_catalog import Reproducibility, ResolutionStatus
from app.certification.reliability import percentile


@pytest.fixture(autouse=True)
def _clean():
    reliability._reset_for_testing()
    failure_catalog._reset_for_testing()
    yield
    reliability._reset_for_testing()
    failure_catalog._reset_for_testing()


class TestModels:
    def test_scenario_to_dict(self):
        scs = scenarios.build_scenarios()
        d = scs[0].to_dict()
        for k in ["scenario_id", "name", "website", "workflow", "category", "fixture",
                  "expected_outcome", "success_criteria", "browser", "requires_auth", "known_limitations"]:
            assert k in d

    def test_result_passed_property(self):
        r = CertificationResult("s", "n", "C", "w", OutcomeStatus.passed)
        assert r.passed is True
        r2 = CertificationResult("s", "n", "C", "w", OutcomeStatus.failed)
        assert r2.passed is False

    def test_criterion_result_dict(self):
        d = CriterionResult("K", "detail", True, "obs").to_dict()
        assert d == {"kind": "K", "detail": "detail", "passed": True, "observed": "obs"}


class TestFixtures:
    def test_18_fixtures_present(self):
        assert len(fixtures.FIXTURES) == 18
        for p in ["/login", "/register", "/dashboard", "/crud", "/search", "/upload", "/download",
                  "/pagination", "/modal", "/multistep", "/scroll", "/nav", "/tabs", "/accordion",
                  "/dynamic", "/toast", "/confirm", "/dragdrop"]:
            assert p in fixtures.FIXTURES

    def test_fixture_html_lookup(self):
        assert "<form" in fixtures.fixture_html("/login")
        assert fixtures.fixture_html("login") == fixtures.fixture_html("/login")
        assert fixtures.fixture_html("/missing") is None

    def test_fixtures_are_valid_wi_inputs(self):
        from app.website_intelligence import analyzer
        # each fixture analyzes deterministically and yields a page model
        for path, html in fixtures.FIXTURES.items():
            res = analyzer.analyze_html(html, title=path)
            assert res.page.root.type.value == "PAGE"

    def test_semantic_structures_present(self):
        from app.website_intelligence import analyzer
        cases = {"/login": "FORM", "/crud": "TABLE", "/nav": "NAVIGATION", "/tabs": "TABS",
                 "/accordion": "ACCORDION", "/pagination": "PAGINATION", "/upload": "UPLOAD",
                 "/download": "DOWNLOAD", "/dashboard": "DASHBOARD", "/confirm": "DIALOG",
                 "/search": "SEARCH_BAR"}
        for path, stype in cases.items():
            tc = analyzer.analyze_html(fixtures.FIXTURES[path]).page.type_counts
            assert tc.get(stype, 0) >= 1, f"{path} missing {stype}"

    def test_server_starts_and_serves(self):
        srv = fixtures.FixtureServer().start()
        try:
            import urllib.request
            with urllib.request.urlopen(srv.base_url + "/login", timeout=5) as r:
                body = r.read().decode()
            assert "Acme Login" in body
            with urllib.request.urlopen(srv.base_url + "/download-file", timeout=5) as r:
                assert r.read() == fixtures.DOWNLOAD_BODY
        finally:
            srv.stop()


class TestScenarios:
    def test_all_scenarios_well_formed(self):
        scs = scenarios.build_scenarios()
        assert len(scs) >= 20
        ids = [s.scenario_id for s in scs]
        assert len(ids) == len(set(ids))  # unique
        for s in scs:
            assert s.build_steps is not None
            steps = s.build_steps("http://x")
            assert len(steps) >= 1
            assert s.success_criteria
            assert isinstance(s.category, ScenarioCategory)

    def test_categories_cover_required_workflows(self):
        cats = {s.category for s in scenarios.build_scenarios()}
        for required in [ScenarioCategory.form_submit, ScenarioCategory.search, ScenarioCategory.filter,
                         ScenarioCategory.table_edit, ScenarioCategory.upload, ScenarioCategory.download,
                         ScenarioCategory.navigation, ScenarioCategory.dialog, ScenarioCategory.recovery,
                         ScenarioCategory.resume, ScenarioCategory.pagination, ScenarioCategory.multistep,
                         ScenarioCategory.tabs, ScenarioCategory.accordion, ScenarioCategory.dynamic_loading,
                         ScenarioCategory.toast]:
            assert required in cats

    def test_steps_reference_served_fixtures(self):
        for s in scenarios.build_scenarios():
            assert s.fixture in fixtures.FIXTURES


class TestReliability:
    def test_percentile(self):
        assert percentile([], 50) == 0.0
        assert percentile([5], 95) == 5.0
        assert percentile([1, 2, 3, 4], 50) == 2.5
        assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9.1

    def test_record_and_rollup(self):
        for i in range(10):
            reliability.record_workflow(WorkflowOutcome(f"s{i}", "FORM_SUBMIT", "app", i < 8, float(i * 10)))
        m = reliability.metrics()
        assert m["workflows_total"] == 10
        assert m["workflows_passed"] == 8
        assert m["workflow_success_rate"] == 0.8
        assert m["duration_ms"]["p50"] >= 0
        assert "FORM_SUBMIT" in m["category_success"]
        assert m["category_success"]["FORM_SUBMIT"]["total"] == 10

    def test_semantic_latency(self):
        reliability.record_semantic_latency(2.0)
        reliability.record_semantic_latency(4.0)
        m = reliability.metrics()
        assert m["semantic_analysis_ms"]["samples"] == 2

    def test_merges_step_metrics(self):
        m = reliability.metrics()
        assert "step_metrics" in m   # merged from exec_metrics


class TestFailureCatalog:
    def test_record_and_dedup(self):
        failure_catalog.record(category="FORM", website="a", workflow="w", seen_at=100.0)
        failure_catalog.record(category="FORM", website="a", workflow="w", seen_at=200.0)
        recs = failure_catalog.list_all()
        assert len(recs) == 1
        assert recs[0].occurrences == 2
        assert recs[0].first_seen == 100.0
        assert recs[0].last_seen == 200.0
        assert recs[0].reproducibility == Reproducibility.intermittent

    def test_promotes_to_always(self):
        for t in [1.0, 2.0, 3.0]:
            failure_catalog.record(category="X", website="a", workflow="w", seen_at=t)
        assert failure_catalog.list_all()[0].reproducibility == Reproducibility.always

    def test_distinct_keys(self):
        failure_catalog.record(category="A", website="x", workflow="w", seen_at=1.0)
        failure_catalog.record(category="B", website="x", workflow="w", seen_at=1.0)
        assert failure_catalog.summary()["total_distinct"] == 2

    def test_summary_shape(self):
        failure_catalog.record(category="A", website="x", workflow="w", seen_at=1.0,
                               resolution_status=ResolutionStatus.mitigated)
        s = failure_catalog.summary()
        for k in ["total_distinct", "total_occurrences", "by_category", "by_resolution", "records"]:
            assert k in s


class TestReport:
    def test_build_report(self):
        results = [
            CertificationResult("s1", "n1", "FORM_SUBMIT", "app", OutcomeStatus.passed),
            CertificationResult("s2", "n2", "SEARCH", "app", OutcomeStatus.failed,
                                failure_category="criteria", failure_detail="x"),
        ]
        for r in results:
            reliability.record_workflow(WorkflowOutcome(r.scenario_id, r.category, r.website, r.passed, 10.0))
        rep = report.build_report(results, scenarios=scenarios.build_scenarios(), mode="mock")
        assert rep["scenarios_total"] == 2
        assert rep["supported_count"] == 1
        assert rep["unsupported_count"] == 1
        assert rep["pass_rate"] == 0.5
        assert rep["known_limitations"]   # scenarios declare some
        assert rep["recommendations"]
        md = report.render_markdown(rep)
        assert "Certification Report" in md and "Reliability" in md


class TestTrace:
    def test_no_trace_for_unknown(self):
        assert trace.has_trace("nope-exec") is False

    def test_semantic_snapshot_of_html(self):
        snap = trace.semantic_snapshot_of(fixtures.FIXTURES["/login"], title="login")
        assert snap is not None
        assert snap["page"]["type_counts"].get("FORM", 0) >= 1
