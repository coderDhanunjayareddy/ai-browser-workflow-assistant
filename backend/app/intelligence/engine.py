"""
V4.0 Intelligence Engine — orchestrates all 7 components into one pipeline call.

Pipeline (all deterministic, < 1 ms total):
  1. ExecutionOpportunityDetector  → ExecutionOpportunity
  2. GoalDecomposer                → GoalTree
  3. WorkflowReadinessAnalyzer     → WorkflowReadiness
  4. ApprovalPolicyAdvisor         → ApprovalLevel
  5. ExecutionPlanBuilder          → ExecutionPlan
  6. WorkflowRecommendationEngine  → list[WorkflowRecommendation]
  7. WorkflowBootstrapGenerator    → BootstrapFacts

When no execution opportunity is detected (pure research):
  - GoalTree, ReadinessAnalysis, ExecutionPlan, BootstrapFacts are all None
  - recommendations is []
  - latency overhead approaches 0

Safety:
  - This engine ONLY prepares execution context.
  - It does NOT launch workflows, click buttons, or make any network calls.
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from app.intelligence.models import (
    ApprovalLevel,
    IntelligenceResult,
)
from app.intelligence.opportunity_detector import detector
from app.intelligence.goal_decomposer import decomposer
from app.intelligence.readiness_analyzer import analyzer
from app.intelligence.approval_advisor import advisor
from app.intelligence.plan_builder import builder
from app.intelligence.recommendation_engine import engine as rec_engine
from app.intelligence.bootstrap_generator import generator
from app.intelligence import analytics

logger = logging.getLogger(__name__)


def run_intelligence(
    query: str,
    topic: str,
    research_summary: str,
    cognitive_session=None,
) -> IntelligenceResult:
    """
    Run the full intelligence pipeline for a given research query.

    Args:
        query: original user message
        topic: research topic extracted by ResearchPlanner
        research_summary: executive summary from ResearchReport (or "")
        cognitive_session: CognitiveSession (may be None in tests)

    Returns:
        IntelligenceResult with all component outputs populated.
    """
    t0 = time.monotonic()

    try:
        # 1. Detect execution opportunity
        opportunity = detector.detect(query, cognitive_session)

        if not opportunity.detected:
            analytics.record_research_only()
            latency_ms = int((time.monotonic() - t0) * 1000)
            return IntelligenceResult(
                opportunity=opportunity,
                goal_tree=None,
                readiness=None,
                execution_plan=None,
                recommendations=[],
                bootstrap_facts=None,
                latency_ms=latency_ms,
            )

        analytics.record_opportunity_detected()

        # 2. Decompose goal into tree
        goal_tree = decomposer.decompose(topic, opportunity)

        # 3. Analyze workflow readiness
        readiness = analyzer.analyze(opportunity, goal_tree, cognitive_session)
        analytics.record_readiness(readiness.state.value)

        # 4. Classify approval level
        approval_level: ApprovalLevel = advisor.classify(opportunity, query)
        analytics.record_approval(approval_level.value)

        # 5. Build execution plan
        execution_plan = builder.build(
            query=query,
            topic=topic,
            opportunity=opportunity,
            readiness=readiness,
            approval_level=approval_level,
            goal_tree=goal_tree,
            cognitive_session=cognitive_session,
        )
        analytics.record_plan_built()

        # 6. Generate recommendations
        recommendations = rec_engine.generate(execution_plan, readiness)
        analytics.record_recommendations(len(recommendations))

        # 7. Build bootstrap facts
        bootstrap_facts = generator.generate(
            query=query,
            execution_plan=execution_plan,
            research_topic=topic,
            research_summary=research_summary,
            cognitive_session=cognitive_session,
        )
        analytics.record_bootstrap_generated()

        latency_ms = int((time.monotonic() - t0) * 1000)
        return IntelligenceResult(
            opportunity=opportunity,
            goal_tree=goal_tree,
            readiness=readiness,
            execution_plan=execution_plan,
            recommendations=recommendations,
            bootstrap_facts=bootstrap_facts,
            latency_ms=latency_ms,
        )

    except Exception as exc:
        logger.error("Intelligence engine failed for %r: %s", query, exc)
        latency_ms = int((time.monotonic() - t0) * 1000)
        # Return a safe stub so the research response is never blocked
        from app.intelligence.opportunity_detector import detector as _det
        stub_opportunity = _det.detect(query)
        stub_opportunity.detected = False
        return IntelligenceResult(
            opportunity=stub_opportunity,
            goal_tree=None,
            readiness=None,
            execution_plan=None,
            recommendations=[],
            bootstrap_facts=None,
            latency_ms=latency_ms,
        )
