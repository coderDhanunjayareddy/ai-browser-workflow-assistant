from __future__ import annotations

from typing import Any

from app.semantic_execution_kernel.models import SemanticActionProposal


def loop_prevention_status(proposal: SemanticActionProposal | None, prior_steps: list[Any]) -> dict[str, Any]:
    if proposal is None:
        return {"detected": False, "reason": "no proposal"}
    signatures = [_signature_from_step(step) for step in prior_steps[-6:]]
    current = _proposal_signature(proposal)
    duplicate_count = signatures.count(current)
    oscillation = len(signatures) >= 4 and signatures[-4] == signatures[-2] and signatures[-3] == signatures[-1]
    detected = duplicate_count >= 2 or oscillation
    return {
        "detected": detected,
        "duplicate_count": duplicate_count,
        "oscillation": oscillation,
        "proposal_signature": current,
        "reason": "duplicate proposal or oscillation" if detected else "proposal is not looping",
    }


def _proposal_signature(proposal: SemanticActionProposal) -> str:
    return "|".join([
        proposal.action_type,
        "",
        proposal.parameters.get("value", "").rstrip("/"),
        proposal.parameters.get("selector", ""),
    ]).lower()


def _signature_from_step(step: Any) -> str:
    data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
    return "|".join([
        _semantic_action_type(str(data.get("action_type") or "")),
        "",
        str(data.get("value") or "").rstrip("/"),
        str(data.get("target_selector") or ""),
    ]).lower()


def _semantic_action_type(action_type: str) -> str:
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
    return mapping.get(action_type.lower(), action_type.upper())
