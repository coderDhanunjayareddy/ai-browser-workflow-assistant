"""
V8.5 Governance Layer — Domain models.

GovernanceContract  — durability record produced when an ApprovalRequest is APPROVED.
EligibilityResult   — deterministic eligibility snapshot (no side-effects).
ExecutionAuthorization — V9.x execution gateway reads ONLY this object.

Governance Layer does NOT execute anything.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any

CONTRACT_TTL_SECONDS: float = 604800.0   # 7 days default
CONTRACT_VERSION:     str   = "1.0"


class ContractStatus(str, Enum):
    active   = "ACTIVE"
    expired  = "EXPIRED"
    revoked  = "REVOKED"
    consumed = "CONSUMED"


@dataclass
class GovernanceContract:
    contract_id:       str
    approval_id:       str
    created_at:        float          # time.time()
    expires_at:        float
    approved:          bool
    approved_by:       str
    approved_at:       float
    source_type:       str            # ApprovalRequest.source_type.value
    source_id:         str            # ApprovalRequest.source_id
    risk_level:        str            # ApprovalRequest.risk_level.value
    contract_version:  str = CONTRACT_VERSION
    execution_allowed: bool = True    # snapshot at creation
    execution_reason:  str = "Approved by human"

    status:          ContractStatus  = ContractStatus.active
    mission_id:      Optional[str]   = None
    task_id:         Optional[str]   = None
    revoked_at:      Optional[float] = None
    revoked_reason:  Optional[str]   = None
    consumed_at:     Optional[float] = None
    metadata:        dict[str, Any]  = field(default_factory=dict)

    # ── computed ─────────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self.status == ContractStatus.active

    @property
    def is_expired_now(self) -> bool:
        return self.status == ContractStatus.active and time.time() > self.expires_at

    @property
    def is_eligible(self) -> bool:
        return (
            self.status  == ContractStatus.active
            and self.approved
            and time.time() <= self.expires_at
        )

    def to_dict(self) -> dict:
        return {
            "contract_id":       self.contract_id,
            "approval_id":       self.approval_id,
            "mission_id":        self.mission_id,
            "task_id":           self.task_id,
            "created_at":        self.created_at,
            "expires_at":        self.expires_at,
            "approved":          self.approved,
            "approved_by":       self.approved_by,
            "approved_at":       self.approved_at,
            "source_type":       self.source_type,
            "source_id":         self.source_id,
            "risk_level":        self.risk_level,
            "contract_version":  self.contract_version,
            "execution_allowed": self.execution_allowed,
            "execution_reason":  self.execution_reason,
            "status":            self.status.value,
            "revoked_at":        self.revoked_at,
            "revoked_reason":    self.revoked_reason,
            "consumed_at":       self.consumed_at,
            "metadata":          self.metadata,
        }


@dataclass
class EligibilityResult:
    """Deterministic eligibility snapshot. No side-effects."""
    eligible:    bool
    contract_id: str
    reason:      str
    checked_at:  float
    conditions:  dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "eligible":    self.eligible,
            "contract_id": self.contract_id,
            "reason":      self.reason,
            "checked_at":  self.checked_at,
            "conditions":  self.conditions,
        }

    def to_authorization(self) -> "ExecutionAuthorization":
        return ExecutionAuthorization(
            contract_id = self.contract_id,
            authorized  = self.eligible,
            reason      = self.reason,
        )


@dataclass
class ExecutionAuthorization:
    """
    V9.x execution gateway reads ONLY this object.
    It must NEVER inspect ApprovalRequest or GovernanceContract directly.
    """
    contract_id: str
    authorized:  bool
    reason:      str
    metadata:    dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "contract_id": self.contract_id,
            "authorized":  self.authorized,
            "reason":      self.reason,
            "metadata":    self.metadata,
        }


def make_contract(
    approval_id:  str,
    approved:     bool,
    approved_by:  str,
    approved_at:  float,
    source_type:  str,
    source_id:    str,
    risk_level:   str,
    *,
    mission_id:   Optional[str]   = None,
    task_id:      Optional[str]   = None,
    ttl_seconds:  float           = CONTRACT_TTL_SECONDS,
    metadata:     Optional[dict]  = None,
) -> GovernanceContract:
    now = time.time()
    allowed = approved
    reason  = "Approved by human" if approved else "Not approved — contract not executable"
    return GovernanceContract(
        contract_id      = str(uuid.uuid4()),
        approval_id      = approval_id,
        mission_id       = mission_id,
        task_id          = task_id,
        created_at       = now,
        expires_at       = now + ttl_seconds,
        approved         = approved,
        approved_by      = approved_by,
        approved_at      = approved_at,
        source_type      = source_type,
        source_id        = source_id,
        risk_level       = risk_level,
        contract_version = CONTRACT_VERSION,
        execution_allowed= allowed,
        execution_reason = reason,
        metadata         = metadata or {},
    )
