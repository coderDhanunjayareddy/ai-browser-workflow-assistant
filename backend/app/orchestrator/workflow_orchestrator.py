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

logger = logging.getLogger(__name__)


class WorkflowOrchestrator:
    """Domain-neutral coordination for one browser-assistant session."""

    def __init__(self, session_id: str, db: Session):
        self.session_id = session_id
        self.db = db
        self.state_persistence = StatePersistence(db)
        self.timeline_service = TimelineService(session_id)
        self.budget_manager = BudgetManager(db, session_id)
        self.context_compressor = ContextCompressor()

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

        compressed_context = self.context_compressor.compress(
            task=task,
            page_context=page_context,
            verified_facts=verified_state,
            prior_steps=planner_prior_steps,
            task_constraints=[supplemental_context] if supplemental_context else [],
            cognitive_context=cognitive_context,
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
                logger.info(
                    "SGV: session=%s verified=%s claim=%r",
                    self.session_id,
                    result.sgv_verified,
                    result.report.claim if result.report else "",
                )

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
