import logging
import json
import hashlib
import re
import time
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.extraction_v2.grounded_registry import GroundedElementRegistry
from app.models.db import WorkflowEvent, WorkflowSession
from app.replay.timeline_service import TimelineService
from app.state_engine.persistence import StatePersistence
from app.budget_engine import BudgetManager
from app.budget_engine.budget_enforcer import enforce_budget
from app.budget_engine.budget_models import BudgetCheckpoint
from app.context_compression import ContextCompressor
from app.services.analytics_service import record_planner_call
from app.run_ledger import RunLedgerWriter
from app.observability.tracing import record_structured_trace
from app.observability.metrics import default_metric_sink
from app.feature_flags import is_active, is_shadow_or_active
from app.context_packet import ContextPacketBuilder, PlannerV2Adapter
from app.context_packet.telemetry import record_packet_metrics
from app.diagnostics.console import diagnostic_terminal_enabled, safe_print
from app.evaluation import EvaluationEngine
from app.grounding import GroundingCache, GroundingResolver
from app.grounding.telemetry import record_grounding_metrics
from app.mission.v3 import MissionIntelligenceEngine
from app.policy import GovernanceDecisionEngine
from app.run_ledger.reader import RunLedgerReader
from app.schemas.response import AnalyzeResponse, ReportOutcome
from app.semantic_page.cache import SemanticGraphCache
from app.semantic_page.telemetry import record_graph_metrics
from app.verification import ValidationEngine

logger = logging.getLogger(__name__)

_semantic_graph_cache = SemanticGraphCache()
_context_packet_builder = ContextPacketBuilder()
_planner_v2_adapter = PlannerV2Adapter()
_grounding_resolver = GroundingResolver()
_grounding_cache = GroundingCache()
_mission_intelligence = MissionIntelligenceEngine()
_validation_engine = ValidationEngine()
_governance_engine = GovernanceDecisionEngine()
_evaluation_engine = EvaluationEngine()
_browser_intelligence_artifacts: dict[str, Any] = {}


