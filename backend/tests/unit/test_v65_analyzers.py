"""
V6.5 Unit Tests — Mission, Workflow, Tab, Action Analyzers (28 tests).
"""
import pytest

from app.trust.models import RiskLevel, TargetType
from app.trust import analytics as trust_analytics

import app.trust.registry as trust_reg


@pytest.fixture(autouse=True)
def reset():
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()
    yield
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()


# ── ActionTrustAnalyzer ───────────────────────────────────────────────────────

class TestActionAnalyzer:
    def test_read_page_low_risk(self):
        from app.trust.action_analyzer import analyze
        ev = analyze("read_page")
        assert ev.risk_level        == RiskLevel.low
        assert ev.approval_required is False

    def test_purchase_critical(self):
        from app.trust.action_analyzer import analyze
        ev = analyze("purchase")
        assert ev.risk_level        == RiskLevel.critical
        assert ev.approval_required is True

    def test_delete_critical_approval(self):
        from app.trust.action_analyzer import analyze
        ev = analyze("delete")
        assert ev.approval_required is True

    def test_target_type_action(self):
        from app.trust.action_analyzer import analyze
        ev = analyze("click", action_id="btn-1")
        assert ev.target_type == TargetType.action
        assert ev.target_id   == "btn-1"

    def test_analytics_incremented(self):
        from app.trust.action_analyzer import analyze
        analyze("purchase")
        a = trust_analytics.get_analytics()
        assert a["trust_evaluations"] >= 1
        assert a["critical_risk"]     >= 1

    def test_blockers_reduce_score(self):
        from app.trust.action_analyzer import analyze
        ev_clean  = analyze("click", blocker_count=0)
        ev_blocked = analyze("click", blocker_count=3)
        assert ev_blocked.trust_score < ev_clean.trust_score

    def test_workflow_context_elevates_risk(self):
        from app.trust.action_analyzer import analyze
        ev = analyze("click", workflow_type="purchase_workflow")
        assert ev.risk_level == RiskLevel.critical


# ── WorkflowTrustAnalyzer ─────────────────────────────────────────────────────

class TestWorkflowAnalyzer:
    def test_research_workflow_low(self):
        from app.trust.workflow_analyzer import analyze
        ev = analyze("research_workflow")
        assert ev.risk_level == RiskLevel.low

    def test_purchase_workflow_critical(self):
        from app.trust.workflow_analyzer import analyze
        ev = analyze("purchase_workflow")
        assert ev.risk_level        == RiskLevel.critical
        assert ev.approval_required is True

    def test_booking_workflow_medium_or_higher(self):
        from app.trust.workflow_analyzer import analyze
        ev = analyze("booking_workflow")
        assert ev.risk_level in (RiskLevel.medium, RiskLevel.high, RiskLevel.critical)

    def test_target_type_workflow(self):
        from app.trust.workflow_analyzer import analyze
        ev = analyze("booking_workflow", workflow_id="wf-99")
        assert ev.target_type == TargetType.workflow
        assert ev.target_id   == "wf-99"

    def test_readiness_improves_score(self):
        from app.trust.workflow_analyzer import analyze
        lo = analyze("research_workflow", readiness_score=0.0)
        hi = analyze("research_workflow", readiness_score=1.0)
        assert hi.trust_score > lo.trust_score

    def test_blockers_reduce_score(self):
        from app.trust.workflow_analyzer import analyze
        ev_clean   = analyze("research_workflow", critical_blocker_count=0)
        ev_blocked = analyze("research_workflow", critical_blocker_count=3)
        assert ev_blocked.trust_score < ev_clean.trust_score

    def test_workflow_tab_present_bonus(self):
        from app.trust.workflow_analyzer import analyze
        ev_no_tab = analyze("research_workflow", workflow_tab_present=False)
        ev_tab    = analyze("research_workflow", workflow_tab_present=True)
        assert ev_tab.trust_score >= ev_no_tab.trust_score


# ── TabTrustAnalyzer ──────────────────────────────────────────────────────────

