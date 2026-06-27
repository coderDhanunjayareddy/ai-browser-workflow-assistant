"""
V8.8 Execution Authorization Framework — Domain models.

ExecutionAuthorization  — The sole entry point for V9.x Execution Gateway.
ExecutionReadinessReport — Mission-level readiness snapshot.

V9.x Execution Gateway MUST accept ONLY ExecutionAuthorization.
It must NEVER read ApprovalRequest, GovernanceContract, or TrustEvaluation.

This module does NOT execute anything.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

EVALUATOR_VERSION:     str   = "1.0"
AUTHORIZATION_TTL:     float = 604800.0   # 7 days (mirrors contract TTL)
TRUST_SCORE_THRESHOLD: float = 0.5        # used in readiness (not in auth outcome)


class AuthorizationStatus(str, Enum):
    active   = "ACTIVE"    # live, usable by V9.x
    denied   = "DENIED"    # contract failed conditions
    expired  = "EXPIRED"   # past expires_at
    revoked  = "REVOKED"   # manually revoked
    consumed = "CONSUMED"  # consumed by V9.x gateway


@dataclass
class ExecutionAuthorization:
    """
    The V8.8 Execution Authorization — sole object the V9.x Execution Gateway may read.

    Produced by AuthorizationEngine when a GovernanceContract satisfies all 6 conditions.
    Authorization outcome is DETERMINISTIC: it depends ONLY on contract state.
    Trust score and mission state are informational (influence reason, not outcome).
    """
    authorization_id:     str
    contract_id:          str
    evaluated_at:         float
    expires_at:           float
    authorized:           bool
    authorization_reason: str
    evaluator_version:    str = EVALUATOR_VERSION
    risk_level:           str = "LOW"
    status:               AuthorizationStatus = AuthorizationStatus.active

    mission_id:     Optional[str]   = None
    task_id:        Optional[str]   = None
    trust_score:    Optional[float] = None

    conditions:     dict[str, bool] = field(default_factory=dict)
    metadata:       dict[str, Any]  = field(default_factory=dict)

    revoked_at:     Optional[float] = None
    revoked_reason: Optional[str]   = None
    consumed_at:    Optional[float] = None

    # ── computed ──────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self.status == AuthorizationStatus.active

    @property
    def is_expired_now(self) -> bool:
        return (
            self.status in (AuthorizationStatus.active, AuthorizationStatus.denied)
            and time.time() > self.expires_at
        )

    @property
    def is_executable(self) -> bool:
        """True only when authorized, ACTIVE, and not yet expired."""
        return (
            self.authorized
            and self.status == AuthorizationStatus.active
            and time.time() <= self.expires_at
        )

    def to_dict(self) -> dict:
        return {
            "authorization_id":     self.authorization_id,
            "contract_id":          self.contract_id,
            "mission_id":           self.mission_id,
            "task_id":              self.task_id,
            "evaluated_at":         self.evaluated_at,
            "expires_at":           self.expires_at,
            "authorized":           self.authorized,
            "authorization_reason": self.authorization_reason,
            "evaluator_version":    self.evaluator_version,
            "risk_level":           self.risk_level,
            "status":               self.status.value,
            "trust_score":          self.trust_score,
            "conditions":           self.conditions,
            "metadata":             self.metadata,
            "revoked_at":           self.revoked_at,
            "revoked_reason":       self.revoked_reason,
            "consumed_at":          self.consumed_at,
            "is_executable":        self.is_executable,
        }


@dataclass
class ExecutionReadinessReport:
    """
    Mission-level readiness snapshot.
    No execution. Read-only assessment of whether execution COULD proceed.
    """
    mission_id:           str
    mission_ready:        bool
    contracts_ready:      int
    approvals_ready:      int
    trust_ready:          bool
    blockers:             list[str]
    readiness_score:      float   # 0.0 to 1.0
    evaluated_at:         float
    active_authorizations:int = 0
    denied_authorizations: int = 0
    executable_tasks:     list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mission_id":            self.mission_id,
            "mission_ready":         self.mission_ready,
            "contracts_ready":       self.contracts_ready,
            "approvals_ready":       self.approvals_ready,
            "trust_ready":           self.trust_ready,
            "blockers":              self.blockers,
            "readiness_score":       self.readiness_score,
            "evaluated_at":          self.evaluated_at,
            "active_authorizations": self.active_authorizations,
            "denied_authorizations": self.denied_authorizations,
            "executable_tasks":      self.executable_tasks,
        }


def make_authorization(
    contract_id:          str,
    authorized:           bool,
    authorization_reason: str,
    risk_level:           str,
    expires_at:           float,
    *,
    mission_id:   Optional[str]   = None,
    task_id:      Optional[str]   = None,
    trust_score:  Optional[float] = None,
    conditions:   Optional[dict]  = None,
    metadata:     Optional[dict]  = None,
) -> ExecutionAuthorization:
    status = AuthorizationStatus.active if authorized else AuthorizationStatus.denied
    return ExecutionAuthorization(
        authorization_id     = str(uuid.uuid4()),
        contract_id          = contract_id,
        evaluated_at         = time.time(),
        expires_at           = expires_at,
        authorized           = authorized,
        authorization_reason = authorization_reason,
        evaluator_version    = EVALUATOR_VERSION,
        risk_level           = risk_level,
        status               = status,
        mission_id           = mission_id,
        task_id              = task_id,
        trust_score          = trust_score,
        conditions           = conditions or {},
        metadata             = metadata or {},
    )
