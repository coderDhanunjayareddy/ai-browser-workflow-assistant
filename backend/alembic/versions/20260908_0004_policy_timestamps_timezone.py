"""make policy timestamps explicitly UTC-aware

Revision ID: 20260908_0004
Revises: 20260802_0003
Create Date: 2026-09-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260908_0004"
down_revision = "20260802_0003"
branch_labels = None
depends_on = None


_POLICY_TIMESTAMP_COLUMNS = {
    "policy_audit_events": ("created_at",),
    "policy_confirmation_receipts": ("created_at", "expires_at", "consumed_at"),
    "policy_origin_grants": ("created_at", "expires_at", "revoked_at"),
}


def upgrade() -> None:
    # Existing naive policy timestamps were produced from UTC-aware application
    # values and persisted by PostgreSQL without their zone. Interpret those
    # stored wall-clock values as UTC while converting to timestamptz.
    for table_name, columns in _POLICY_TIMESTAMP_COLUMNS.items():
        for column_name in columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.DateTime(timezone=False),
                type_=sa.DateTime(timezone=True),
                existing_nullable=column_name in {"consumed_at", "revoked_at"},
                postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    for table_name, columns in _POLICY_TIMESTAMP_COLUMNS.items():
        for column_name in columns:
            op.alter_column(
                table_name,
                column_name,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.DateTime(timezone=False),
                existing_nullable=column_name in {"consumed_at", "revoked_at"},
                postgresql_using=f"{column_name} AT TIME ZONE 'UTC'",
            )
