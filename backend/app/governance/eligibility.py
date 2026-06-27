"""
V8.5 Governance Layer — Execution Eligibility Engine.

Pure deterministic eligibility check. No side-effects. No execution.

Rules (ALL must pass):
  R1. contract.status == ACTIVE
  R2. contract.approved == True
  R3. time.time() <= contract.expires_at   (not wall-clock expired)
  R4. contract.status != REVOKED           (not manually revoked)
  R5. contract.status != CONSUMED          (not already consumed by V9.x)

Returns EligibilityResult. V9.x must call to_authorization() on the result
to get an ExecutionAuthorization — the ONLY object V9.x may act on.
"""
from __future__ import annotations

import time

from app.governance.models import (
    GovernanceContract, ContractStatus, EligibilityResult, ExecutionAuthorization,
)


class EligibilityEngine:

    def check(self, contract: GovernanceContract) -> EligibilityResult:
        now = time.time()
        conditions = {
            "is_active":    contract.status == ContractStatus.active,
            "approved":     contract.approved is True,
            "not_expired":  now <= contract.expires_at,
            "not_revoked":  contract.status != ContractStatus.revoked,
            "not_consumed": contract.status != ContractStatus.consumed,
        }
        eligible = all(conditions.values())

        if eligible:
            reason = "All governance conditions satisfied — execution eligible"
        else:
            failed = [k for k, v in conditions.items() if not v]
            reason = f"Eligibility denied: {', '.join(failed)}"

        return EligibilityResult(
            eligible    = eligible,
            contract_id = contract.contract_id,
            reason      = reason,
            checked_at  = now,
            conditions  = conditions,
        )

    def authorize(self, contract: GovernanceContract) -> ExecutionAuthorization:
        """Convenience: check + convert to ExecutionAuthorization in one call."""
        result = self.check(contract)
        return result.to_authorization()


# Module-level singleton
_engine = EligibilityEngine()


def check(contract: GovernanceContract) -> EligibilityResult:
    return _engine.check(contract)


def authorize(contract: GovernanceContract) -> ExecutionAuthorization:
    return _engine.authorize(contract)