class WorkflowOrchestrator:
    """Domain-neutral coordination for one browser-assistant session."""

    def __init__(self, session_id: str, db: Session):
        self.session_id = session_id
        self.db = db
        self.state_persistence = StatePersistence(db)
        self.timeline_service = TimelineService(session_id)
        self.budget_manager = BudgetManager(db, session_id)
        self.context_compressor = ContextCompressor()
        self.v3_ledger = RunLedgerWriter(db)

    def _record_v3_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        step_index: int = 0,
        links: dict[str, Any] | None = None,
    ) -> None:
        """Best-effort V3.0 trace parity hook.

        This is write-only foundation infrastructure. It must never change
        production workflow behavior or raise into the orchestration path.
        """
        try:
            event = self.v3_ledger.append(
                run_id=self.session_id,
                event_type=event_type,
                payload=payload or {},
                step_index=step_index,
                links=links or {},
            )
            trace_event = record_structured_trace(
                run_id=self.session_id,
                event_type=event_type,
                payload=payload or {},
                ledger_event_id=event.event_id if event else None,
            )
            if event is not None or trace_event is not None:
                default_metric_sink.record(
                    "v3.workflow_event",
                    1,
                    run_id=self.session_id,
                    tags={"event_type": event_type},
                )
            self._update_mission_intelligence_shadow(
                event_type=event_type,
                payload=payload or {},
                step_index=step_index,
                source_event_id=event.event_id if event else None,
            )
        except Exception:
            logger.debug("V3 event recording skipped for %s", event_type, exc_info=True)

    def _update_mission_intelligence_shadow(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        step_index: int,
        source_event_id: str | None,
    ) -> None:
        """Update V3.3 Mission Intelligence from workflow events in shadow mode."""
        if event_type == "mission.updated" or not is_shadow_or_active("V3_MISSION_INTELLIGENCE"):
            return
        try:
            snapshot, transition_ms = _mission_intelligence.apply_workflow_event(
                run_id=self.session_id,
                event_type=event_type,
                payload=payload,
                event_id=source_event_id,
                step_index=step_index,
            )
            mission_event = self.v3_ledger.append(
                run_id=self.session_id,
                event_type="mission.updated",
                payload={
                    "schema_version": snapshot.schema_version,
                    "mission_id": snapshot.mission_id,
                    "state": snapshot.state,
                    "mode": snapshot.mode,
                    "goal": snapshot.goal,
                    "current_objective": snapshot.current_objective,
                    "completed_objectives": snapshot.completed_objectives,
                    "remaining_objectives": snapshot.remaining_objectives,
                    "blocked_objectives": snapshot.blocked_objectives,
                    "progress_summary": snapshot.progress_summary,
                    "recent_attempts": [
                        attempt.model_dump(mode="json")
                        for attempt in snapshot.attempts[-5:]
                    ],
                    "replanning_requested": snapshot.replanning_requested,
                    "replan_reasons": snapshot.replan_reasons,
                    "paused": snapshot.paused,
                    "planner_iterations": snapshot.planner_iterations,
                    "retry_count": snapshot.retry_count,
                    "recovery_count": snapshot.recovery_count,
                    "completed_steps": snapshot.completed_steps,
                    "next_expected_action": snapshot.next_expected_action,
                    "transition_ms": transition_ms,
                },
                step_index=step_index,
                producer="backend.mission_intelligence",
                links={"source_event_id": source_event_id} if source_event_id else {},
            )
            record_structured_trace(
                run_id=self.session_id,
                event_type="mission.updated",
                payload={
                    "state": snapshot.state,
                    "mode": snapshot.mode,
                    "replanning_requested": snapshot.replanning_requested,
                    "planner_iterations": snapshot.planner_iterations,
                },
                ledger_event_id=mission_event.event_id if mission_event else None,
            )
        except Exception:
            logger.debug("V3 mission intelligence shadow update skipped", exc_info=True)

    def _build_semantic_graph_shadow(self, page_context: Any) -> None:
        """Build V3.1A Semantic Page Graph in shadow mode only.

        The graph is infrastructure telemetry. It is not included in planner
        context and cannot affect planner, workflow, or execution behavior.
        """
        if not is_shadow_or_active("V3_SEMANTIC_GRAPH"):
            return
        try:
            result = _semantic_graph_cache.get_or_build(page_context)
            graph = result.graph
            record_graph_metrics(
                self.session_id,
                result,
                hit_ratio=_semantic_graph_cache.hit_ratio(),
                cache_size=_semantic_graph_cache.size(),
            )
            self._record_v3_event(
                "semantic_graph.built",
                {
                    "graph_id": graph.graph_id,
                    "observation_id": graph.observation_id,
                    "schema_version": graph.schema_version,
                    "builder_version": graph.builder_version,
                    "page_type": graph.page_type,
                    "node_count": len(graph.nodes),
                    "edge_count": len(graph.edges),
                    "fact_count": len(graph.facts),
                    "target_count": len(graph.targets),
                    "input_hash": graph.metadata.get("input_hash"),
                    "cache_hit": result.cache_hit,
                    "build_ms": result.build_ms,
                },
            )
        except Exception:
            logger.debug("V3 semantic graph shadow build skipped", exc_info=True)

    def _build_browser_intelligence_shadow(self, page_context: Any) -> Any | None:
        """Build V4.5 Browser Intelligence artifacts without changing behavior.

        Active mode may reuse this artifact to enrich compressed planner context,
        but the planner action contract remains Planner Contract V2.
        """
        live_path_trace = diagnostic_terminal_enabled("AI_BROWSER_LIVE_PATH_TRACE")
        if live_path_trace:
            safe_print(
                "[V4.5.1 live-path] ORCHESTRATOR_BEFORE_BROWSER_INTELLIGENCE "
                + json.dumps(
                    {
                        "session_id": self.session_id,
                        "v45_browser_intelligence": "enabled" if is_shadow_or_active("V45_BROWSER_INTELLIGENCE") else "disabled",
                        "url": str(getattr(page_context, "url", "") or ""),
                        "interactive_count": len(getattr(page_context, "interactive_elements", []) or []),
                        "content_block_count": len(getattr(page_context, "content_blocks", []) or []),
                        "metadata_keys": list((getattr(page_context, "metadata", {}) or {}).keys()),
                        "has_semantic_entities_attr": hasattr(page_context, "semantic_entities"),
                        "first_content_blocks": [
                            {
                                "text": str(getattr(block, "text", "") or "")[:120],
                                "href": getattr(block, "href", None),
                                "selector": getattr(block, "selector", None),
                            }
                            for block in list(getattr(page_context, "content_blocks", []) or [])[:6]
                        ],
                    },
                    ensure_ascii=True,
                )
            )
        if not is_shadow_or_active("V45_BROWSER_INTELLIGENCE"):
            if live_path_trace:
                safe_print(
                    "[V4.5.1 live-path] ORCHESTRATOR_BROWSER_INTELLIGENCE_NOT_EXECUTED "
                    + json.dumps({"session_id": self.session_id, "reason": "V45_BROWSER_INTELLIGENCE is off"})
                )
            return None
        try:
            from app.browser_intelligence import build_browser_intelligence

            artifact = build_browser_intelligence(page_context, scope_id=self.session_id)
            _browser_intelligence_artifacts[self.session_id] = artifact
            if live_path_trace:
                safe_print(
                    "[V4.5.1 live-path] ORCHESTRATOR_BROWSER_INTELLIGENCE_EXECUTED "
                    + json.dumps(
                        {
                            "session_id": self.session_id,
                            "adapter": artifact.page_model.adapter,
                            "semantic_element_count": len(artifact.page_model.elements),
                            "search_result_count": len(artifact.page_model.search_results),
                            "semantic_elements": [
                                {
                                    "kind": element.kind,
                                    "label": element.label[:120],
                                    "href": element.href,
                                    "selector_id": element.selector_id,
                                    "confidence": element.confidence,
                                }
                                for element in artifact.page_model.elements[:12]
                            ],
                            "search_results": [
                                {
                                    "rank": result.rank,
                                    "title": result.title[:120],
                                    "url": result.url,
                                    "selector_id": result.selector_id,
                                }
                                for result in artifact.page_model.search_results[:12]
                            ],
                        },
                        ensure_ascii=True,
                    )
                )
            payload = {
                "schema_version": artifact.page_model.schema_version,
                "url": artifact.page_model.url,
                "title": artifact.page_model.title,
                "page_type": artifact.page_model.classification.page_type,
                "classification_confidence": artifact.page_model.classification.confidence,
                "adapter": artifact.page_model.adapter,
                "semantic_element_count": len(artifact.page_model.elements),
                "search_result_count": len(artifact.page_model.search_results),
                "selector_candidate_count": len(artifact.page_model.selector_candidates),
                "telemetry": artifact.capability_report.get("telemetry", {}),
                "replay_schema_version": artifact.replay.get("schema_version"),
            }
            self._record_v3_event(
                "browser_intelligence.built",
                payload,
                links={"page_model_schema": artifact.page_model.schema_version},
            )
            return artifact
        except Exception:
            logger.debug("V4.5 browser intelligence shadow build skipped", exc_info=True)
            return None

    def _build_context_packet_shadow(
        self,
        *,
        task: str,
        page_context: Any,
        prior_steps: list,
        supplemental_context: str,
        verified_state: dict[str, Any],
        compressed_context: dict[str, Any],
    ) -> None:
        """Build V3.1B Context Packet without changing planner execution."""
        if not (
            is_shadow_or_active("V3_CONTEXT_PACKET")
            and is_shadow_or_active("V3_SEMANTIC_GRAPH")
        ):
            return
        try:
            graph_result = _semantic_graph_cache.get_or_build(page_context)
            packet, build_ms = _context_packet_builder.build(
                run_id=self.session_id,
                task=task,
                page_context=page_context,
                semantic_graph=graph_result.graph,
                prior_steps=prior_steps,
                supplemental_context=supplemental_context,
                verified_facts=verified_state,
                compressed_context=compressed_context,
            )
            legacy_inputs = _planner_v2_adapter.to_legacy_inputs(
                packet=packet,
                task=task,
                page_context=page_context,
                prior_steps=prior_steps,
                supplemental_context="",
                verified_state=verified_state,
                compressed_context=compressed_context,
            )
            record_packet_metrics(self.session_id, packet, build_ms=build_ms)
            self._record_v3_event(
                "planner.packet_built",
                {
                    "schema_version": packet.schema_version,
                    "output_contract": packet.output_contract,
                    "semantic_graph_id": packet.run.get("semantic_graph_id"),
                    "packet_chars": packet.budget_metadata.packet_chars,
                    "original_counts": packet.budget_metadata.original_counts,
                    "trimmed_counts": packet.budget_metadata.trimmed_counts,
                    "build_ms": build_ms,
                    "adapter_output_contract": legacy_inputs.get("output_contract"),
                },
            )
        except Exception:
            logger.debug("V3 context packet shadow build skipped", exc_info=True)

    def _ground_intents_shadow(
        self,
        *,
        task: str,
        page_context: Any,
        prior_steps: list,
        supplemental_context: str,
        verified_state: dict[str, Any],
        compressed_context: dict[str, Any],
        planner_response: Any,
    ) -> None:
        """Resolve planner intents in V3.2 shadow mode without changing actions."""
        if not (
            is_shadow_or_active("V3_INTENT_GROUNDING")
            and is_shadow_or_active("V3_SEMANTIC_GRAPH")
            and is_shadow_or_active("V3_CONTEXT_PACKET")
        ):
            return
        if not getattr(planner_response, "suggested_actions", None):
            return
        try:
            graph_result = _semantic_graph_cache.get_or_build(page_context)
            packet, _build_ms = _context_packet_builder.build(
                run_id=self.session_id,
                task=task,
                page_context=page_context,
                semantic_graph=graph_result.graph,
                prior_steps=prior_steps,
                supplemental_context=supplemental_context,
                verified_facts=verified_state,
                compressed_context=compressed_context,
            )
            for action in planner_response.suggested_actions:
                cache_result = _grounding_cache.get_or_resolve(
                    run_id=self.session_id,
                    action=action,
                    graph=graph_result.graph,
                    packet=packet,
                    resolver=_grounding_resolver,
                )
                record_grounding_metrics(
                    self.session_id,
                    cache_result,
                    hit_ratio=_grounding_cache.hit_ratio(),
                    cache_size=_grounding_cache.size(),
                )
                grounding = cache_result.result
                self._record_v3_event(
                    "grounding.resolved",
                    {
                        "schema_version": grounding.schema_version,
                        "status": grounding.status,
                        "action_id": action.action_id,
                        "action_type": action.action_type,
                        "semantic_target_id": grounding.semantic_target_id,
                        "selected_selector": grounding.selected_selector,
                        "confidence": grounding.confidence,
                        "candidate_count": len(grounding.candidates),
                        "fallback_used": grounding.fallback_used,
                        "fallback_reason": grounding.fallback_reason,
                        "ambiguity_reason": grounding.ambiguity_reason,
                        "cache_hit": cache_result.cache_hit,
                        "semantic_graph_id": graph_result.graph.graph_id,
                        "planner_packet_version": packet.schema_version,
                    },
                )
        except Exception:
            logger.debug("V3 intent grounding shadow resolution skipped", exc_info=True)

    def _record_validation_shadow(self, validation: Any, latency_ms: int) -> None:
        if not is_shadow_or_active("V3_VALIDATION"):
            return
        try:
            event = self.v3_ledger.append(
                run_id=self.session_id,
                event_type="validation.completed",
                payload={
                    "schema_version": validation.schema_version,
                    "validation_id": validation.validation_id,
                    "mission_id": validation.mission_id,
                    "step_id": validation.step_id,
                    "expected_outcome": validation.expected_outcome,
                    "observed_outcome": validation.observed_outcome,
                    "validation_status": validation.validation_status,
                    "confidence": validation.confidence,
                    "failure_category": validation.failure_category,
                    "required_evidence": validation.required_evidence,
                    "observed_evidence": validation.observed_evidence,
                    "missing_evidence": validation.missing_evidence,
                    "contradictions": validation.contradictions,
                    "evidence_count": len(validation.evidence),
                    "latency_ms": latency_ms,
                    "replay_metadata": validation.replay_metadata,
                },
                producer="backend.validation",
            )
            record_structured_trace(
                run_id=self.session_id,
                event_type="validation.completed",
                payload={
                    "validation_id": validation.validation_id,
                    "validation_status": validation.validation_status,
                    "failure_category": validation.failure_category,
                    "confidence": validation.confidence,
                },
                ledger_event_id=event.event_id if event else None,
            )
            self._update_mission_intelligence_shadow(
                event_type="validation.completed",
                payload={
                    "validation_status": validation.validation_status,
                    "failure_category": validation.failure_category,
                    "confidence": validation.confidence,
                },
                step_index=0,
                source_event_id=event.event_id if event else None,
            )
        except Exception:
            logger.debug("V3 validation shadow recording skipped", exc_info=True)

    def _evaluate_governance_shadow(self, planner_response: Any) -> None:
        if not is_shadow_or_active("V3_GOVERNANCE"):
            return
        if not getattr(planner_response, "suggested_actions", None):
            return
        try:
            for index, action in enumerate(planner_response.suggested_actions):
                governance, latency_ms = _governance_engine.evaluate_action(
                    run_id=self.session_id,
                    mission_id=self.session_id,
                    step_id=action.action_id or f"planner.action.{index + 1}",
                    action=action,
                    runtime={},
                )
                event = self.v3_ledger.append(
                    run_id=self.session_id,
                    event_type="governance.evaluated",
                    payload={
                        "schema_version": governance.schema_version,
                        "governance_id": governance.governance_id,
                        "mission_id": governance.mission_id,
                        "step_id": governance.step_id,
                        "policy_decision": governance.policy_decision,
                        "execution_constraints": governance.execution_constraints.model_dump(mode="json"),
                        "approval_required": governance.approval_required,
                        "requires_handoff": governance.requires_handoff,
                        "decision_reason": governance.decision_reason,
                        "confidence": governance.confidence,
                        "risk_level": governance.risk_level,
                        "constraints_violated": governance.constraints_violated,
                        "approval_hooks": governance.approval_hooks,
                        "scheduler_item_id": governance.scheduler_item_id,
                        "scheduler_status": governance.scheduler_status,
                        "latency_ms": latency_ms,
                        "replay_metadata": governance.replay_metadata,
                    },
                    producer="backend.policy",
                )
                record_structured_trace(
                    run_id=self.session_id,
                    event_type="governance.evaluated",
                    payload={
                        "governance_id": governance.governance_id,
                        "policy_decision": governance.policy_decision,
                        "approval_required": governance.approval_required,
                        "risk_level": governance.risk_level,
                    },
                    ledger_event_id=event.event_id if event else None,
                )
                self._update_mission_intelligence_shadow(
                    event_type="governance.evaluated",
                    payload={
                        "policy_decision": governance.policy_decision,
                        "approval_required": governance.approval_required,
                        "requires_handoff": governance.requires_handoff,
                    },
                    step_index=0,
                    source_event_id=event.event_id if event else None,
                )
        except Exception:
            logger.debug("V3 governance shadow evaluation skipped", exc_info=True)

    def _evaluate_learning_shadow(self) -> None:
        """Evaluate completed run evidence in V3.6 shadow mode only.

        Evaluation is production-adjacent observability. It must never alter the
        planner response, workflow routing, browser execution, validation, or
        governance decisions.
        """
        if not is_shadow_or_active("V3_LEARNING"):
            return
        try:
            events = RunLedgerReader(self.db).list_events(self.session_id)
            artifacts = _evaluation_engine.evaluate_run(
                run_id=self.session_id,
                mission_id=self.session_id,
                events=events,
            )
            evaluation = artifacts.evaluation
            event = self.v3_ledger.append(
                run_id=self.session_id,
                event_type="evaluation.completed",
                payload={
                    "schema_version": evaluation.schema_version,
                    "evaluation_id": evaluation.evaluation_id,
                    "mission_id": evaluation.mission_id,
                    "validation_summary": evaluation.validation_summary,
                    "governance_summary": evaluation.governance_summary,
                    "mission_summary": evaluation.mission_summary,
                    "execution_metrics": evaluation.execution_metrics.model_dump(mode="json"),
                    "score_dimensions": evaluation.score_dimensions.model_dump(mode="json"),
                    "overall_score": evaluation.overall_score,
                    "confidence": evaluation.confidence,
                    "latency_ms": artifacts.latency_ms,
                    "replay_metadata": evaluation.replay_metadata,
                },
                producer="backend.evaluation",
            )
            record_structured_trace(
                run_id=self.session_id,
                event_type="evaluation.completed",
                payload={
                    "evaluation_id": evaluation.evaluation_id,
                    "overall_score": evaluation.overall_score,
                    "confidence": evaluation.confidence,
                    "learning_signals": len(artifacts.learning_signals),
                },
                ledger_event_id=event.event_id if event else None,
            )
            self.v3_ledger.append(
                run_id=self.session_id,
                event_type="run.scorecard_generated",
                payload=artifacts.scorecard.model_dump(mode="json"),
                producer="backend.evaluation",
            )
            for signal in artifacts.learning_signals:
                self.v3_ledger.append(
                    run_id=self.session_id,
                    event_type="learning.signal_recorded",
                    payload=signal.model_dump(mode="json"),
                    producer="backend.evaluation",
                )
            for record in artifacts.knowledge_records:
                self.v3_ledger.append(
                    run_id=self.session_id,
                    event_type="knowledge.recorded",
                    payload=record.model_dump(mode="json"),
                    producer="backend.evaluation",
                )
        except Exception:
            logger.debug("V3 learning shadow evaluation skipped", exc_info=True)

    def orchestrate_analysis(
        self,
        task: str,
        page_context: Any,
        prior_steps: list,
        supplemental_context: str,
        handoff_payload: Any = None,
    ):
        """Plan from the task and live page state without selecting a site workflow."""
        logger.info("Planning next browser action for session %s", self.session_id)

        session = self.db.get(WorkflowSession, self.session_id)
        session_created = not bool(session)
        if not session:
            session = WorkflowSession(
                id=self.session_id,
                tab_url=page_context.url,
                tab_title=page_context.title,
                status="running",
            )
            self.db.add(session)
        else:
            session.tab_url = page_context.url
            session.tab_title = page_context.title
            session.status = "running"
        self.db.commit()
        if session_created:
            self._record_v3_event(
                "run.started",
                {"task": task, "tab_url": page_context.url, "tab_title": page_context.title},
            )
        self._record_v3_event(
            "observation.captured",
            {
                "url": page_context.url,
                "title": page_context.title,
                "interactive_elements": len(page_context.interactive_elements),
            },
        )
        self._build_semantic_graph_shadow(page_context)
        browser_intelligence_artifact = self._build_browser_intelligence_shadow(page_context)

        registry = GroundedElementRegistry(self.session_id)
        registry.register_elements([element.model_dump() for element in page_context.interactive_elements])

        # V3.0: bootstrap state facts from cognitive handoff (cold-start only)
        if handoff_payload is not None:
            self.state_persistence.bootstrap_from_handoff(self.session_id, handoff_payload)

        db_state = self.state_persistence.get_state(self.session_id)
        if not db_state:
            db_state = self.state_persistence.create_state(self.session_id, {})
        verified_state = db_state.facts if db_state else {}

        # V3.0: build cognitive_context for the planner when payload is present
        cognitive_context: dict | None = None
        if handoff_payload is not None:
            from app.cognitive_core.workflow_context import build_cognitive_context
            cognitive_context = build_cognitive_context(handoff_payload)

        # Production Strategy Generation SG-1: if the previous production turn
        # passively detected Goal Convergence, append the already-prepared
        # context to this planner request as prior-step context only. This does
        # not alter prompts globally, outcomes, actions, execution, or recovery.
        from app.orchestrator.strategy_generation import consume_strategy_prior_steps
        planner_prior_steps = consume_strategy_prior_steps(
            session_id=self.session_id,
            prior_steps=prior_steps,
            page_context=page_context,
        )
        from app.orchestrator.planner_recovery import consume_recovery_prior_steps
        planner_prior_steps = consume_recovery_prior_steps(
            session_id=self.session_id,
            prior_steps=planner_prior_steps,
            page_context=page_context,
        )
        from app.execution_continuity import (
            enrich_planner_context,
            observe_execution_continuity,
            postprocess_planner_response,
        )

        continuity_snapshot = observe_execution_continuity(
            session_id=self.session_id,
            task=task,
            page_context=page_context,
            prior_steps=planner_prior_steps,
        )
        from app.execution_orchestrator import (
            enrich_planner_context_with_orchestrator,
            observe_execution_orchestrator,
            postprocess_with_orchestrator,
        )

        orchestrator_snapshot = observe_execution_orchestrator(
            session_id=self.session_id,
            task=task,
            page_context=page_context,
            prior_steps=planner_prior_steps,
        )
        from app.runtime_state_manager import (
            enrich_planner_context_with_runtime_state,
            observe_runtime_state,
            postprocess_with_runtime_state,
        )

        runtime_state_snapshot = observe_runtime_state(
            session_id=self.session_id,
            page_context=page_context,
            prior_steps=planner_prior_steps,
            current_phase=orchestrator_snapshot.active_phase.name if orchestrator_snapshot is not None else None,
        )
        from app.knowledge_extraction import (
            enrich_planner_context_with_knowledge,
            observe_knowledge_pipeline,
            postprocess_with_knowledge,
        )

        knowledge_snapshot = observe_knowledge_pipeline(
            session_id=self.session_id,
            task=task,
            page_context=page_context,
            current_phase=orchestrator_snapshot.active_phase.name if orchestrator_snapshot is not None else None,
        )
        from app.mission_completion import (
            completion_response,
            enrich_planner_context_with_completion,
            observe_mission_completion,
            postprocess_with_mission_completion,
            should_terminate_before_planner,
        )

        mission_completion_snapshot = observe_mission_completion(
            session_id=self.session_id,
            task=task,
            knowledge_snapshot=knowledge_snapshot,
            phase_state=orchestrator_snapshot,
            runtime_state=runtime_state_snapshot,
            execution_state=None,
        )
        if should_terminate_before_planner(mission_completion_snapshot):
            completion = completion_response(self.session_id, mission_completion_snapshot)
            self._record_cognitive_decision_comparison_shadow(
                result=completion,
                runtime_reason=mission_completion_snapshot.reason,
            )
            self._record_v3_event(
                "mission_completion.terminated_before_planner",
                mission_completion_snapshot.to_compact_context() if mission_completion_snapshot else {},
            )
            return completion
        knowledge_completion = _deterministic_knowledge_report_response(
            session_id=self.session_id,
            knowledge_snapshot=knowledge_snapshot,
            orchestrator_snapshot=orchestrator_snapshot,
        )
        if knowledge_completion is not None:
            self._record_v3_event(
                "knowledge_extraction.report_completed_without_planner",
                {
                    "report_id": getattr(knowledge_snapshot.report_artifact, "id", None) if knowledge_snapshot else None,
                    "read_count": len(knowledge_snapshot.read_artifacts) if knowledge_snapshot else 0,
                    "record_count": len(knowledge_snapshot.extraction_records) if knowledge_snapshot else 0,
                    "completion_status": dict(getattr(knowledge_snapshot, "completion_status", {}) or {}),
                },
            )
            return knowledge_completion
        read_continuation = _deterministic_read_phase_response(
            db=self.db,
            session_id=self.session_id,
            task=task,
            page_context=page_context,
            prior_steps=planner_prior_steps,
            runtime_state_snapshot=runtime_state_snapshot,
            knowledge_snapshot=knowledge_snapshot,
            mission_completion_snapshot=mission_completion_snapshot,
            orchestrator_snapshot=orchestrator_snapshot,
        )
        if read_continuation is not None:
            self._record_v3_event(
                "execution_orchestrator.read_phase_continuation_without_planner",
                {
                    "active_phase": orchestrator_snapshot.active_phase.name if orchestrator_snapshot else None,
                    "read_count": len(knowledge_snapshot.read_artifacts) if knowledge_snapshot else 0,
                    "opened_count": len(orchestrator_snapshot.artifacts.opened_pages) if orchestrator_snapshot else 0,
                    "queue_status": read_continuation.intent_execution.status if read_continuation.intent_execution else None,
                    "browser_action": bool(read_continuation.suggested_actions),
                },
            )
            return read_continuation
        interactive_state = _deterministic_interactive_state_response(
            session_id=self.session_id,
            task=task,
            page_context=page_context,
            orchestrator_snapshot=orchestrator_snapshot,
        )
        if interactive_state is not None:
            self._record_v3_event(
                "interactive_state.reported_without_planner",
                {
                    "page_url": str(getattr(page_context, "url", "") or ""),
                    "page_title": str(getattr(page_context, "title", "") or ""),
                    "active_phase": orchestrator_snapshot.active_phase.name if orchestrator_snapshot else None,
                },
            )
            return interactive_state
        from app.semantic_execution_kernel import (
            enrich_planner_context_with_kernel,
            observe_semantic_execution_kernel,
            postprocess_with_kernel,
        )

        kernel_snapshot = observe_semantic_execution_kernel(
            session_id=self.session_id,
            task=task,
            page_context=page_context,
            prior_steps=planner_prior_steps,
        )

        compressed_context = self.context_compressor.compress(
            task=task,
            page_context=page_context,
            verified_facts=verified_state,
            prior_steps=planner_prior_steps,
            task_constraints=[supplemental_context] if supplemental_context else [],
            cognitive_context=cognitive_context,
        )
        if browser_intelligence_artifact is not None and (
            is_active("V45_BROWSER_INTELLIGENCE")
            or is_shadow_or_active("V451_BROWSER_INTELLIGENCE_PLANNER_CONTEXT")
        ):
            from app.browser_intelligence import format_browser_intelligence_for_planner

            compressed_context["browser_intelligence"] = format_browser_intelligence_for_planner(
                browser_intelligence_artifact,
                scope_id=self.session_id,
            )
        bi_context = compressed_context.get("browser_intelligence") if isinstance(compressed_context, dict) else None
        bi_entities = bi_context.get("semantic_entities", []) if isinstance(bi_context, dict) else []
        if diagnostic_terminal_enabled("AI_BROWSER_LIVE_PATH_TRACE"):
            safe_print(
                "[V4.5.1 live-path] ORCHESTRATOR_PLANNER_CONTEXT_BOUNDARY "
                + json.dumps(
                    {
                        "session_id": self.session_id,
                        "has_browser_intelligence_artifact": browser_intelligence_artifact is not None,
                        "has_browser_intelligence_context": isinstance(bi_context, dict),
                        "semantic_entity_count": len(bi_entities) if isinstance(bi_entities, list) else 0,
                        "search_result_count": len(bi_context.get("search_results", [])) if isinstance(bi_context, dict) and isinstance(bi_context.get("search_results"), list) else 0,
                        "semantic_element_count": len(bi_context.get("semantic_elements", [])) if isinstance(bi_context, dict) and isinstance(bi_context.get("semantic_elements"), list) else 0,
                        "context_keys": list(compressed_context.keys()),
                        "first_semantic_entities": [
                            {
                                "entity_id": entity.get("entity_id"),
                                "title": entity.get("title"),
                                "canonical_url": entity.get("canonical_url"),
                                "source_adapter": entity.get("source_adapter"),
                            }
                            for entity in (bi_entities[:8] if isinstance(bi_entities, list) else [])
                            if isinstance(entity, dict)
                        ],
                    },
                    ensure_ascii=True,
                )
            )
        compressed_context = enrich_planner_context(compressed_context, continuity_snapshot)
        compressed_context = enrich_planner_context_with_orchestrator(compressed_context, orchestrator_snapshot)
        compressed_context = enrich_planner_context_with_runtime_state(compressed_context, runtime_state_snapshot)
        compressed_context = enrich_planner_context_with_knowledge(compressed_context, knowledge_snapshot)
        compressed_context = enrich_planner_context_with_completion(compressed_context, mission_completion_snapshot)
        compressed_context = enrich_planner_context_with_kernel(compressed_context, kernel_snapshot)
        if browser_intelligence_artifact is not None:
            from app.runtime_state_manager.entity_pipeline_trace import (
                planner_context_entities,
                record_planner_context_entities,
            )

            planner_entities = planner_context_entities(compressed_context)
            record_planner_context_entities(
                self.session_id,
                compressed_context,
                browser_entity_count=len(planner_entities),
            )
        from app.runtime_state_manager.entity_binding import entity_binding_trace, list_entities, registry_identity

        registered_entities = list_entities(self.session_id)
        self._record_v3_event(
            "entity_binding.planner_context",
            {
                "registry": registry_identity(self.session_id),
                "entities": [
                    {
                        "entity_id": entity.entity_id,
                        "artifact_id": entity.artifact_id,
                        "canonical_url": entity.canonical_url,
                        "entity_type": entity.entity_type,
                        "source_layer": entity.source_layer,
                        "state": entity.state,
                    }
                    for entity in registered_entities[:30]
                ],
                "trace_tail": entity_binding_trace(self.session_id, limit=12),
            },
        )
        self._build_context_packet_shadow(
            task=task,
            page_context=page_context,
            prior_steps=planner_prior_steps,
            supplemental_context=supplemental_context,
            verified_state=verified_state,
            compressed_context=compressed_context,
        )

        blueprint_result = self._try_blueprint_runtime(
            task=task,
            page_context=page_context,
            prior_steps=planner_prior_steps,
            runtime_state_snapshot=runtime_state_snapshot,
            browser_intelligence_artifact=browser_intelligence_artifact,
            knowledge_snapshot=knowledge_snapshot,
            mission_completion_snapshot=mission_completion_snapshot,
            orchestrator_snapshot=orchestrator_snapshot,
            kernel_snapshot=kernel_snapshot,
        )
        if blueprint_result is not None:
            return blueprint_result

        from app.services import ai_service

        with enforce_budget(self.budget_manager, BudgetCheckpoint.PLANNING):
            started = time.perf_counter()
            result = ai_service.analyze(
                session_id=self.session_id,
                task=task,
                page_context=page_context,
                prior_steps=planner_prior_steps,
                supplemental_context="",
                active_node=None,
                verified_state=verified_state,
                compressed_context=compressed_context,
            )
            result = postprocess_planner_response(result, continuity_snapshot)
            result = postprocess_with_orchestrator(result, orchestrator_snapshot)
            runtime_state_snapshot = observe_runtime_state(
                session_id=self.session_id,
                page_context=page_context,
                prior_steps=planner_prior_steps,
                current_phase=orchestrator_snapshot.active_phase.name if orchestrator_snapshot is not None else None,
                planner_response=result,
            )
            result = postprocess_with_runtime_state(result, runtime_state_snapshot)
            if result.intent_dispatch is not None:
                from app.intent_runtime import ExecutionContext, execute_intent_queue
                from app.services import mission_ledger_service

                execution_context = ExecutionContext(
                    mission_id=self.session_id,
                    task=task,
                    page_context=page_context,
                    prior_steps=planner_prior_steps,
                    runtime_state=runtime_state_snapshot,
                    browser_intelligence=browser_intelligence_artifact,
                    knowledge=knowledge_snapshot,
                    completion_state=mission_completion_snapshot,
                    phase_state=orchestrator_snapshot,
                    kernel_state=kernel_snapshot,
                )
                queued_intents = [result.intent_dispatch]
                if result.execution_orchestrator is not None:
                    queued_intents.extend(result.execution_orchestrator.continuation_actions)
                    result.execution_orchestrator.continuation_actions = []
                result.intent_execution = execute_intent_queue(
                    mission_id=self.session_id,
                    initial_intents=queued_intents,
                    context=execution_context,
                )
                mission_ledger_service.record_queue_result(
                    self.db,
                    mission_id=self.session_id,
                    initial_intent=result.intent_dispatch,
                    queue_result=result.intent_execution,
                )
                if result.intent_execution.status in {"waiting_browser", "browser_action_required"} and result.intent_execution.browser_action:
                    from app.schemas.response import SuggestedAction

                    browser_payload = _normalize_browser_action_payload(result.intent_execution.browser_action)
                    result.suggested_actions = [
                        SuggestedAction(
                            action_id=str(browser_payload.get("action_id") or browser_payload.get("intent_id") or result.intent_dispatch.intent_id),
                            intent_id=str(browser_payload.get("intent_id") or result.intent_dispatch.intent_id),
                            mission_id=self.session_id,
                            action_type=str(browser_payload.get("action_type") or result.intent_dispatch.intent),
                            target_selector=str(browser_payload.get("target_selector") or ""),
                            value=browser_payload.get("value"),
                            description=str(browser_payload.get("description") or result.intent_dispatch.reason),
                            reasoning=str(browser_payload.get("reasoning") or result.intent_dispatch.reason),
                            confidence=float(browser_payload.get("confidence") or 0.8),
                            safety_level=str(browser_payload.get("safety_level") or "safe"),  # type: ignore[arg-type]
                        )
                    ]
                runtime_state_snapshot = execution_context.runtime_state or runtime_state_snapshot
                knowledge_snapshot = execution_context.knowledge or knowledge_snapshot
                mission_completion_snapshot = execution_context.completion_state or mission_completion_snapshot
            knowledge_snapshot = observe_knowledge_pipeline(
                session_id=self.session_id,
                task=task,
                page_context=page_context,
                current_phase=orchestrator_snapshot.active_phase.name if orchestrator_snapshot is not None else None,
            )
            result = postprocess_with_knowledge(result, knowledge_snapshot)
            result = postprocess_with_kernel(
                result=result,
                session_id=self.session_id,
                task=task,
                page_context=page_context,
                prior_steps=planner_prior_steps,
            )
            mission_completion_snapshot = observe_mission_completion(
                session_id=self.session_id,
                task=task,
                knowledge_snapshot=knowledge_snapshot,
                phase_state=orchestrator_snapshot,
                runtime_state=runtime_state_snapshot,
                execution_state=kernel_snapshot,
                planner_response=result,
            )
            result = postprocess_with_mission_completion(result, mission_completion_snapshot)
            self._apply_collection_policy_continuation(
                result=result,
                knowledge_snapshot=knowledge_snapshot,
                page_context=page_context,
                prior_steps=planner_prior_steps,
            )
            self._route_legacy_browser_actions_through_mission_ledger(
                result=result,
                task=task,
                page_context=page_context,
                prior_steps=planner_prior_steps,
                runtime_state_snapshot=runtime_state_snapshot,
                browser_intelligence_artifact=browser_intelligence_artifact,
                knowledge_snapshot=knowledge_snapshot,
                mission_completion_snapshot=mission_completion_snapshot,
                orchestrator_snapshot=orchestrator_snapshot,
                kernel_snapshot=kernel_snapshot,
            )
            self._record_v3_event(
                "planner.responded",
                {
                    "outcome_kind": result.outcome_kind,
                    "suggested_actions": len(result.suggested_actions),
                    "has_report": result.report is not None,
                    "has_replan": result.replan is not None,
                    "execution_continuity": (
                        continuity_snapshot.progress_validation.to_dict()
                        if continuity_snapshot is not None
                        else None
                    ),
                    "semantic_execution_kernel": (
                        {
                            "entity_count": len(kernel_snapshot.entities),
                            "current_goal_id": kernel_snapshot.mission_state.current_goal_id,
                            "loop_detected": kernel_snapshot.loop_prevention.get("detected"),
                        }
                        if kernel_snapshot is not None
                        else None
                    ),
                    "execution_orchestrator": (
                        {
                            "active_phase": orchestrator_snapshot.active_phase.name,
                            "workflow_category": orchestrator_snapshot.workflow_category,
                            "artifact_counts": orchestrator_snapshot.artifacts.counts(),
                            "budget_exhausted": orchestrator_snapshot.budgets.exhausted,
                        }
                        if orchestrator_snapshot is not None
                        else None
                    ),
                    "runtime_state_manager": (
                        {
                            "tab_count": len(runtime_state_snapshot.tabs),
                            "artifact_count": len(runtime_state_snapshot.artifacts),
                            "focused_tab_id": runtime_state_snapshot.focused_tab_id,
                            "consistency": runtime_state_snapshot.consistency.to_dict(),
                        }
                        if runtime_state_snapshot is not None
                        else None
                    ),
                    "knowledge_extraction": (
                        {
                            "read_count": len(knowledge_snapshot.read_artifacts),
                            "record_count": len(knowledge_snapshot.extraction_records),
                            "missing_artifacts": knowledge_snapshot.missing_artifacts,
                            "completion_status": knowledge_snapshot.completion_status,
                        }
                        if knowledge_snapshot is not None
                        else None
                    ),
                    "mission_completion": (
                        mission_completion_snapshot.to_compact_context()
                        if mission_completion_snapshot is not None
                        else None
                    ),
                },
            )
            self._ground_intents_shadow(
                task=task,
                page_context=page_context,
                prior_steps=planner_prior_steps,
                supplemental_context=supplemental_context,
                verified_state=verified_state,
                compressed_context=compressed_context,
                planner_response=result,
            )
            self._evaluate_governance_shadow(result)
            latency_ms = int((time.perf_counter() - started) * 1000)
            # Provider-neutral approximation; exact provider usage can replace this
            # without changing budget or analytics contracts. Estimate the same
            # provider-safe projection sent by ai_service.analyze, not the richer
            # internal context used by deterministic runtime layers.
            planner_budget_context = ai_service.budget_compressed_planner_context(compressed_context)
            token_estimate = ai_service.estimate_tokens(json.dumps(planner_budget_context))
            token_estimate += ai_service.estimate_tokens(json.dumps(_planner_output_budget_projection(result)))
            record_planner_call(self.db, self.session_id, token_estimate, latency_ms)
            self.budget_manager.consume(tokens=token_estimate)

            # Production SGV Phase 1: validate report claims against live page
            # evidence before returning to the extension.
            # SGV is a validator only — outcome_kind and report are never modified.
            if result.outcome_kind == "report":
                if result.backend_authoritative_report:
                    result.sgv_verified = True
                else:
                    from app.orchestrator.report_verifier import verify_report
                    result.sgv_verified = verify_report(
                        claim=result.report.claim if result.report else "",
                        answer=result.report.answer if result.report else None,
                        page_context=page_context,
                    )
                if is_shadow_or_active("V3_VALIDATION"):
                    graph_result = (
                        _semantic_graph_cache.get_or_build(page_context)
                        if is_shadow_or_active("V3_SEMANTIC_GRAPH")
                        else None
                    )
                    validation, validation_ms = _validation_engine.validate_report(
                        run_id=self.session_id,
                        mission_id=self.session_id,
                        step_id=f"planner.report.{latency_ms}",
                        claim=result.report.claim if result.report else "",
                        answer=result.report.answer if result.report else None,
                        page_context=page_context,
                        semantic_graph=graph_result.graph if graph_result else None,
                    )
                    self._record_validation_shadow(validation, validation_ms)
                logger.info(
                    "SGV: session=%s verified=%s claim=%r",
                    self.session_id,
                    result.sgv_verified,
                    result.report.claim if result.report else "",
                )
                self._record_v3_event(
                    "report.verified",
                    {
                        "sgv_verified": result.sgv_verified,
                        "has_answer": bool(result.report and result.report.answer),
                    },
                )
                if result.sgv_verified:
                    self._evaluate_learning_shadow()

            # Production Goal Convergence GC-1: observer-only stagnation signal.
            # It never modifies outcome_kind, suggested_actions, report, replan,
            # prompts, execution, recovery, or planner decisions.
            from app.orchestrator.goal_convergence import assess_goal_convergence
            convergence = assess_goal_convergence(
                session_id=self.session_id,
                page_context=page_context,
                planner_response=result,
            )
            if not result.backend_authoritative_report:
                result.goal_convergence = convergence.goal_convergence
            logger.info(
                "Goal convergence: session=%s stalled=%s signature=%s",
                self.session_id,
                result.goal_convergence,
                convergence.semantic_signature,
            )
            self._record_v3_event(
                "goal_convergence.assessed",
                {
                    "goal_convergence": result.goal_convergence,
                    "semantic_signature": convergence.semantic_signature,
                },
            )

            # Production Strategy Generation SG-1: prepare context for the next
            # planner turn only after GC observes semantic stagnation. The
            # current planner response remains untouched and no recovery or
            # automatic replanning is triggered.
            from app.orchestrator.strategy_generation import prepare_strategy_context_if_stalled
            strategy_context_prepared = prepare_strategy_context_if_stalled(
                session_id=self.session_id,
                goal_convergence=result.goal_convergence,
                task=task,
                page_context=page_context,
                planner_response=result,
            )
            logger.info(
                "Strategy generation: session=%s prepared=%s",
                self.session_id,
                strategy_context_prepared,
            )
            # Production Planner Recovery PR-1: after GC and SG both fire,
            # mark the next planner invocation as a one-turn recovery cycle.
            # This only adds context to the next request and never creates
            # actions, reports, replans, retries, or workflow transitions.
            from app.orchestrator.planner_recovery import (
                prepare_planner_recovery_if_strategy_context,
            )
            recovery_prepared = prepare_planner_recovery_if_strategy_context(
                session_id=self.session_id,
                goal_convergence=result.goal_convergence,
                strategy_context_prepared=strategy_context_prepared,
            )
            logger.info(
                "Planner recovery: session=%s prepared=%s",
                self.session_id,
                recovery_prepared,
            )
            self._record_cognitive_decision_comparison_shadow(result=result)

            return result

    def _apply_collection_policy_continuation(
        self,
        *,
        result: Any,
        knowledge_snapshot: Any,
        page_context: Any,
        prior_steps: list,
    ) -> None:
        """Create the next safe pagination action from CollectionPolicy evidence.

        This runs before the legacy action bridge so the generated action is
        converted into a durable Mission Ledger intent before browser handoff.
        """
        if result.intent_dispatch is not None or result.intent_execution is not None:
            return
        if list(getattr(result, "suggested_actions", []) or []):
            return
        if getattr(result, "backend_authoritative_report", False):
            return
        if getattr(result, "sgv_verified", False):
            return
        collection_state = getattr(knowledge_snapshot, "collection_state", None)
        if collection_state is None or not bool(getattr(collection_state, "should_continue", False)):
            return
        next_url = str(getattr(collection_state, "next_url", "") or "").strip()
        if not _is_http_url(next_url):
            return
        current_url = str(getattr(page_context, "url", "") or "").rstrip("/").lower()
        if next_url.rstrip("/").lower() == current_url:
            return
        if _already_navigated_to(prior_steps, next_url):
            return

        from app.schemas.response import SuggestedAction

        policy = getattr(collection_state, "policy", None)
        item_count = int(getattr(collection_state, "total_seen_count", 0) or 0)
        requested_count = int(getattr(policy, "requested_count", 0) or 0)
        result.outcome_kind = "act"
        result.suggested_actions = [
            SuggestedAction(
                action_id="collection_next_" + hashlib.sha1(next_url.encode("utf-8")).hexdigest()[:12],
                action_type="navigate",
                target_selector="",
                value=next_url,
                description="Continue collection on the next result page",
                reasoning=(
                    "CollectionPolicy found more pages to collect. "
                    f"Collected {item_count}/{requested_count or '?'} items so far; "
                    f"next page is {next_url}."
                ),
                confidence=0.86,
                safety_level="safe",
            )
        ]
        result.analysis = "\n\n".join(
            [
                str(getattr(result, "analysis", "") or ""),
                (
                    "CollectionPolicy continuation: navigating to the next page "
                    f"to continue collecting entries ({item_count}/{requested_count or '?'} seen)."
                ),
            ]
        ).strip()
        self._record_v3_event(
            "collection_policy.continuation_selected",
            {
                "next_url": next_url,
                "item_count": item_count,
                "requested_count": requested_count,
                "stop_reason": getattr(collection_state, "stop_reason", ""),
            },
        )

    def _route_legacy_browser_actions_through_mission_ledger(
        self,
        *,
        result: Any,
        task: str,
        page_context: Any,
        prior_steps: list,
        runtime_state_snapshot: Any,
        browser_intelligence_artifact: Any,
        knowledge_snapshot: Any,
        mission_completion_snapshot: Any,
        orchestrator_snapshot: Any,
        kernel_snapshot: Any,
    ) -> None:
        """Make legacy SuggestedAction output enter Runtime V1 before browser handoff.

        Planner Contract V2 still exposes SuggestedAction to the extension as a
        compatibility DTO, but executable browser work must have a durable
        Mission Ledger intent identity before the browser receives it.
        """
        if result.intent_dispatch is not None or result.intent_execution is not None:
            return
        if result.outcome_kind not in {"act", "wait"}:
            return
        actions = list(result.suggested_actions or [])
        if not actions:
            return
        if any(getattr(action, "intent_id", None) for action in actions):
            return

        from app.intent_dispatcher.models import ExecutionContext
        from app.intent_runtime import dispatch_intent, execute_intent_queue
        from app.schemas.response import SuggestedAction
        from app.services import mission_ledger_service

        directives = []
        for action in actions:
            payload = action.model_dump(mode="json")
            payload["mission_id"] = self.session_id
            directive = dispatch_intent(intent=action.action_type, payload=payload)
            if directive is None:
                continue
            directive.mission_id = self.session_id
            directives.append(directive)

        if not directives:
            return

        execution_context = ExecutionContext(
            mission_id=self.session_id,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
            runtime_state=runtime_state_snapshot,
            browser_intelligence=browser_intelligence_artifact,
            knowledge=knowledge_snapshot,
            completion_state=mission_completion_snapshot,
            phase_state=orchestrator_snapshot,
            kernel_state=kernel_snapshot,
            metadata={"source": "legacy_planner_action_bridge"},
        )
        queue_result = execute_intent_queue(
            mission_id=self.session_id,
            initial_intents=directives,
            context=execution_context,
        )
        mission_ledger_service.record_queue_result(
            self.db,
            mission_id=self.session_id,
            initial_intent=directives[0],
            queue_result=queue_result,
        )
        result.intent_dispatch = directives[0]
        result.intent_execution = queue_result

        if queue_result.status not in {"waiting_browser", "browser_action_required"} or not queue_result.browser_action:
            result.suggested_actions = []
            return

        browser_payload = _normalize_browser_action_payload(queue_result.browser_action)
        result.suggested_actions = [
            SuggestedAction(
                action_id=str(browser_payload.get("action_id") or browser_payload.get("intent_id") or directives[0].intent_id),
                intent_id=str(browser_payload.get("intent_id") or directives[0].intent_id),
                mission_id=self.session_id,
                action_type=str(browser_payload.get("action_type") or directives[0].intent),
                target_selector=str(browser_payload.get("target_selector") or ""),
                value=browser_payload.get("value"),
                description=str(browser_payload.get("description") or directives[0].reason),
                reasoning=str(browser_payload.get("reasoning") or directives[0].reason),
                confidence=float(browser_payload.get("confidence") or 0.8),
                safety_level=str(browser_payload.get("safety_level") or "safe"),  # type: ignore[arg-type]
            )
        ]
        self._record_v3_event(
            "mission_ledger.legacy_actions_bridged",
            {
                "queued_intents": len(directives),
                "first_intent_id": directives[0].intent_id,
                "queue_status": queue_result.status,
            },
        )

    def _try_blueprint_runtime(
        self,
        *,
        task: str,
        page_context: Any,
        prior_steps: list,
        runtime_state_snapshot: Any,
        browser_intelligence_artifact: Any,
        knowledge_snapshot: Any,
        mission_completion_snapshot: Any,
        orchestrator_snapshot: Any,
        kernel_snapshot: Any,
    ) -> Any | None:
        if not is_active("MISSION_BLUEPRINT_V1"):
            return None
        try:
            from app.intent_dispatcher.models import ExecutionContext
            from app.mission.blueprint.expansion import BlueprintExpansionEngine
            from app.mission.blueprint.readiness import BlueprintReadinessEvaluator
            from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository
            from app.mission.intelligence.blueprint_builder import create_and_store_blueprint
            from app.schemas.response import AnalyzeResponse, ReplanOutcome, SuggestedAction
            from app.services import mission_ledger_service

            repository = SqlAlchemyMissionBlueprintRepository(self.db)
            blueprint = repository.get(self.session_id)
            lifecycle = "loaded"
            if blueprint is None:
                build_result = create_and_store_blueprint(
                    mission_id=self.session_id,
                    user_goal=task,
                    repository=repository,
                    created_by="workflow_orchestrator",
                )
                blueprint = build_result.blueprint
                lifecycle = "created"
            elif _blueprint_stale_for_task(blueprint, task):
                from app.mission.intelligence.blueprint_builder import MissionBlueprintBuilder

                build_result = MissionBlueprintBuilder().build(
                    mission_id=self.session_id,
                    user_goal=task,
                )
                blueprint = replace(
                    build_result.blueprint,
                    blueprint_id=blueprint.blueprint_id,
                    revision=blueprint.revision + 1,
                    created_at=blueprint.created_at,
                )
                blueprint = repository.update(
                    blueprint,
                    reason="mission objective changed or blueprint classification refreshed",
                    created_by="workflow_orchestrator",
                )
                lifecycle = "refreshed"

            evidence = mission_ledger_service._blueprint_evidence_from_ledger(  # type: ignore[attr-defined]
                self.db,
                mission_id=self.session_id,
                include_objectives=True,
            )
            readiness = BlueprintReadinessEvaluator().evaluate(blueprint, evidence=evidence)
            repository.save_readiness_snapshot(readiness)
            expansion = BlueprintExpansionEngine(db=self.db, repository=repository).expand_ready_nodes(
                mission_id=self.session_id,
                readiness=readiness,
            )
            search_recovery = _search_challenge_recovery_action(
                session_id=self.session_id,
                task=task,
                page_context=page_context,
                prior_steps=prior_steps,
            )
            if search_recovery is not None:
                response = AnalyzeResponse(
                    session_id=self.session_id,
                    analysis=(
                        "Search provider challenge/no-results state detected. "
                        "Recovering by switching to an alternate search provider before continuing evidence collection."
                    ),
                    outcome_kind="act",
                    suggested_actions=[search_recovery],
                )
                self._record_v3_event(
                    "mission_blueprint.search_provider_recovery",
                    {
                        "blueprint_id": blueprint.blueprint_id,
                        "revision": blueprint.revision,
                        "reason": "search_provider_challenge",
                        "recovery_action": search_recovery.action_type,
                        "recovery_url": search_recovery.value,
                    },
                )
                return response
            open_continuation = _deterministic_open_phase_response(
                session_id=self.session_id,
                orchestrator_snapshot=orchestrator_snapshot,
            )
            if open_continuation is not None:
                self._record_v3_event(
                    "mission_blueprint.open_phase_continued_without_planner",
                    {
                        "blueprint_id": blueprint.blueprint_id,
                        "revision": blueprint.revision,
                        "reason": "opened_sources_below_target",
                        "action_url": open_continuation.suggested_actions[0].value if open_continuation.suggested_actions else None,
                    },
                )
                return open_continuation
            search_collection = _deterministic_search_collection_response(
                db=self.db,
                session_id=self.session_id,
                task=task,
                page_context=page_context,
                prior_steps=prior_steps,
                runtime_state_snapshot=runtime_state_snapshot,
                browser_intelligence_artifact=browser_intelligence_artifact,
                knowledge_snapshot=knowledge_snapshot,
                mission_completion_snapshot=mission_completion_snapshot,
                orchestrator_snapshot=orchestrator_snapshot,
                kernel_snapshot=kernel_snapshot,
            )
            if search_collection is not None:
                self._record_v3_event(
                    "mission_blueprint.search_results_collected_without_planner",
                    {
                        "blueprint_id": blueprint.blueprint_id,
                        "revision": blueprint.revision,
                        "reason": "search_results_page_no_queued_work",
                        "queue_status": search_collection.intent_execution.status if search_collection.intent_execution else None,
                    },
                )
                return search_collection
            if readiness.ready_nodes and not expansion.generated_intent_ids:
                reason = (
                    "Blueprint has ready nodes but no executable browser intents after URL and safety filtering. "
                    "The current discovery surface may be blocked or may not expose usable results."
                )
                self._record_v3_event(
                    "mission_blueprint.no_executable_ready_nodes",
                    {
                        "blueprint_id": blueprint.blueprint_id,
                        "revision": blueprint.revision,
                        "ready_nodes": readiness.ready_nodes,
                        "blocked_nodes": readiness.blocked_nodes,
                    },
                )
                return AnalyzeResponse(
                    session_id=self.session_id,
                    analysis=reason,
                    outcome_kind="replan",
                    suggested_actions=[],
                    replan=ReplanOutcome(reason=reason),
                )
            if not readiness.ready_nodes and not expansion.generated_intent_ids:
                self._record_v3_event(
                    "mission_blueprint.planner_fallback",
                    {
                        "reason": "no_ready_blueprint_nodes",
                        "blueprint_id": blueprint.blueprint_id,
                        "revision": blueprint.revision,
                    },
                )
                return None

            execution_context = ExecutionContext(
                mission_id=self.session_id,
                task=task,
                page_context=page_context,
                prior_steps=prior_steps,
                runtime_state=runtime_state_snapshot,
                browser_intelligence=browser_intelligence_artifact,
                knowledge=knowledge_snapshot,
                completion_state=mission_completion_snapshot,
                phase_state=orchestrator_snapshot,
                kernel_state=kernel_snapshot,
                metadata={"source": "mission_blueprint_runtime"},
            )
            executed = mission_ledger_service.execute_next_queued_intents(
                self.db,
                mission_id=self.session_id,
                context=execution_context,
            )
            if executed is None:
                self._record_v3_event(
                    "mission_blueprint.planner_fallback",
                    {
                        "reason": "no_executable_ledger_intent",
                        "blueprint_id": blueprint.blueprint_id,
                        "revision": blueprint.revision,
                        "ready_nodes": readiness.ready_nodes,
                    },
                )
                return None

            initial_intent, queue_result = executed
            suggested_actions = []
            if queue_result.status in {"waiting_browser", "browser_action_required"} and queue_result.browser_action:
                browser_payload = _normalize_browser_action_payload(queue_result.browser_action)
                suggested_actions = [
                    SuggestedAction(
                        action_id=str(browser_payload.get("action_id") or browser_payload.get("intent_id") or initial_intent.intent_id),
                        intent_id=str(browser_payload.get("intent_id") or initial_intent.intent_id),
                        mission_id=self.session_id,
                        action_type=str(browser_payload.get("action_type") or initial_intent.intent),
                        target_selector=str(browser_payload.get("target_selector") or ""),
                        value=browser_payload.get("value"),
                        description=str(browser_payload.get("description") or initial_intent.reason),
                        reasoning=str(browser_payload.get("reasoning") or initial_intent.reason),
                        confidence=float(browser_payload.get("confidence") or 0.8),
                        safety_level=str(browser_payload.get("safety_level") or "safe"),  # type: ignore[arg-type]
                    )
                ]

            response = AnalyzeResponse(
                session_id=self.session_id,
                analysis=(
                    "Mission Blueprint produced deterministic executable work. "
                    "Planner fallback was not invoked."
                ),
                outcome_kind="act",
                suggested_actions=suggested_actions,
                intent_execution=queue_result,
            )
            self._record_v3_event(
                "mission_blueprint.runtime_selected",
                {
                    "blueprint_id": blueprint.blueprint_id,
                    "revision": blueprint.revision,
                    "lifecycle": lifecycle,
                    "ready_nodes": readiness.ready_nodes,
                    "expanded_nodes": expansion.expanded_nodes,
                    "generated_intent_ids": expansion.generated_intent_ids,
                    "queue_status": queue_result.status,
                    "browser_action": suggested_actions[0].action_type if suggested_actions else None,
                    "planner_fallback": False,
                },
            )
            return response
        except Exception:
            logger.debug("Mission Blueprint runtime integration fell back to planner", exc_info=True)
            return None

    def _record_cognitive_decision_comparison_shadow(
        self,
        *,
        result: Any,
        runtime_reason: str | None = None,
    ) -> None:
        """Best-effort Wave 5A comparison hook.

        Runtime V1 remains authoritative. This method must never mutate the
        response, create intents, call providers, replan, or raise into the
        orchestration path.
        """
        try:
            if not is_shadow_or_active("COGNITIVE_RUNTIME_V2"):
                return
            from app.cognitive_runtime.comparison_service import DecisionComparisonService
            from app.cognitive_runtime.comparison_repository import SqlAlchemyDecisionComparisonRepository
            from app.cognitive_runtime.repository import SqlAlchemyCognitiveRuntimeRepository
            from app.cognitive_runtime.service import CognitiveRuntimeService
            from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository

            cognitive_repository = SqlAlchemyCognitiveRuntimeRepository(self.db)
            service = CognitiveRuntimeService(cognitive_repository)
            if service.load_runtime(self.session_id) is None:
                return
            blueprint_repository = SqlAlchemyMissionBlueprintRepository(self.db)
            started = time.perf_counter()
            recommendation = service.cognitive_decision(
                mission_id=self.session_id,
                blueprint=blueprint_repository.get(self.session_id),
                readiness=blueprint_repository.latest_readiness_snapshot(self.session_id),
            )
            latency_ms = (time.perf_counter() - started) * 1000
            runtime_decision, inferred_reason = _runtime_decision_from_response(result)
            action = (getattr(result, "suggested_actions", None) or [None])[0]
            intent_id = getattr(action, "intent_id", None) if action is not None else None
            DecisionComparisonService(SqlAlchemyDecisionComparisonRepository(self.db)).record(
                mission_id=self.session_id,
                intent_id=intent_id,
                blueprint_node_id=None,
                runtime_decision=runtime_decision,
                runtime_reason=runtime_reason or inferred_reason,
                cognitive=recommendation,
                recommendation_latency_ms=latency_ms,
                metadata={
                    "source": "workflow_orchestrator",
                    "runtime_response_outcome_kind": getattr(result, "outcome_kind", None),
                    "execution_impact": "none",
                },
            )
        except Exception:
            logger.debug("Cognitive Runtime Wave 5A comparison skipped", exc_info=True)

    def process_executed_step(
        self,
        action_type: str,
        selector: str,
        value: str,
        success: bool,
        execution_result: str,
    ) -> None:
        """Record execution without applying domain-specific validation or recovery."""
        logger.info("Recording browser execution result: %s", execution_result)

        self.budget_manager.enforce()

        session = self.db.get(WorkflowSession, self.session_id)
        if session:
            session.status = "action_executed" if success else "action_failed"
            self.db.commit()

        db_state = self.state_persistence.get_state(self.session_id)
        current_facts = db_state.facts if db_state else {}
        events_count = self.db.query(WorkflowEvent).filter(
            WorkflowEvent.session_id == self.session_id
        ).count()
        self.timeline_service.record_step(
            step_number=events_count,
            action_type=action_type,
            value_used=f"selector: {selector}, value: {value}",
            state_before=current_facts,
            state_after=current_facts,
            screenshot_before="",
            screenshot_after="",
            success=success,
        )
        self.budget_manager.consume(steps=1, retries=0 if success else 1)
        self._record_v3_event(
            "execution.completed",
            {
                "action_type": action_type,
                "success": success,
                "execution_result": execution_result,
            },
            step_index=events_count,
        )
        if success and action_type.lower() in {"open_new_tab", "navigate"} and value.startswith(("http://", "https://")):
            from app.runtime_state_manager.entity_binding import bind_runtime_resource, resolve_entity
            from app.runtime_state_manager.entity_pipeline_trace import get_entity_pipeline_tracer

            entity = resolve_entity(self.session_id, canonical_url=value)
            if entity is not None:
                logical_tab_id = "logical_tab_" + hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
                bound = bind_runtime_resource(
                    self.session_id,
                    entity_id=entity.entity_id,
                    runtime_resource_id=logical_tab_id,
                )
                self._record_v3_event(
                    "entity_binding.browser_execution",
                    {
                        "entity_id": entity.entity_id,
                        "artifact_id": entity.artifact_id,
                        "canonical_url": entity.canonical_url,
                        "runtime_resource_id": logical_tab_id,
                        "tab_id": logical_tab_id,
                        "window_id": "logical_window_1",
                        "url": value,
                        "binding_success": bound is not None,
                    },
                    step_index=events_count,
                )
                get_entity_pipeline_tracer().emit(
                    self.session_id,
                    "BROWSER_CONTROL",
                    success=True,
                    reason="executed",
                    trace_id=entity.trace_id,
                    entity_id=entity.entity_id,
                    artifact_id=entity.artifact_id,
                    canonical_url=entity.canonical_url,
                    runtime_resource_id=logical_tab_id,
                    source=entity.source_layer,
                )
            else:
                get_entity_pipeline_tracer().verify_exists(
                    self.session_id,
                    stage="BROWSER_CONTROL",
                    reason="Runtime -> Browser resource binding exists",
                    exists=False,
                )
        if is_shadow_or_active("V3_VALIDATION"):
            validation, validation_ms = _validation_engine.validate_execution(
                run_id=self.session_id,
                mission_id=self.session_id,
                step_id=f"execution.{events_count}",
                action_type=action_type,
                selector=selector,
                success=success,
                execution_result=execution_result,
            )
            self._record_validation_shadow(validation, validation_ms)


