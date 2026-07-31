from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.cognitive_runtime.comparison_models import DecisionComparison
from app.models.db import CognitiveDecisionComparisonRecord


class DecisionComparisonRepository(ABC):
    @abstractmethod
    def save(self, comparison: DecisionComparison) -> DecisionComparison:
        raise NotImplementedError

    @abstractmethod
    def latest(self, mission_id: str) -> DecisionComparison | None:
        raise NotImplementedError

    @abstractmethod
    def history(self, mission_id: str) -> list[DecisionComparison]:
        raise NotImplementedError

    @abstractmethod
    def disagreements(self, mission_id: str) -> list[DecisionComparison]:
        raise NotImplementedError


class SqlAlchemyDecisionComparisonRepository(DecisionComparisonRepository):
    def __init__(self, db: Session):
        self.db = db

    def save(self, comparison: DecisionComparison) -> DecisionComparison:
        record = CognitiveDecisionComparisonRecord(
            comparison_id=comparison.comparison_id,
            mission_id=comparison.mission_id,
            intent_id=comparison.intent_id,
            blueprint_node_id=comparison.blueprint_node_id,
            runtime_decision=comparison.runtime_decision,
            cognitive_decision=comparison.cognitive_decision,
            agreement=comparison.agreement,
            confidence=comparison.confidence,
            runtime_reason=comparison.runtime_reason,
            cognitive_reason=comparison.cognitive_reason,
            explanation=dict(comparison.explanation),
            comparison_metadata=dict(comparison.metadata),
            created_at=comparison.timestamp,
        )
        self.db.merge(record)
        self.db.commit()
        return comparison

    def latest(self, mission_id: str) -> DecisionComparison | None:
        record = (
            self.db.query(CognitiveDecisionComparisonRecord)
            .filter(CognitiveDecisionComparisonRecord.mission_id == mission_id)
            .order_by(CognitiveDecisionComparisonRecord.created_at.desc())
            .first()
        )
        return _from_record(record) if record is not None else None

    def history(self, mission_id: str) -> list[DecisionComparison]:
        records = (
            self.db.query(CognitiveDecisionComparisonRecord)
            .filter(CognitiveDecisionComparisonRecord.mission_id == mission_id)
            .order_by(CognitiveDecisionComparisonRecord.created_at.asc())
            .all()
        )
        return [_from_record(record) for record in records]

    def disagreements(self, mission_id: str) -> list[DecisionComparison]:
        records = (
            self.db.query(CognitiveDecisionComparisonRecord)
            .filter(CognitiveDecisionComparisonRecord.mission_id == mission_id)
            .filter(CognitiveDecisionComparisonRecord.agreement.in_(["partial", "disagreement"]))
            .order_by(CognitiveDecisionComparisonRecord.created_at.asc())
            .all()
        )
        return [_from_record(record) for record in records]


def _from_record(record: CognitiveDecisionComparisonRecord) -> DecisionComparison:
    return DecisionComparison(
        comparison_id=record.comparison_id,
        mission_id=record.mission_id,
        intent_id=record.intent_id,
        blueprint_node_id=record.blueprint_node_id,
        runtime_decision=record.runtime_decision,
        cognitive_decision=record.cognitive_decision,
        agreement=record.agreement,
        confidence=float(record.confidence or 0.0),
        runtime_reason=record.runtime_reason or "",
        cognitive_reason=record.cognitive_reason or "",
        explanation=dict(record.explanation or {}),
        timestamp=_timestamp(record.created_at),
        metadata=dict(record.comparison_metadata or {}),
    )


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.now(UTC)