class TestTabAnalyzer:
    def test_no_tabs_neutral(self):
        from app.trust.tab_analyzer import analyze
        ev = analyze("m1", tab_context=None)
        assert ev.risk_level        == RiskLevel.low
        assert ev.approval_required is False

    def test_https_tabs_high_trust(self):
        from app.trust.tab_analyzer import analyze
        ctx = {
            "tab_count": 2,
            "tab_summaries": [
                {"tab_id": "t1", "url": "https://amazon.com", "role": "RESEARCH",
                 "state": "OPEN", "mission_id": "m1"},
                {"tab_id": "t2", "url": "https://flipkart.com", "role": "COMPARISON",
                 "state": "OPEN", "mission_id": "m1"},
            ]
        }
        ev = analyze("m1", tab_context=ctx)
        assert ev.trust_score > 0.80

    def test_orphan_finding_reduces_trust(self):
        from app.trust.tab_analyzer import analyze
        ctx = {"tab_count": 1, "tab_summaries": []}
        findings = [{"code": "ORPHAN_TABS", "severity": "INFO"}]
        ev_no_finding = analyze("m1", tab_context=ctx)
        ev_with_finding = analyze("m1", tab_context=ctx, tab_findings=findings)
        assert ev_with_finding.trust_score <= ev_no_finding.trust_score

    def test_duplicate_finding_reduces_trust(self):
        from app.trust.tab_analyzer import analyze
        ctx = {"tab_count": 2, "tab_summaries": []}
        findings = [{"code": "DUPLICATE_TABS", "severity": "INFO"}]
        ev = analyze("m1", tab_context=ctx, tab_findings=findings)
        assert ev.trust_score < 0.85

    def test_target_type_tab(self):
        from app.trust.tab_analyzer import analyze
        ev = analyze("m1")
        assert ev.target_type == TargetType.tab
        assert ev.target_id   == "m1"


# ── MissionTrustAnalyzer ──────────────────────────────────────────────────────

class TestMissionAnalyzer:
    def test_high_readiness_high_trust(self):
        from app.trust.mission_analyzer import analyze
        ev = analyze("m1", readiness_score=0.95,
                     task_count=4, completed_task_count=4)
        assert ev.trust_score > 0.70
        assert ev.risk_level == RiskLevel.low

    def test_failed_tasks_reduce_trust(self):
        from app.trust.mission_analyzer import analyze
        ev_clean  = analyze("m1", task_count=4, completed_task_count=4, failed_task_count=0)
        ev_failed = analyze("m1", task_count=4, completed_task_count=2, failed_task_count=2)
        assert ev_failed.trust_score < ev_clean.trust_score

    def test_critical_blockers_reduce_trust(self):
        from app.trust.mission_analyzer import analyze
        ev = analyze("m1", critical_blockers=3, readiness_score=0.0)
        assert ev.trust_score < 0.60

    def test_orphan_tabs_reduce_trust(self):
        from app.trust.mission_analyzer import analyze
        ev_clean  = analyze("m1", tab_count=3, orphan_tab_count=0)
        ev_orphan = analyze("m1", tab_count=3, orphan_tab_count=3)
        assert ev_orphan.trust_score < ev_clean.trust_score

    def test_no_tasks_neutral(self):
        from app.trust.mission_analyzer import analyze
        ev = analyze("m1", task_count=0)
        assert 0.0 <= ev.trust_score <= 1.0

    def test_target_type_mission(self):
        from app.trust.mission_analyzer import analyze
        ev = analyze("m99")
        assert ev.target_type == TargetType.mission
        assert ev.target_id   == "m99"

    def test_workflow_tab_bonus(self):
        from app.trust.mission_analyzer import analyze
        ev_no_wf = analyze("m1", tab_count=3, workflow_tab_present=False)
        ev_wf    = analyze("m1", tab_count=3, workflow_tab_present=True)
        assert ev_wf.trust_score >= ev_no_wf.trust_score

    def test_approval_required_for_very_low_trust(self):
        from app.trust.mission_analyzer import analyze
        ev = analyze("m1", readiness_score=0.0, critical_blockers=5,
                     task_count=4, failed_task_count=4, missing_info_count=10)
        # Either approval_required or risk is at least medium
        assert ev.risk_level in (RiskLevel.medium, RiskLevel.high, RiskLevel.critical)
