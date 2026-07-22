from __future__ import annotations

import re
import time
from typing import Any

from app.context_packet.models import PlannerPacket
from app.grounding.models import GroundingCandidate, GroundingResult
from app.schemas.response import SuggestedAction
from app.semantic_page.graph import SemanticPageGraph, SemanticTarget


_TOKEN_RE = re.compile(r"[a-z0-9]+")


class GroundingResolver:
    """Deterministic V3.2 intent-to-target resolver.

    The resolver produces replayable grounding decisions from already-built V3
    artifacts. It does not call the planner, inspect the browser, or mutate
    Planner Contract V2 actions.
    """

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.55,
        ambiguity_margin: float = 0.05,
        legacy_fallback: bool = True,
    ):
        self.confidence_threshold = confidence_threshold
        self.ambiguity_margin = ambiguity_margin
        self.legacy_fallback = legacy_fallback

    def resolve(
        self,
        *,
        run_id: str,
        action: SuggestedAction,
        graph: SemanticPageGraph,
        packet: PlannerPacket | None = None,
        cache_hit: bool = False,
    ) -> GroundingResult:
        started = time.perf_counter()
        intent = planner_intent(action)
        candidates = sorted(
            (
                _score_target(action, intent, target)
                for target in graph.targets
                if target.locator_candidates
            ),
            key=lambda item: (-item.confidence, item.target_id),
        )
        relevant = [
            candidate for candidate in candidates
            if candidate.confidence >= self.confidence_threshold
        ]

        if len(relevant) >= 2 and _is_ambiguous(relevant[0], relevant[1], self.ambiguity_margin):
            result = GroundingResult(
                run_id=run_id,
                status="ambiguous",
                planner_intent=intent,
                action_type=action.action_type,
                confidence=relevant[0].confidence,
                candidates=relevant[:5],
                ambiguity_reason="multiple_semantic_targets_with_similar_confidence",
                cache_hit=cache_hit,
            )
        elif relevant:
            selected = relevant[0]
            result = GroundingResult(
                run_id=run_id,
                status="resolved",
                planner_intent=intent,
                action_type=action.action_type,
                semantic_target_id=selected.target_id,
                selected_selector=selected.locator_candidates[0],
                confidence=selected.confidence,
                candidates=relevant[:5],
                cache_hit=cache_hit,
            )
        elif self.legacy_fallback and action.target_selector:
            result = GroundingResult(
                run_id=run_id,
                status="fallback",
                planner_intent=intent,
                action_type=action.action_type,
                selected_selector=action.target_selector,
                confidence=max(0.0, min(action.confidence, 1.0)),
                candidates=candidates[:5],
                fallback_used=True,
                fallback_reason="semantic_target_not_resolved_using_legacy_selector",
                cache_hit=cache_hit,
            )
        else:
            result = GroundingResult(
                run_id=run_id,
                status="not_found",
                planner_intent=intent,
                action_type=action.action_type,
                candidates=candidates[:5],
                fallback_reason="no_semantic_target_or_legacy_selector_available",
                cache_hit=cache_hit,
            )

        result.replay_metadata = _replay_metadata(
            graph=graph,
            packet=packet,
            candidate_count=len(candidates),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
        return result


def planner_intent(action: SuggestedAction) -> str:
    parts = [
        action.action_type,
        action.description,
        action.reasoning,
        action.value or "",
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _score_target(
    action: SuggestedAction,
    intent: str,
    target: SemanticTarget,
) -> GroundingCandidate:
    intent_tokens = set(_tokens(intent))
    target_text = f"{target.label} {target.semantic_role} {target.target_type}"
    target_tokens = set(_tokens(target_text))
    overlap = intent_tokens & target_tokens

    confidence = 0.0
    reasons: list[str] = []
    if overlap:
        confidence += min(0.45, len(overlap) / max(len(intent_tokens), 1))
        reasons.append("intent_label_overlap")
    if action.target_selector and action.target_selector in target.locator_candidates:
        confidence += 0.35
        reasons.append("legacy_selector_match")
    compatibility = _compatibility(action.action_type, target)
    if compatibility:
        confidence += compatibility
        reasons.append("action_target_compatible")
    if target.confidence:
        confidence += min(target.confidence, 1.0) * 0.15
        reasons.append("target_confidence")

    return GroundingCandidate(
        target_id=target.target_id,
        target_type=target.target_type,
        semantic_role=target.semantic_role,
        label=target.label,
        locator_candidates=list(target.locator_candidates),
        confidence=round(min(confidence, 1.0), 4),
        match_reasons=reasons,
    )


def _compatibility(action_type: str, target: SemanticTarget) -> float:
    role = target.semantic_role
    target_type = (target.target_type or "").lower()
    if action_type in {"click", "hover"} and (
        "control" in role or "link" in role or target_type in {"button", "a"}
    ):
        return 0.2
    if action_type in {"fill", "keyboard_shortcut"} and (
        "field" in role or target_type in {"input", "textarea"}
    ):
        return 0.2
    if action_type in {"select_option", "choose_date"} and (
        "select" in role or "field" in role or target_type == "select"
    ):
        return 0.2
    if action_type in {"open_new_tab", "switch_tab", "focus_existing_tab"} and "link" in role:
        return 0.15
    return 0.0


def _tokens(value: str) -> list[str]:
    return _TOKEN_RE.findall(value.lower())


def _is_ambiguous(
    first: GroundingCandidate,
    second: GroundingCandidate,
    margin: float,
) -> bool:
    return abs(first.confidence - second.confidence) <= margin


def _replay_metadata(
    *,
    graph: SemanticPageGraph,
    packet: PlannerPacket | None,
    candidate_count: int,
    elapsed_ms: int,
) -> dict[str, Any]:
    return {
        "graph_id": graph.graph_id,
        "observation_id": graph.observation_id,
        "semantic_graph_version": graph.schema_version,
        "planner_packet_version": packet.schema_version if packet else None,
        "target_count": len(graph.targets),
        "candidate_count": candidate_count,
        "elapsed_ms": elapsed_ms,
    }
