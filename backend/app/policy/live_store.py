from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from app.policy.models import ConfirmationReceipt, OriginGrant, PolicyAuditEvent


class LivePolicyStore:
    """Thread-safe runtime store for narrow grants, receipts, and audit evidence.

    The API never stores action values. Exact action scope is represented only by
    a SHA-256 digest, preventing secrets from entering policy audit records.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._grants: dict[str, OriginGrant] = {}
        self._receipts: dict[str, ConfirmationReceipt] = {}
        self._audit: list[PolicyAuditEvent] = []

    def add_grant(self, grant: OriginGrant) -> None:
        with self._lock:
            self._grants[grant.grant_id] = grant

    def get_grant(self, grant_id: str | None) -> OriginGrant | None:
        if not grant_id:
            return None
        with self._lock:
            return self._grants.get(grant_id)

    def revoke_grant(self, grant_id: str) -> OriginGrant | None:
        with self._lock:
            grant = self._grants.get(grant_id)
            if grant is None or grant.revoked_at is not None:
                return None
            updated = grant.model_copy(update={"revoked_at": datetime.now(timezone.utc)})
            self._grants[grant_id] = updated
            return updated

    def add_receipt(self, receipt: ConfirmationReceipt) -> None:
        with self._lock:
            self._receipts[receipt.receipt_id] = receipt

    def get_receipt(self, receipt_id: str | None) -> ConfirmationReceipt | None:
        if not receipt_id:
            return None
        with self._lock:
            return self._receipts.get(receipt_id)

    def consume_receipt(self, receipt_id: str) -> ConfirmationReceipt | None:
        with self._lock:
            receipt = self._receipts.get(receipt_id)
            if receipt is None or receipt.consumed_at is not None:
                return None
            updated = receipt.model_copy(update={"consumed_at": datetime.now(timezone.utc)})
            self._receipts[receipt_id] = updated
            return updated

    def record(self, event: PolicyAuditEvent) -> None:
        with self._lock:
            self._audit.append(event)

    def audit_for_session(self, session_id: str, *, limit: int = 200) -> list[PolicyAuditEvent]:
        with self._lock:
            return [event for event in self._audit if event.session_id == session_id][-limit:]

    def reset_for_testing(self) -> None:
        with self._lock:
            self._grants.clear()
            self._receipts.clear()
            self._audit.clear()


class SqlAlchemyLivePolicyStore(LivePolicyStore):
    """Durable policy state used by the live API.

    Tests can continue to use ``LivePolicyStore`` directly for deterministic,
    isolated behavior. Database failures propagate so the execution boundary
    fails closed instead of silently downgrading to an in-memory approval.
    """

    def __init__(self, session_factory=None) -> None:
        self._session_factory = session_factory

    def _session(self):
        if self._session_factory is not None:
            return self._session_factory()
        from app.core.database import SessionLocal
        return SessionLocal()

    def add_grant(self, grant: OriginGrant) -> None:
        from app.models.db import PolicyOriginGrantRecord
        with self._session() as db:
            db.add(PolicyOriginGrantRecord(
                grant_id=grant.grant_id,
                session_id=grant.session_id,
                origin=grant.origin,
                action_types=list(grant.action_types),
                issued_by=grant.issued_by,
                created_at=grant.created_at,
                expires_at=grant.expires_at,
                revoked_at=grant.revoked_at,
            ))
            db.commit()

    def get_grant(self, grant_id: str | None) -> OriginGrant | None:
        if not grant_id:
            return None
        from app.models.db import PolicyOriginGrantRecord
        with self._session() as db:
            row = db.get(PolicyOriginGrantRecord, grant_id)
            return self._grant(row) if row else None

    def revoke_grant(self, grant_id: str) -> OriginGrant | None:
        from app.models.db import PolicyOriginGrantRecord
        with self._session() as db:
            row = db.get(PolicyOriginGrantRecord, grant_id)
            if row is None or row.revoked_at is not None:
                return None
            row.revoked_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(row)
            return self._grant(row)

    def add_receipt(self, receipt: ConfirmationReceipt) -> None:
        from app.models.db import PolicyConfirmationReceiptRecord
        with self._session() as db:
            db.add(PolicyConfirmationReceiptRecord(
                receipt_id=receipt.receipt_id,
                session_id=receipt.session_id,
                action_id=receipt.action_id,
                action_digest=receipt.action_digest,
                origin=receipt.origin,
                issued_by=receipt.issued_by,
                created_at=receipt.created_at,
                expires_at=receipt.expires_at,
                consumed_at=receipt.consumed_at,
            ))
            db.commit()

    def get_receipt(self, receipt_id: str | None) -> ConfirmationReceipt | None:
        if not receipt_id:
            return None
        from app.models.db import PolicyConfirmationReceiptRecord
        with self._session() as db:
            row = db.get(PolicyConfirmationReceiptRecord, receipt_id)
            return self._receipt(row) if row else None

    def consume_receipt(self, receipt_id: str) -> ConfirmationReceipt | None:
        from app.models.db import PolicyConfirmationReceiptRecord
        with self._session() as db:
            consumed_at = datetime.now(timezone.utc)
            updated = (
                db.query(PolicyConfirmationReceiptRecord)
                .filter(
                    PolicyConfirmationReceiptRecord.receipt_id == receipt_id,
                    PolicyConfirmationReceiptRecord.consumed_at.is_(None),
                )
                .update({"consumed_at": consumed_at}, synchronize_session=False)
            )
            if updated != 1:
                db.rollback()
                return None
            db.commit()
            row = db.get(PolicyConfirmationReceiptRecord, receipt_id)
            return self._receipt(row)

    def record(self, event: PolicyAuditEvent) -> None:
        from app.models.db import PolicyAuditRecord
        with self._session() as db:
            db.add(PolicyAuditRecord(
                event_id=event.event_id,
                event_type=event.event_type,
                session_id=event.session_id,
                action_id=event.action_id,
                origin=event.origin,
                decision_id=event.decision_id,
                policy_decision=event.policy_decision,
                reason=event.reason,
                metadata_json=dict(event.metadata),
                created_at=event.created_at,
            ))
            db.commit()

    def audit_for_session(self, session_id: str, *, limit: int = 200) -> list[PolicyAuditEvent]:
        from app.models.db import PolicyAuditRecord
        with self._session() as db:
            rows = (
                db.query(PolicyAuditRecord)
                .filter(PolicyAuditRecord.session_id == session_id)
                .order_by(PolicyAuditRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                PolicyAuditEvent(
                    event_id=row.event_id,
                    event_type=row.event_type,
                    session_id=row.session_id,
                    action_id=row.action_id,
                    origin=row.origin,
                    decision_id=row.decision_id,
                    policy_decision=row.policy_decision,
                    reason=row.reason,
                    metadata=dict(row.metadata_json or {}),
                    created_at=row.created_at,
                )
                for row in reversed(rows)
            ]

    @staticmethod
    def _grant(row) -> OriginGrant:
        return OriginGrant(
            grant_id=row.grant_id,
            session_id=row.session_id,
            origin=row.origin,
            action_types=list(row.action_types or []),
            issued_by=row.issued_by,
            created_at=row.created_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )

    @staticmethod
    def _receipt(row) -> ConfirmationReceipt:
        return ConfirmationReceipt(
            receipt_id=row.receipt_id,
            session_id=row.session_id,
            action_id=row.action_id,
            action_digest=row.action_digest,
            origin=row.origin,
            issued_by=row.issued_by,
            created_at=row.created_at,
            expires_at=row.expires_at,
            consumed_at=row.consumed_at,
        )


live_policy_store = SqlAlchemyLivePolicyStore()