def _is_http_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _already_navigated_to(prior_steps: list, url: str) -> bool:
    target = url.rstrip("/").lower()
    for step in prior_steps:
        value = str(getattr(step, "value", "") or "").rstrip("/").lower()
        page_url = str(getattr(step, "page_url", "") or "").rstrip("/").lower()
        if target and target in {value, page_url}:
            return True
    return False


def _blueprint_stale_for_task(blueprint: Any, task: str) -> bool:
    task_text = _normalize_task_text(task)
    objective_text = _normalize_task_text(getattr(blueprint, "objective", ""))
    if task_text and objective_text and task_text != objective_text:
        return True
    if _explicit_url_collection_task(task):
        node_ids = {str(getattr(node, "node_id", "")) for node in list(getattr(blueprint, "nodes", []) or [])}
        if "open_search_engine" in node_ids or "execute_search" in node_ids:
            return True
        locate_source = next((node for node in list(getattr(blueprint, "nodes", []) or []) if getattr(node, "node_id", "") == "locate_source"), None)
        payload = dict(getattr(locate_source, "metadata", {}) or {}).get("action_payload") if locate_source is not None else None
        if not isinstance(payload, dict) or not _is_http_url(str(payload.get("value") or "")):
            return True
    return False


def _search_challenge_recovery_action(
    *,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list,
) -> Any | None:
    from urllib.parse import quote_plus, urlparse

    url = str(getattr(page_context, "url", "") or "")
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if not _is_search_challenge_page(page_context):
        return None
    query = _search_query_from_task(task)
    if not query:
        return None

    provider_urls = [
        ("bing", f"https://www.bing.com/search?q={quote_plus(query)}"),
        ("duckduckgo", f"https://duckduckgo.com/?q={quote_plus(query)}"),
    ]
    attempted = {_normalize_attempted_search_url(url)}
    for step in prior_steps:
        attempted.add(_normalize_attempted_search_url(str(getattr(step, "value", "") or "")))
        attempted.add(_normalize_attempted_search_url(str(getattr(step, "page_url", "") or "")))

    provider_name = ""
    recovery_url = ""
    for candidate_name, candidate_url in provider_urls:
        if candidate_name == host:
            continue
        if _normalize_attempted_search_url(candidate_url) in attempted:
            continue
        provider_name = candidate_name
        recovery_url = candidate_url
        break
    if not recovery_url:
        return None

    from app.schemas.response import SuggestedAction

    return SuggestedAction(
        action_id=f"search_provider_recovery_{provider_name}",
        mission_id=session_id,
        action_type="navigate",
        target_selector="",
        value=recovery_url,
        description=f"Recover search by opening {provider_name.title()} results for: {query}",
        reasoning=(
            "The current search provider returned a challenge/no-results surface. "
            "Switch to an alternate public search provider so organic result collection can continue."
        ),
        confidence=0.86,
        safety_level="safe",
    )


