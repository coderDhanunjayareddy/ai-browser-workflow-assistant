"""add mission intent blueprint indexes

Revision ID: 20260802_0003
Revises: 20260802_0002
Create Date: 2026-08-02
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "20260802_0003"
down_revision = "20260802_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("mission_intents")}

    if "ix_mission_intents_blueprint_id" not in existing_indexes:
        op.create_index(
            "ix_mission_intents_blueprint_id",
            "mission_intents",
            ["blueprint_id"],
            unique=False,
        )

    if "ix_mission_intents_blueprint_node_id" not in existing_indexes:
        op.create_index(
            "ix_mission_intents_blueprint_node_id",
            "mission_intents",
            ["blueprint_node_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_indexes = {index["name"] for index in inspector.get_indexes("mission_intents")}

    if "ix_mission_intents_blueprint_node_id" in existing_indexes:
        op.drop_index("ix_mission_intents_blueprint_node_id", table_name="mission_intents")

    if "ix_mission_intents_blueprint_id" in existing_indexes:
        op.drop_index("ix_mission_intents_blueprint_id", table_name="mission_intents")
