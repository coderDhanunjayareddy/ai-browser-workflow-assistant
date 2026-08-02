"""convert mission result confidence to double precision

Revision ID: 20260802_0002
Revises: 20260802_0001
Create Date: 2026-08-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260802_0002"
down_revision = "20260802_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "mission_results" not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns("mission_results")}
    confidence = columns.get("confidence")
    if confidence is None:
        return
    if not isinstance(confidence["type"], (sa.Float, sa.Numeric)):
        op.execute(
            """
            ALTER TABLE mission_results
            ALTER COLUMN confidence TYPE DOUBLE PRECISION
            USING COALESCE(NULLIF(confidence, '')::double precision, 0.0)
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "mission_results" not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns("mission_results")}
    confidence = columns.get("confidence")
    if confidence is None:
        return
    if not isinstance(confidence["type"], sa.String):
        op.execute(
            """
            ALTER TABLE mission_results
            ALTER COLUMN confidence TYPE VARCHAR
            USING confidence::varchar
            """
        )
