"""baseline current ORM schema

Revision ID: 20260802_0001
Revises:
Create Date: 2026-08-02
"""
from __future__ import annotations

from alembic import op

from app.core.database import Base

import app.mission_result.persistence  # noqa: F401
import app.models.db  # noqa: F401
import app.product.models  # noqa: F401


revision = "20260802_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    # Baseline downgrades are intentionally non-destructive for existing deployments.
    pass
