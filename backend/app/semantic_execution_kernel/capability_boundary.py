from __future__ import annotations

from app.schemas.response import AnalyzeResponse
from app.semantic_execution_kernel.capability_contracts import compile_capability_request


def bind_capability_contracts(
    response: AnalyzeResponse,
    *,
    session_id: str,
    task: str,
) -> AnalyzeResponse:
    """Compile every browser proposal at the final backend boundary.

    This deliberately runs after all planner, deterministic, recovery, and
    compatibility paths. During migration, unsupported proposals are exposed as
    violations. They are not silently assigned a named-site procedure.
    """
    contracts: list[dict] = []
    violations: list[dict[str, str]] = []
    proposed_actions = list(response.suggested_actions)
    if response.execution_orchestrator:
        proposed_actions.extend(response.execution_orchestrator.continuation_actions)
    seen_action_refs: set[str] = set()
    for index, action in enumerate(proposed_actions):
        action_ref = str(action.intent_id or action.action_id or f"objective-{index + 1}")
        if action_ref in seen_action_refs:
            continue
        seen_action_refs.add(action_ref)
        objective_id = action_ref
        try:
            contract = compile_capability_request(
                action=action,
                mission_id=session_id,
                objective_id=objective_id,
                objective_identity=_declared_identity(action),
                run_id=session_id,
            )
        except (TypeError, ValueError) as exc:
            violations.append({
                "action_id": str(action.action_id),
                "action_type": str(action.action_type),
                "reason": str(exc),
            })
            continue
        contracts.append(contract.model_dump(mode="json"))
    return response.model_copy(update={
        "capability_contracts": contracts,
        "capability_contract_violations": violations,
    })


def _declared_identity(action: object) -> str | None:
    for declaration_name in ("consequential_submission", "content_insertion"):
        declaration = getattr(action, declaration_name, None)
        if not isinstance(declaration, dict):
            continue
        for key in ("destination_entity", "destination_identity", "target_identity"):
            value = declaration.get(key)
            if value:
                return str(value)
    grounding = getattr(action, "grounding", None)
    if isinstance(grounding, dict):
        for key in ("accessible_name", "target_name", "observed_name"):
            value = grounding.get(key)
            if value:
                return str(value)
    return None
