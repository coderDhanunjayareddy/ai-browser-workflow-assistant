import logging
import json
import time
from typing import Any

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
from app.evaluation import EvaluationEngine
from app.grounding import GroundingCache, GroundingResolver
from app.grounding.telemetry import record_grounding_metrics
from app.mission.v3 import MissionIntelligenceEngine
from app.policy import GovernanceDecisionEngine
from app.run_ledger.reader import RunLedgerReader
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
        if not is_shadow_or_active("V45_BROWSER_INTELLIGENCE"):
            return None
        try:
            from app.browser_intelligence import build_browser_intelligence

            artifact = build_browser_intelligence(page_context, scope_id=self.session_id)
            _browser_intelligence_artifacts[self.session_id] = artifact
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

        compressed_context = self.context_compressor.compress(
            task=task,
            page_context=page_context,
            verified_facts=verified_state,
            prior_steps=planner_prior_steps,
            task_constraints=[supplemental_context] if supplemental_context else [],
            cognitive_context=cognitive_context,
        )
        if browser_intelligence_artifact is not None and is_active("V45_BROWSER_INTELLIGENCE"):
            from app.browser_intelligence import format_browser_intelligence_for_planner

            compressed_context["browser_intelligence"] = format_browser_intelligence_for_planner(
                browser_intelligence_artifact
            )
        compressed_context = enrich_planner_context(compressed_context, continuity_snapshot)
        self._build_context_packet_shadow(
            task=task,
            page_context=page_context,
            prior_steps=planner_prior_steps,
            supplemental_context=supplemental_context,
            verified_state=verified_state,
            compressed_context=compressed_context,
        )

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
            # without changing budget or analytics contracts.
            token_estimate = ai_service.estimate_tokens(json.dumps(compressed_context))
            token_estimate += ai_service.estimate_tokens(result.model_dump_json())
            record_planner_call(self.db, self.session_id, token_estimate, latency_ms)
            self.budget_manager.consume(tokens=token_estimate)

            # Production SGV Phase 1: validate report claims against live page
            # evidence before returning to the extension.
            # SGV is a validator only — outcome_kind and report are never modified.
            if result.outcome_kind == "report":
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

            return result

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
