from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


MISSION_INTENT_OPTIONAL_COLUMNS: dict[str, str] = {
    "blueprint_id": "VARCHAR",
    "blueprint_node_id": "VARCHAR",
    "blueprint_revision": "INTEGER",
}


def ensure_additive_schema(engine: Engine) -> list[str]:
    """Apply idempotent additive schema guards for existing deployments.

    SQLAlchemy ``create_all`` creates missing tables but intentionally does not
    alter existing tables. These guards keep live databases aligned with
    additive ORM fields without changing runtime behavior or deleting data.
    """
    applied: list[str] = []
    inspector = inspect(engine)
    if "mission_intents" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("mission_intents")}
        missing = {
            name: ddl_type
            for name, ddl_type in MISSION_INTENT_OPTIONAL_COLUMNS.items()
            if name not in existing
        }
        if missing:
            with engine.begin() as connection:
                for name, ddl_type in missing.items():
                    connection.execute(text(f"ALTER TABLE mission_intents ADD COLUMN {name} {ddl_type}"))
                    applied.append(f"mission_intents.{name}")
    return applied
