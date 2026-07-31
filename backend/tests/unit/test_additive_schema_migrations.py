from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.core.schema_migrations import ensure_additive_schema


def test_additive_schema_adds_missing_mission_intent_blueprint_columns():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE mission_intents (intent_id VARCHAR PRIMARY KEY, mission_id VARCHAR NOT NULL)"))

        applied = ensure_additive_schema(engine)
        columns = {column["name"] for column in inspect(engine).get_columns("mission_intents")}
        applied_again = ensure_additive_schema(engine)

        assert {"blueprint_id", "blueprint_node_id", "blueprint_revision"} <= columns
        assert set(applied) == {
            "mission_intents.blueprint_id",
            "mission_intents.blueprint_node_id",
            "mission_intents.blueprint_revision",
        }
        assert applied_again == []
    finally:
        engine.dispose()
