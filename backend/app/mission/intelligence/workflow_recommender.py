"""
V5.5 Mission Intelligence — WorkflowRecommendationEngine.

Determines which workflow type should be launched for a mission.

Strategy:
  1. Detect action intent from mission title + objective (reuses opportunity_detector)
  2. Map detected ActionType → workflow_type string (reuses plan_builder map)
  3. Compute confidence from readiness_score and detection confidence
  4. Return MissionWorkflowRecommendation (advisory only)

No LLM. No DB. No execution. Pure deterministic logic.
"""
from __future__ import annotations

from typing import Optional

from app.intelligence.models import ActionType
from app.intelligence.opportunity_detector import detector, _WORKFLOW_CANDIDATES
from app.mission.intelligence.models import MissionWorkflowRecommendation

# Reuse plan_builder's ActionType → workflow_type map
_WORKFLOW_TYPE_MAP: dict[ActionType, str] = {
    ActionType.book:        "booking_workflow",
    ActionType.purchase:    "purchase_workflow",
    ActionType.register:    "registration_workflow",
    ActionType.schedule:    "scheduling_workflow",
    ActionType.download:    "download_workflow",
    ActionType.communicate: "communication_workflow",
    ActionType.navigate:    "navigation_workflow",
    ActionType.rent:        "rental_workflow",
    ActionType.apply:       "application_workflow",
    ActionType.search:      "search_workflow",
    ActionType.unknown:     "generic_workflow",
}

# Human-readable reasoning templates
_REASONING: dict[ActionType, str] = {
    ActionType.book:        "Mission intent is booking/reservation. Use booking workflow to complete.",
    ActionType.purchase:    "Mission intent is purchasing a product. Use purchase workflow.",
    ActionType.register:    "Mission intent is account registration. Use registration workflow.",
    ActionType.schedule:    "Mission intent involves scheduling. Use scheduling workflow.",
    ActionType.download:    "Mission intent is downloading/installing. Use download workflow.",
    ActionType.communicate: "Mission intent is communication. Use communication workflow.",
    ActionType.navigate:    "Mission intent is navigation. Use navigation workflow.",
    ActionType.rent:        "Mission intent is renting. Use rental workflow.",
    ActionType.apply:       "Mission intent is applying for something. Use application workflow.",
    ActionType.search:      "Mission intent is research/search. Use search workflow.",
    ActionType.unknown:     "Mission intent could not be classified. Generic workflow recommended.",
}


def recommend(
    mission_title: str,
    mission_objective: str,
    readiness_score: float,
) -> Optional[MissionWorkflowRecommendation]:
    """
    Recommend a workflow for the given mission.

    Returns None if the mission intent cannot be classified or readiness is too low.
    Confidence is jointly determined by detection confidence and readiness_score.
    """
    combined_text = f"{mission_title} {mission_objective}".strip()
    if not combined_text:
        return None

    opportunity = detector.detect(combined_text, cognitive_session=None)

    # Only recommend a workflow if there's a detectable action
    if not opportunity.detected and opportunity.action_type == ActionType.unknown:
        return None

    workflow_type = _WORKFLOW_TYPE_MAP.get(opportunity.action_type, "generic_workflow")
    action_type   = opportunity.action_type.value

    # Confidence = average of detection confidence (0.9 or 0.0) and readiness_score
    raw_confidence = (opportunity.confidence + readiness_score) / 2.0
    confidence     = round(min(1.0, raw_confidence), 3)

    reasoning = _REASONING.get(opportunity.action_type, "Workflow selected by action type.")

    return MissionWorkflowRecommendation(
        workflow_type=workflow_type,
        action_type=action_type,
        confidence=confidence,
        reasoning=reasoning,
    )
