from __future__ import annotations

from typing import Any

from app.runtime_state_manager.execution_result import is_successful_execution_result
from app.semantic_execution_kernel.evidence import evidence_for_step
from app.semantic_execution_kernel.models import ProgressLedgerEntry, SemanticActionProposal


def build_progress_ledger(prior_steps: list[Any], proposal: SemanticActionProposal | None) -> list[ProgressLedgerEntry]:
    entries: list[ProgressLedgerEntry] = []
    for step in prior_steps[-20:]:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        evidence = evidence_for_step(step)
        success = bool(evidence) and is_successful_execution_result(data.get("execution_result"))
        entries.append(
            ProgressLedgerEntry(
                semantic_action=_semantic_from_browser_action(str(data.get("action_type") or "")),
                entity_id=None,
                status="completed" if success else "failed",
                evidence=evidence,
                failure_reason=None if success else str(data.get("execution_result") or "unknown"),
            )
        )
    if proposal is not None:
        entries.append(
            ProgressLedgerEntry(
                semantic_action=proposal.action_type,
                entity_id=proposal.entity_id,
                status="pending",
                evidence=[],
            )
        )
    return entries


def _semantic_from_browser_action(action_type: str) -> str:
    mapping = {
        "navigate": "SEARCH_WEB",
        "open_new_tab": "OPEN_ENTITY",
        "switch_tab": "FOCUS_TAB",
        "focus_existing_tab": "FOCUS_TAB",
        "click": "CLICK_ENTITY",
        "fill": "FILL_FORM",
        "wait": "WAIT_FOR_STATE",
        "scroll": "COLLECT_RESULTS",
    }
    return mapping.get(action_type.lower(), action_type.upper() or "UNKNOWN")
