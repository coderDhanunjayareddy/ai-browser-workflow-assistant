"""
V6.5 Trust Engine — Domain Models.

Pure Python dataclasses + enums. No Pydantic, no DB.
All trust evaluations are ADVISORY ONLY — they never approve actions,
never bypass existing approval flows, never execute anything.

Safety contract:
  Trust informs decisions.
  Humans still make decisions.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Risk taxonomy ─────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    """Deterministic risk classification for any platform target or action."""
    low      = "LOW"       # read, research, compare — no external side-effects
    medium   = "MEDIUM"    # click, fill, navigate — reversible side-effects
    high     = "HIGH"      # send, share, email — hard-to-reverse external actions
    critical = "CRITICAL"  # purchase, delete, payment — irreversible external actions


RISK_LEVEL_ORDER: dict[RiskLevel, int] = {
    RiskLevel.low: 0, RiskLevel.medium: 1,
    RiskLevel.high: 2, RiskLevel.critical: 3,
}


def max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher of two risk levels."""
    return a if RISK_LEVEL_ORDER[a] >= RISK_LEVEL_ORDER[b] else b


# ── Target taxonomy ───────────────────────────────────────────────────────────

class TargetType(str, Enum):
    """What kind of entity is being evaluated."""
    mission  = "MISSION"
    task     = "TASK"
    workflow = "WORKFLOW"
    tab      = "TAB"
    action   = "ACTION"


# ── Core evaluation ───────────────────────────────────────────────────────────

@dataclass
class TrustEvaluation:
    """
    Advisory trust evaluation for a platform target.

    NEVER auto-approves. NEVER mutates state. NEVER executes actions.
    All fields are read-only advisory outputs.
    """
    evaluation_id:     str
    target_type:       TargetType
    target_id:         str
    trust_score:       float           # 0.0 (no trust) – 1.0 (full trust)
    risk_level:        RiskLevel
    approval_required: bool            # advisory recommendation only
    confidence:        float           # 0.0–1.0 confidence in this evaluation
    reasoning:         str             # human-readable explanation
    created_at:        datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "evaluation_id":     self.evaluation_id,
            "target_type":       self.target_type.value,
            "target_id":         self.target_id,
            "trust_score":       round(self.trust_score, 3),
            "risk_level":        self.risk_level.value,
            "approval_required": self.approval_required,
            "confidence":        round(self.confidence, 3),
            "reasoning":         self.reasoning,
            "created_at":        self.created_at.isoformat(),
        }


def make_evaluation(
    target_type:       TargetType,
    target_id:         str,
    trust_score:       float,
    risk_level:        RiskLevel,
    approval_required: bool,
    confidence:        float,
    reasoning:         str,
) -> TrustEvaluation:
    """Factory: create a TrustEvaluation with a generated ID."""
    return TrustEvaluation(
        evaluation_id     = str(uuid.uuid4())[:12],
        target_type       = target_type,
        target_id         = target_id,
        trust_score       = max(0.0, min(1.0, trust_score)),
        risk_level        = risk_level,
        approval_required = approval_required,
        confidence        = max(0.0, min(1.0, confidence)),
        reasoning         = reasoning,
    )


# ── V7.5 Controlled Autonomy Contract (no implementation yet) ─────────────────

@dataclass
class TrustDecisionContract:
    """
    V7.5 Controlled Autonomy — pre-agreed decision boundary.

    Defines what the system is allowed to do without user approval,
    given a specific trust evaluation. This contract is created by the human
    operator; it is NEVER created autonomously.

    No autonomy in V6.5. This class documents the agreed shape so V7.5
    can begin without architecture redesign.
    """
    contract_id:              str
    evaluation_id:            str            # which TrustEvaluation this governs
    allowed_without_approval: bool = False   # always False in V6.5
    requires_user_approval:   bool = True    # always True in V6.5
    risk_level:               RiskLevel = RiskLevel.critical
    trust_score:              float = 0.0
    created_at:               datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "contract_id":              self.contract_id,
            "evaluation_id":            self.evaluation_id,
            "allowed_without_approval": self.allowed_without_approval,
            "requires_user_approval":   self.requires_user_approval,
            "risk_level":               self.risk_level.value,
            "trust_score":              self.trust_score,
        }
