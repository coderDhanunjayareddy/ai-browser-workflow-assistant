"""
V6.0 Unit Tests — TabIntelligenceAnalyzer (18 tests).
"""
import pytest
from datetime import datetime, timedelta

from app.tabs.intelligence import TabIntelligenceAnalyzer, analyze, TabFindingSeverity
from app.tabs.context import TabContext
from app.tabs import analytics as tab_analytics


@pytest.fixture(autouse=True)
def reset():
    tab_analytics._reset_for_testing()
    yield


def _ctx(
    mission_id="m1",
    tab_summaries=None,
    workflow_tab=False,
    comparison_tab=False,
    research_tab=False,
    duplicate_urls=None,
    active_tab_count=0,
):
    summaries = tab_summaries or []
    return TabContext(
        mission_id             = mission_id,
        tab_count              = len(summaries),
        active_tab_count       = active_tab_count,
        tab_summaries          = summaries,
        roles_present          = list({t["role"] for t in summaries}),
        primary_tab            = None,
        active_tab             = None,
        workflow_tab_present   = workflow_tab,
        comparison_tab_present = comparison_tab,
        research_tab_present   = research_tab,
        duplicate_urls         = duplicate_urls or [],
        latency_ms             = 0,
    )


def _ts(tab_id, role="RESEARCH", url=None, state="OPEN", mission_id="m1",
        updated_at=None):
    return {
        "tab_id":     tab_id,
        "url":        url or f"https://{tab_id}.com",
        "title":      tab_id,
        "role":       role,
        "state":      state,
        "mission_id": mission_id,
        "task_id":    None,
        "updated_at": (updated_at or datetime.utcnow()).isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }


class TestNoFindings:
    def test_empty_tabs_no_findings(self):
        ctx = _ctx()
        result = analyze(ctx)
        assert result.findings == []
        assert result.has_issues is False

    def test_single_research_tab_no_issues(self):
        ctx = _ctx(tab_summaries=[_ts("t1", "RESEARCH")], research_tab=True)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "MISSING_COMPARISON_TAB" not in codes


class TestMissingComparisonTab:
    def test_two_research_no_comparison_fires(self):
        summaries = [_ts("t1", "RESEARCH"), _ts("t2", "RESEARCH")]
        ctx = _ctx(tab_summaries=summaries, research_tab=True)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "MISSING_COMPARISON_TAB" in codes

    def test_one_research_no_comparison_no_finding(self):
        summaries = [_ts("t1", "RESEARCH")]
        ctx = _ctx(tab_summaries=summaries, research_tab=True)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "MISSING_COMPARISON_TAB" not in codes

    def test_two_research_with_comparison_no_finding(self):
        summaries = [
            _ts("t1", "RESEARCH"),
            _ts("t2", "RESEARCH"),
            _ts("t3", "COMPARISON"),
        ]
        ctx = _ctx(tab_summaries=summaries, research_tab=True, comparison_tab=True)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "MISSING_COMPARISON_TAB" not in codes

    def test_finding_severity_is_warning(self):
        summaries = [_ts("t1", "RESEARCH"), _ts("t2", "RESEARCH")]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        f = next(f for f in result.findings if f.code == "MISSING_COMPARISON_TAB")
        assert f.severity == TabFindingSeverity.warning


class TestMissingWorkflowTab:
    def test_high_readiness_no_workflow_fires(self):
        summaries = [_ts("t1", "RESEARCH")]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx, readiness_score=0.85)
        codes = {f.code for f in result.findings}
        assert "MISSING_WORKFLOW_TAB" in codes

    def test_low_readiness_no_workflow_no_finding(self):
        summaries = [_ts("t1", "RESEARCH")]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx, readiness_score=0.50)
        codes = {f.code for f in result.findings}
        assert "MISSING_WORKFLOW_TAB" not in codes

    def test_workflow_tab_present_no_finding(self):
        summaries = [_ts("t1", "WORKFLOW")]
        ctx = _ctx(tab_summaries=summaries, workflow_tab=True)
        result = analyze(ctx, readiness_score=0.90)
        codes = {f.code for f in result.findings}
        assert "MISSING_WORKFLOW_TAB" not in codes

    def test_empty_tabs_no_missing_workflow(self):
        ctx = _ctx()
        result = analyze(ctx, readiness_score=0.90)
        codes = {f.code for f in result.findings}
        assert "MISSING_WORKFLOW_TAB" not in codes


class TestDuplicateTabs:
    def test_duplicate_url_detected(self):
        summaries = [
            _ts("t1", url="https://amazon.com"),
            _ts("t2", url="https://amazon.com"),
        ]
        ctx = _ctx(tab_summaries=summaries, duplicate_urls=["https://amazon.com"])
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "DUPLICATE_TABS" in codes

    def test_no_duplicates_no_finding(self):
        summaries = [_ts("t1"), _ts("t2")]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "DUPLICATE_TABS" not in codes


class TestStaleTabs:
    def test_stale_background_tab_detected(self):
        old_time = datetime.utcnow() - timedelta(minutes=35)
        summaries = [_ts("t1", state="BACKGROUND", updated_at=old_time)]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "STALE_TABS" in codes

    def test_fresh_background_tab_not_stale(self):
        summaries = [_ts("t1", state="BACKGROUND")]  # just now
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "STALE_TABS" not in codes


class TestOrphanTabs:
    def test_tab_without_mission_is_orphan(self):
        summaries = [
            {**_ts("t1"), "mission_id": None},
        ]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "ORPHAN_TABS" in codes

    def test_tab_with_mission_not_orphan(self):
        summaries = [_ts("t1", mission_id="m1")]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        codes = {f.code for f in result.findings}
        assert "ORPHAN_TABS" not in codes


class TestRecommendations:
    def test_recommendations_generated_for_findings(self):
        summaries = [_ts("t1", "RESEARCH"), _ts("t2", "RESEARCH")]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        assert len(result.recommendations) > 0

    def test_to_dict_serializable(self):
        summaries = [_ts("t1")]
        ctx = _ctx(tab_summaries=summaries)
        result = analyze(ctx)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "findings" in d
        assert "recommendations" in d
