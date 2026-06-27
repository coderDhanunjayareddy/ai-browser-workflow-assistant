"""
V8.5 Governance Layer — ApprovalContractGenerator.

Produces a GovernanceContract when an ApprovalRequest transitions to APPROVED.
Wraps V8.0 ApprovalRequest outputs; does NOT duplicate approval logic.

Safety: No execution. No dispatch. Record only.
"""
from __future__ import annotations

import time
from typing import Optional

from app.governance.models import GovernanceContract, make_contract


def generate_from_approval(approval) -> Optional[GovernanceContract]:
    """
    Generate a GovernanceContract from an approved ApprovalRequest.

    Returns None if the approval is not in APPROVED status.
    The caller is responsible for persisting the returned contract.
    """
    try:
        from app.approvals.models import ApprovalStatus
        if approval.status != ApprovalStatus.approved:
            return None

        resolved_at = approval.resolved_at if approval.resolved_at else time.time()
        resolved_by = approval.resolved_by or "human_via_api"

        return make_contract(
            approval_id = approval.approval_id,
            approved    = True,
            approved_by = resolved_by,
            approved_at = resolved_at,
            source_type = approval.source_type.value,
            source_id   = approval.source_id,
            risk_level  = approval.risk_level.value,
            mission_id  = approval.mission_id,
            task_id     = approval.task_id,
            metadata    = {
                "priority":         approval.priority,
                "approval_title":   approval.title,
                **approval.metadata,
            },
        )
    except Exception:
        return None


def generate_pending_contracts_for_mission(mission_id: str) -> list[GovernanceContract]:
    """
    Scan the ApprovalRegistry for already-approved requests with no contract yet,
    and generate missing GovernanceContracts.
    """
    out: list[GovernanceContract] = []
    try:
        from app.approvals import registry as appr_reg
        from app.approvals.models import ApprovalStatus
        from app.governance import registry as gov_reg

        items = appr_reg.list_for_mission(mission_id, limit=500)
        for item in items:
            if item.status != ApprovalStatus.approved:
                continue
            existing = gov_reg.get_for_approval(item.approval_id)
            if existing is not None:
                continue   # already has a contract
            contract = generate_from_approval(item)
            if contract:
                out.append(contract)
    except Exception:
        pass
    return out