def _is_search_challenge_page(page_context: Any) -> bool:
    from urllib.parse import urlparse

    url = str(getattr(page_context, "url", "") or "")
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    text = " ".join(
        str(value or "")
        for value in (
            getattr(page_context, "title", ""),
            getattr(page_context, "visible_text", ""),
            getattr(page_context, "selected_text", ""),
        )
    ).lower()
    if host == "google.com" and path.startswith(("/sorry", "/challenge", "/consent")):
        return True
    challenge_markers = (
        "one last step",
        "please solve the challenge",
        "captcha",
        "recaptcha",
        "hcaptcha",
        "verify you are human",
        "not a robot",
        "unusual traffic",
        "automated queries",
    )
    return host in {"google.com", "bing.com", "duckduckgo.com"} and any(marker in text for marker in challenge_markers)


def _normalize_attempted_search_url(url: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    parsed = urlparse(str(url or ""))
    if not parsed.scheme or not parsed.netloc:
        return ""
    host = parsed.netloc.lower().removeprefix("www.")
    query = urlencode([(key, value) for key, value in parse_qsl(parsed.query) if key.lower() == "q"])
    return urlunparse((parsed.scheme.lower(), host, parsed.path.rstrip("/") or "/", "", query, "")).rstrip("/").lower()


def _deterministic_search_collection_response(
    *,
    db: Session,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list,
    runtime_state_snapshot: Any,
    browser_intelligence_artifact: Any,
    knowledge_snapshot: Any,
    mission_completion_snapshot: Any,
    orchestrator_snapshot: Any,
    kernel_snapshot: Any,
) -> Any | None:
    if not _is_search_results_url(str(getattr(page_context, "url", "") or "")):
        return None
    if _blueprint_node_completed(db, mission_id=session_id, node_id="collect_serp_results"):
        return None

    from app.intent_dispatcher.models import ExecutionContext, IntentDispatchDirective
    from app.intent_runtime import execute_intent_queue
    from app.schemas.response import AnalyzeResponse
    from app.services import mission_ledger_service

    directive = IntentDispatchDirective(
        mission_id=session_id,
        intent="collect_search_results",
        owner="browser_intelligence",
        capability="serp_collection",
        dispatch_target="browser_intelligence",
        browser_executable=False,
        reason="Collect visible search result candidates from the current search results page without planner fallback.",
        payload={
            "action_type": "collect_search_results",
            "description": "Collect visible search result candidates",
            "reasoning": "The current page is a search results page; deterministic collection can register openable entities.",
            "confidence": 0.9,
            "safety_level": "safe",
            "blueprint_node_id": "collect_serp_results",
            "blueprint_objective": "Collect search result candidates from the SERP",
        },
    )
    execution_context = ExecutionContext(
        mission_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
        runtime_state=runtime_state_snapshot,
        browser_intelligence=browser_intelligence_artifact,
        knowledge=knowledge_snapshot,
        completion_state=mission_completion_snapshot,
        phase_state=orchestrator_snapshot,
        kernel_state=kernel_snapshot,
        metadata={"source": "mission_blueprint_deterministic_search_collection"},
    )
    queue_result = execute_intent_queue(
        mission_id=session_id,
        initial_intents=[directive],
        context=execution_context,
    )
    mission_ledger_service.record_queue_result(
        db,
        mission_id=session_id,
        initial_intent=directive,
        queue_result=queue_result,
    )
    return AnalyzeResponse(
        session_id=session_id,
        analysis=(
            "Mission Blueprint collected search result candidates deterministically. "
            "Planner fallback was not invoked."
        ),
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
        intent_execution=queue_result,
    )


def _deterministic_interactive_state_response(
    *,
    session_id: str,
    task: str,
    page_context: Any,
    orchestrator_snapshot: Any,
) -> AnalyzeResponse | None:
    text = str(task or "").lower()
    if not any(term in text for term in ("detect", "verify", "whether", "status", "logged in", "login")):
        return None
    current_url = str(getattr(page_context, "url", "") or "")
    title = str(getattr(page_context, "title", "") or "")
    if "web.whatsapp.com" not in current_url.lower() and "whatsapp" not in title.lower():
        return None
    opened = list(getattr(getattr(orchestrator_snapshot, "artifacts", None), "opened_pages", []) or []) if orchestrator_snapshot else []
    if not any("web.whatsapp.com" in str(url).lower() for url in [current_url, *opened]):
        return None

    state = _interactive_page_state(page_context)
    report = (
        "| Check | Status | Evidence |\n"
        "|---|---|---|\n"
        f"| Page opened | yes | {current_url or title} |\n"
        f"| Login/QR required | {'yes' if state['login_required'] else 'no'} | {state['login_evidence'] or 'not observed'} |\n"
        f"| Contact/search field visible | {'yes' if state['contact_search_selector'] else 'no'} | {state['contact_search_selector'] or 'not observed'} |\n"
        f"| Message field visible | {'yes' if state['message_selector'] else 'no'} | {state['message_selector'] or 'not observed'} |\n"
        f"| Attachment/file control visible | {'yes' if state['file_selector'] else 'no'} | {state['file_selector'] or 'not observed'} |"
    )
    return AnalyzeResponse(
        session_id=session_id,
        analysis="Deterministic interactive state detector produced a page-state report from current DOM evidence.",
        outcome_kind="report",
        report=ReportOutcome(answer=report, claim="Interactive browser app state was detected from current DOM evidence."),
        suggested_actions=[],
        sgv_verified=True,
        goal_convergence=True,
        backend_authoritative_report=True,
    )


def _interactive_page_state(page_context: Any) -> dict[str, str | bool]:
    visible_text = " ".join(str(getattr(page_context, "visible_text", "") or "").split())
    lower_visible = visible_text.lower()
    state: dict[str, str | bool] = {
        "login_required": any(term in lower_visible for term in ("use whatsapp on your computer", "link a device", "scan", "qr code")),
        "login_evidence": "",
        "contact_search_selector": "",
        "message_selector": "",
        "file_selector": "",
    }
    if state["login_required"]:
        state["login_evidence"] = _first_matching_phrase(lower_visible, ("use whatsapp on your computer", "link a device", "scan", "qr code"))
    for element in list(getattr(page_context, "interactive_elements", []) or []):
        data = element.model_dump() if hasattr(element, "model_dump") else dict(element)
        selector = str(data.get("selector") or "")
        if not selector:
            continue
        label = " ".join(
            str(data.get(key) or "")
            for key in ("text", "aria_label", "accessibility_name", "placeholder", "role", "type", "input_type")
        ).lower()
        role = str(data.get("role") or "").lower()
        element_type = str(data.get("type") or "").lower()
        input_type = str(data.get("input_type") or "").lower()
        editable = role in {"textbox", "searchbox", "combobox"} or element_type in {"input", "textarea"} or input_type == "contenteditable"
        button_like = role == "button" or element_type == "button"
        if (
            not state["contact_search_selector"]
            and (
                (editable and any(term in label for term in ("search", "contact", "recipient")))
                or "start new chat" in label
            )
        ):
            state["contact_search_selector"] = selector
        if not state["message_selector"] and editable and any(term in label for term in ("type a message", "message", "compose")):
            state["message_selector"] = selector
        if (
            not state["file_selector"]
            and (button_like or input_type == "file")
            and any(term in label for term in ("attach", "attachment", "file", "document", "upload"))
        ):
            state["file_selector"] = selector
    return state


def _first_matching_phrase(text: str, phrases: tuple[str, ...]) -> str:
    return next((phrase for phrase in phrases if phrase in text), "")


def _deterministic_knowledge_report_response(
    *,
    session_id: str,
    knowledge_snapshot: Any,
    orchestrator_snapshot: Any = None,
) -> AnalyzeResponse | None:
    if knowledge_snapshot is None:
        return None
    report = getattr(knowledge_snapshot, "report_artifact", None)
    if report is None or getattr(report, "completion_status", "") != "complete":
        return None
    completion_status = dict(getattr(knowledge_snapshot, "completion_status", {}) or {})
    research_spec = getattr(knowledge_snapshot, "research_spec", None)
    if research_spec is None:
        return None
    if not (
        bool(completion_status.get("source_count"))
        and bool(completion_status.get("extract"))
        and bool(completion_status.get("report"))
    ):
        return None
    required_source_count = int(getattr(research_spec, "source_count", 1) or 1)
    if orchestrator_snapshot is not None:
        opened_source_count = _distinct_non_search_opened_source_count(orchestrator_snapshot)
        if opened_source_count < required_source_count:
            return None
    if _distinct_non_search_source_count(knowledge_snapshot) < required_source_count:
        return None
    content = str(getattr(report, "content", "") or "").strip()
    if not content:
        return None
    return AnalyzeResponse(
        session_id=session_id,
        analysis="Knowledge Extraction produced a complete evidence-backed report. Planner fallback was not invoked.",
        outcome_kind="report",
        clarification_question=None,
        report=ReportOutcome(
            answer=content,
            claim="Required sources were read and the requested output artifact was generated from extraction records.",
        ),
        replan=None,
        suggested_actions=[],
        sgv_verified=True,
        goal_convergence=True,
        backend_authoritative_report=True,
    )


def _distinct_non_search_source_count(knowledge_snapshot: Any) -> int:
    urls: set[str] = set()
    for read in list(getattr(knowledge_snapshot, "read_artifacts", []) or []):
        normalized = _normalize_url_for_read(str(getattr(read, "canonical_url", "") or ""))
        if normalized and not _is_search_provider_or_results_url(normalized):
            urls.add(normalized)
    for record in list(getattr(knowledge_snapshot, "extraction_records", []) or []):
        normalized = _normalize_url_for_read(str(getattr(record, "source_page", "") or ""))
        if normalized and not _is_search_provider_or_results_url(normalized):
            urls.add(normalized)
    return len(urls)


def _distinct_non_search_opened_source_count(orchestrator_snapshot: Any) -> int:
    urls = {
        normalized
        for url in list(getattr(getattr(orchestrator_snapshot, "artifacts", None), "opened_pages", []) or [])
        for normalized in [_normalize_url_for_read(str(url or ""))]
        if normalized and not _is_search_provider_or_results_url(normalized)
    }
    return len(urls)


def _is_search_provider_or_results_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"google.com", "bing.com", "duckduckgo.com"}:
        return True
    return _is_search_results_url(url)


