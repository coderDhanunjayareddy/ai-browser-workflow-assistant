"""
V8.8 Execution Authorization Framework — AuthorizationEngine.

Pure deterministic evaluation. No side-effects. No execution.

Rules (ALL must pass for AUTHORIZED):
  R1. contract.status == ACTIVE
  R2. contract.approved == True
  R3. contract.execution_allowed == True
  R4. contract.status != REVOKED
  R5. contract.status != CONSUMED
  R6. time.time() <= contract.expires_at

Trust score and mission state are contextual only — they influence
authorization_reason but NEVER the authorization outcome.
"""
from __future__ import annotations

import time
from typing import Optional

from app.authorization.models import (
    ExecutionAuthorization, make_authorization, EVALUATOR_VERSION,
)


class AuthorizationEngine:

    VERSION = EVALUATOR_VERSION

    def evaluate(
        self,
        contract,                              # GovernanceContract
        mission_state:  Optional[str]   = None,
        trust_score:    Optional[float] = None,
    ) -> ExecutionAuthorization:
        """
        Deterministically evaluate a GovernanceContract.

        Authorization outcome depends ONLY on contract state.
        mission_state and trust_score are informational.
        """
        from app.governance.models import ContractStatus

        now = time.time()

        conditions: dict[str, bool] = {
            "contract_active":   contract.status == ContractStatus.active,
            "contract_approved": contract.approved is True,
            "execution_allowed": contract.execution_allowed is True,
            "not_revoked":       contract.status != ContractStatus.revoked,
            "not_consumed":      contract.status != ContractStatus.consumed,
            "not_expired":       now <= contract.expires_at,
        }

        authorized = all(conditions.values())

        if authorized:
            reason = "All authorization conditions satisfied"
            if trust_score is not None and trust_score < 0.4:
                reason += f" (Note: low trust score {round(trust_score, 3)})"
            if mission_state and mission_state.upper() not in ("ACTIVE", "RUNNING"):
                reason += f" (Note: mission state is {mission_state})"
        else:
            failed = [k for k, v in conditions.items() if not v]
            reason = f"Authorization denied: {', '.join(failed)}"

        return make_authorization(
            contract_id          = contract.contract_id,
            authorized           = authorized,
            authorization_reason = reason,
            risk_level           = contract.risk_level,
            expires_at           = contract.expires_at,
            mission_id           = contract.mission_id,
            task_id              = contract.task_id,
            trust_score          = trust_score,
            conditions           = conditions,
        )


# Module-level singleton
_engine = AuthorizationEngine()


def evaluate(
    contract,
    mission_state:  Optional[str]   = None,
    trust_score:    Optional[float] = None,
) -> ExecutionAuthorization:
    return _engine.evaluate(contract, mission_state=mission_state, trust_score=trust_score)