def _deterministic_open_phase_response(
    *,
    session_id: str,
    orchestrator_snapshot: Any,
) -> AnalyzeResponse | None:
    if orchestrator_snapshot is None or orchestrator_snapshot.active_phase.name != "OPEN":
        return None
    target = int(orchestrator_snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    current = int(orchestrator_snapshot.progress_ledger.current_counts.get("opened_pages", 0) or 0)
    if current >= target:
        return None
    opened_urls = {_normalize_url_for_read(url) for url in list(getattr(orchestrator_snapshot.artifacts, "opened_pages", []) or [])}
    entity = _first_unopened_collected_source(session_id, opened_urls=opened_urls)
    if entity is None or not entity.canonical_url:
        return None

    from app.schemas.response import SuggestedAction

    action = SuggestedAction(
        action_id=f"blueprint_open_collected_{entity.entity_id[-12:]}",
        action_type="open_new_tab",
        target_selector="",
        value=entity.canonical_url,
        description=f"Open collected source: {entity.title or entity.canonical_url}",
        reasoning=(
            "Mission Blueprint OPEN phase is below its source target, so execution continues from a durable "
            f"collected source entity_id={entity.entity_id} instead of planner fallback."
        ),
        confidence=max(0.0, min(1.0, float(entity.confidence or 0.86))),
        safety_level="safe",
    )
    return AnalyzeResponse(
        session_id=session_id,
        analysis=(
            "Mission Blueprint continued OPEN phase from durable collected source entities. "
            "Planner fallback was not invoked."
        ),
        outcome_kind="act",
        suggested_actions=[action],
    )


def _first_unopened_collected_source(session_id: str, *, opened_urls: set[str]):
    from app.browser_url_policy import is_openable_browser_url
    from app.runtime_state_manager.entity_binding import list_entities

    entities = [
        entity
        for entity in list_entities(session_id)
        if entity.canonical_url
        and entity.state != "INVALID"
        and entity.entity_type in {"search_result", "semantic_element", "link", "card", "list_item", "table_row"}
        and is_openable_browser_url(entity.canonical_url)
        and _normalize_url_for_read(entity.canonical_url) not in opened_urls
    ]
    if not entities:
        return None
    return sorted(
        entities,
        key=lambda entity: (
            _entity_rank(entity),
            0 if entity.entity_type == "search_result" else 1,
            -float(entity.confidence or 0.0),
            entity.title,
            entity.entity_id,
        ),
    )[0]


def _entity_rank(entity: Any) -> int:
    try:
        return int((entity.metadata or {}).get("rank") or 9999)
    except (TypeError, ValueError):
        return 9999


def _deterministic_read_phase_response(
    *,
    db: Session,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
    runtime_state_snapshot: Any,
    knowledge_snapshot: Any,
    mission_completion_snapshot: Any,
    orchestrator_snapshot: Any,
) -> AnalyzeResponse | None:
    if orchestrator_snapshot is None:
        return None
    active_phase = str(getattr(orchestrator_snapshot.active_phase, "name", "") or "")
    if active_phase not in {"READ", "EXTRACT", "VALIDATE", "SYNTHESIZE", "REPORT"}:
        return None
    opened = _dedupe_opened_source_urls(list(getattr(orchestrator_snapshot.artifacts, "opened_pages", []) or []))
    if not opened:
        return None
    target = int(orchestrator_snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    required = max(1, min(target, len(opened)))
    read_urls = {
        _normalize_url_for_read(getattr(read, "canonical_url", ""))
        for read in list(getattr(knowledge_snapshot, "read_artifacts", []) or [])
    }
    read_urls.update(_read_urls_from_prior_steps(prior_steps))
    read_urls.discard("")
    opened_identities = {_normalize_url_for_read(url): url for url in opened}
    if len(read_urls.intersection(opened_identities.keys())) >= required:
        return None

    current_url = str(getattr(page_context, "url", "") or "")
    current_identity = _normalize_url_for_read(current_url)
    if current_identity and current_identity in opened_identities and current_identity not in read_urls:
        return _execute_read_page_intent(
            db=db,
            session_id=session_id,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
            runtime_state_snapshot=runtime_state_snapshot,
            knowledge_snapshot=knowledge_snapshot,
            mission_completion_snapshot=mission_completion_snapshot,
            orchestrator_snapshot=orchestrator_snapshot,
        )

    next_url = next((url for url in opened if _normalize_url_for_read(url) not in read_urls), opened[0])
    return _execute_focus_source_intent(
        db=db,
        session_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
        runtime_state_snapshot=runtime_state_snapshot,
        knowledge_snapshot=knowledge_snapshot,
        mission_completion_snapshot=mission_completion_snapshot,
        orchestrator_snapshot=orchestrator_snapshot,
        next_url=next_url,
    )


def _read_urls_from_prior_steps(prior_steps: list[Any]) -> set[str]:
    urls: set[str] = set()
    for step in prior_steps:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        action_type = str(data.get("action_type") or "").lower()
        if action_type not in {"read_page", "focus_existing_tab", "switch_tab"}:
            continue
        result = str(data.get("execution_result") or "").lower()
        if "success" not in result and "completed" not in result and "intent execution queue completed" not in result:
            continue
        for value in (data.get("page_url"), data.get("value"), data.get("description")):
            normalized = _normalize_url_for_read(_first_http_url(str(value or "")) or str(value or ""))
            if normalized:
                urls.add(normalized)
    return urls


def _first_http_url(value: str) -> str:
    match = re.search(r"https?://[^\s<>'\"]+", value or "", flags=re.IGNORECASE)
    return match.group(0).rstrip("),.;]") if match else ""


def _normalize_browser_action_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(payload or {})
    action_type = str(normalized.get("action_type") or "").lower()
    selector = str(normalized.get("selector") or normalized.get("target_selector") or "")
    if action_type in {"navigate", "open_new_tab"}:
        url = _first_http_url(selector)
        if url and not normalized.get("value"):
            normalized["value"] = url
        if url:
            normalized["target_selector"] = ""
    elif "target_selector" not in normalized and selector:
        normalized["target_selector"] = selector
    return normalized


def _execute_read_page_intent(
    *,
    db: Session,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
    runtime_state_snapshot: Any,
    knowledge_snapshot: Any,
    mission_completion_snapshot: Any,
    orchestrator_snapshot: Any,
) -> AnalyzeResponse | None:
    from app.intent_runtime import ExecutionContext, dispatch_intent, execute_intent_queue
    from app.services import mission_ledger_service

    current_url = str(getattr(page_context, "url", "") or "")
    directive = dispatch_intent(
        intent="read_page",
        payload={
            "action_type": "read_page",
            "description": f"Read opened source page: {current_url}",
            "reasoning": "Deterministic READ phase continuation reads the focused opened source before planner fallback.",
            "confidence": 0.9,
            "safety_level": "safe",
            "mission_id": session_id,
        },
    )
    if directive is None:
        return None
    directive.mission_id = session_id
    execution_context = ExecutionContext(
        mission_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
        runtime_state=runtime_state_snapshot,
        knowledge=knowledge_snapshot,
        completion_state=mission_completion_snapshot,
        phase_state=orchestrator_snapshot,
        metadata={"source": "deterministic_read_phase_continuation"},
    )
    queue_result = execute_intent_queue(mission_id=session_id, initial_intents=[directive], context=execution_context)
    mission_ledger_service.record_queue_result(db, mission_id=session_id, initial_intent=directive, queue_result=queue_result)
    return AnalyzeResponse(
        session_id=session_id,
        analysis=(
            "Execution Orchestrator continued READ phase deterministically. "
            "Focused source content was read by the backend knowledge pipeline."
        ),
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
        intent_execution=queue_result,
    )


def _execute_focus_source_intent(
    *,
    db: Session,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
    runtime_state_snapshot: Any,
    knowledge_snapshot: Any,
    mission_completion_snapshot: Any,
    orchestrator_snapshot: Any,
    next_url: str,
) -> AnalyzeResponse | None:
    from app.intent_runtime import ExecutionContext, dispatch_intent, execute_intent_queue
    from app.schemas.response import SuggestedAction
    from app.services import mission_ledger_service

    directive = dispatch_intent(
        intent="focus_existing_tab",
        payload={
            "action_type": "focus_existing_tab",
            "target_selector": "",
            "value": f"url:{next_url}",
            "description": f"Focus unread opened source for READ phase: {next_url}",
            "reasoning": "Deterministic READ phase continuation focuses the next unread opened source before planner fallback.",
            "confidence": 0.88,
            "safety_level": "safe",
            "mission_id": session_id,
        },
    )
    if directive is None:
        return None
    directive.mission_id = session_id
    execution_context = ExecutionContext(
        mission_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
        runtime_state=runtime_state_snapshot,
        knowledge=knowledge_snapshot,
        completion_state=mission_completion_snapshot,
        phase_state=orchestrator_snapshot,
        metadata={"source": "deterministic_read_phase_continuation"},
    )
    queue_result = execute_intent_queue(mission_id=session_id, initial_intents=[directive], context=execution_context)
    mission_ledger_service.record_queue_result(db, mission_id=session_id, initial_intent=directive, queue_result=queue_result)
    suggested_actions: list[SuggestedAction] = []
    if queue_result.status in {"waiting_browser", "browser_action_required"} and queue_result.browser_action:
        browser_payload = _normalize_browser_action_payload(queue_result.browser_action)
        suggested_actions = [
            SuggestedAction(
                action_id=str(browser_payload.get("action_id") or browser_payload.get("intent_id") or directive.intent_id),
                intent_id=str(browser_payload.get("intent_id") or directive.intent_id),
                mission_id=session_id,
                action_type=str(browser_payload.get("action_type") or directive.intent),
                target_selector=str(browser_payload.get("target_selector") or ""),
                value=browser_payload.get("value"),
                description=str(browser_payload.get("description") or directive.reason),
                reasoning=str(browser_payload.get("reasoning") or directive.reason),
                confidence=float(browser_payload.get("confidence") or 0.88),
                safety_level=str(browser_payload.get("safety_level") or "safe"),  # type: ignore[arg-type]
            )
        ]
    return AnalyzeResponse(
        session_id=session_id,
        analysis=(
            "Execution Orchestrator continued READ phase deterministically. "
            f"Next unread opened source selected: {next_url}"
        ),
        outcome_kind="act",
        suggested_actions=suggested_actions,
        intent_dispatch=directive,
        intent_execution=queue_result,
    )


def _dedupe_opened_source_urls(urls: list[str]) -> list[str]:
    from app.browser_url_policy import is_openable_browser_url

    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        identity = _normalize_url_for_read(url)
        if not identity or identity in seen or not is_openable_browser_url(url):
            continue
        seen.add(identity)
        result.append(url)
    return result


def _normalize_url_for_read(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}".rstrip("/")


def _is_search_results_url(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"google.com", "bing.com"} and parsed.path.startswith("/search"):
        return True
    if host == "duckduckgo.com" and parsed.query:
        return True
    return False


def _blueprint_node_completed(db: Session, *, mission_id: str, node_id: str) -> bool:
    from app.models.db import MissionIntentRecord

    return (
        db.query(MissionIntentRecord)
        .filter(MissionIntentRecord.mission_id == mission_id)
        .filter(MissionIntentRecord.blueprint_node_id == node_id)
        .filter(MissionIntentRecord.status == "COMPLETED")
        .first()
        is not None
    )


def _search_query_from_task(task: str) -> str:
    text = " ".join(str(task or "").split())
    patterns = (
        r"search\s+for:\s*`([^`]+)`",
        r"search\s+for:\s*['\"]([^'\"]+)['\"]",
        r"search\s+for\s+`([^`]+)`",
        r"search\s+for\s+(.+?)(?:\.|\n|$)",
        r"use\s+google\s+search\s+and\s+official\s+websites\s+to\s+research:\s*`([^`]+)`",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,:;`")
    return ""


def _explicit_url_collection_task(task: str) -> bool:
    text = str(task or "").lower()
    return bool(re.search(r"https?://[^\s<>'\"`]+", text)) and any(
        term in text
        for term in ("collect", "extract", "directory", "entries", "records", "table")
    )


def _normalize_task_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def _runtime_decision_from_response(result: Any) -> tuple[str, str]:
    outcome = str(getattr(result, "outcome_kind", "") or "").lower()
    intent_execution = getattr(result, "intent_execution", None)
    execution_status = str(getattr(intent_execution, "status", "") or "").lower()
    suggested_actions = list(getattr(result, "suggested_actions", []) or [])
    if outcome == "ask" or getattr(result, "clarification_question", None):
        return "REQUEST_USER", str(getattr(result, "clarification_question", "") or "Runtime V1 requested user input.")
    if outcome == "wait":
        return "WAIT", str(getattr(result, "analysis", "") or "Runtime V1 requested wait.")
    if outcome == "replan" or getattr(result, "replan", None) is not None:
        replan = getattr(result, "replan", None)
        return "REPLAN", str(getattr(replan, "reason", "") or getattr(result, "analysis", "") or "Runtime V1 requested replanning.")
    if outcome == "report" or getattr(result, "report", None) is not None:
        return "COMPLETE", str(getattr(result, "analysis", "") or "Runtime V1 produced a report/completion response.")
    if execution_status == "failed":
        return "FAILED", str(getattr(intent_execution, "reason", "") or "Intent Runtime reported failure.")
    if execution_status == "blocked":
        return "BLOCKED", str(getattr(intent_execution, "reason", "") or "Intent Runtime reported blocked.")
    if execution_status == "waiting_external":
        return "WAIT", str(getattr(intent_execution, "reason", "") or "Intent Runtime is waiting on an external condition.")
    if execution_status == "user_interaction_required":
        return "REQUEST_USER", str(getattr(intent_execution, "reason", "") or "Intent Runtime requires user interaction.")
    if suggested_actions or execution_status in {"waiting_browser", "browser_action_required", "succeeded"}:
        return "CONTINUE", str(getattr(result, "analysis", "") or "Runtime V1 produced executable work.")
    return "CONTINUE", str(getattr(result, "analysis", "") or "Runtime V1 continued without terminal decision.")


def _planner_output_budget_projection(result: Any) -> dict[str, Any]:
    actions = []
    for action in list(getattr(result, "suggested_actions", []) or [])[:1]:
        actions.append(
            {
                "action_type": getattr(action, "action_type", ""),
                "target_selector": getattr(action, "target_selector", ""),
                "value": getattr(action, "value", None),
                "description": getattr(action, "description", ""),
                "reasoning": getattr(action, "reasoning", ""),
                "safety_level": getattr(action, "safety_level", ""),
            }
        )
    report = getattr(result, "report", None)
    replan = getattr(result, "replan", None)
    intent_execution = getattr(result, "intent_execution", None)
    return {
        "analysis": str(getattr(result, "analysis", "") or "")[:1200],
        "outcome_kind": getattr(result, "outcome_kind", None),
        "suggested_actions": actions,
        "report": (
            {
                "answer": str(getattr(report, "answer", "") or "")[:1200],
                "claim": str(getattr(report, "claim", "") or "")[:500],
            }
            if report is not None
            else None
        ),
        "replan": (
            {"reason": str(getattr(replan, "reason", "") or "")[:500]}
            if replan is not None
            else None
        ),
        "intent_execution_status": str(getattr(intent_execution, "status", "") or ""),
        "intent_execution_reason": str(getattr(intent_execution, "reason", "") or "")[:500],
    }
