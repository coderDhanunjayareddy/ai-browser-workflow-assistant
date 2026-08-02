from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.sql.schema import Column

from app.core.config import settings
from app.core.database import Base, engine as default_engine
from app.schema_validation.models import DriftReport, SchemaComparison, SchemaSeverity

import app.mission_result.persistence  # noqa: F401
import app.models.db  # noqa: F401
import app.product.models  # noqa: F401


class SchemaValidator:
    def __init__(self, engine: Engine | None = None) -> None:
        self.engine = engine or default_engine

    def compare(self) -> DriftReport:
        inspector = inspect(self.engine)
        db_tables = set(inspector.get_table_names())
        comparisons: list[SchemaComparison] = []

        for table_name, table in sorted(Base.metadata.tables.items()):
            if table_name == "alembic_version":
                continue
            if table_name not in db_tables:
                comparisons.append(
                    SchemaComparison("table", table_name, "MISSING", SchemaSeverity.ERROR, "ORM table is missing from database")
                )
                continue
            comparisons.append(SchemaComparison("table", table_name, "MATCH", SchemaSeverity.INFO, "Table exists"))

            db_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
            orm_columns = {column.name: column for column in table.columns}
            for column_name, orm_column in sorted(orm_columns.items()):
                object_name = f"{table_name}.{column_name}"
                db_column = db_columns.get(column_name)
                if db_column is None:
                    comparisons.append(
                        SchemaComparison("column", object_name, "MISSING", SchemaSeverity.ERROR, "ORM column is missing from database")
                    )
                    continue
                orm_type = _type_name(orm_column)
                db_type = str(db_column["type"]).lower()
                if not _types_compatible(orm_type, db_type):
                    comparisons.append(
                        SchemaComparison(
                            "column",
                            object_name,
                            "TYPE MISMATCH",
                            SchemaSeverity.ERROR,
                            "Column type differs between ORM and database",
                            orm_value=orm_type,
                            database_value=db_type,
                        )
                    )
                else:
                    comparisons.append(
                        SchemaComparison("column", object_name, "MATCH", SchemaSeverity.INFO, "Column type matches", orm_type, db_type)
                    )
                orm_nullable = bool(orm_column.nullable)
                db_nullable = str(db_column.get("nullable", "")).lower() == "true" or bool(db_column.get("nullable"))
                if orm_nullable != db_nullable:
                    comparisons.append(
                        SchemaComparison(
                            "column",
                            object_name,
                            "NULLABILITY MISMATCH",
                            SchemaSeverity.WARNING,
                            "Column nullability differs",
                            orm_value=str(orm_nullable),
                            database_value=str(db_nullable),
                        )
                    )

            for column_name in sorted(set(db_columns) - set(orm_columns)):
                comparisons.append(
                    SchemaComparison("column", f"{table_name}.{column_name}", "EXTRA", SchemaSeverity.WARNING, "Database column has no ORM column")
                )

            comparisons.extend(self._compare_indexes(inspector, table_name))

        for table_name in sorted(db_tables - set(Base.metadata.tables)):
            if table_name == "alembic_version":
                continue
            comparisons.append(
                SchemaComparison("table", table_name, "EXTRA", SchemaSeverity.WARNING, "Database table has no ORM table")
            )

        current, head = self._alembic_versions()
        if head and current != head:
            comparisons.append(
                SchemaComparison(
                    "migration",
                    "alembic_version",
                    "VERSION MISMATCH",
                    SchemaSeverity.ERROR,
                    "Database is not at Alembic head",
                    orm_value=head,
                    database_value=current or "<none>",
                )
            )
        return DriftReport(
            schema_version="schema_validation.v1",
            database_url_safe=_safe_url(settings.database_url),
            comparisons=comparisons,
            alembic_current=current,
            alembic_head=head,
        )

    def _compare_indexes(self, inspector, table_name: str) -> list[SchemaComparison]:
        comparisons: list[SchemaComparison] = []
        db_indexes = {index["name"]: index for index in inspector.get_indexes(table_name)}
        orm_indexes = {
            index.name
            for index in Base.metadata.tables[table_name].indexes
            if index.name
        }
        for index_name in sorted(orm_indexes):
            status = "MATCH" if index_name in db_indexes else "INDEX MISMATCH"
            comparisons.append(
                SchemaComparison(
                    "index",
                    f"{table_name}.{index_name}",
                    status,
                    SchemaSeverity.INFO if status == "MATCH" else SchemaSeverity.WARNING,
                    "Index presence comparison",
                )
            )
        for index_name in sorted(set(db_indexes) - orm_indexes):
            comparisons.append(
                SchemaComparison("index", f"{table_name}.{index_name}", "EXTRA", SchemaSeverity.INFO, "Database index is not declared as explicit ORM Index")
            )
        return comparisons

    def _alembic_versions(self) -> tuple[str | None, str | None]:
        current = None
        try:
            with self.engine.connect() as connection:
                current = MigrationContext.configure(connection).get_current_revision()
        except Exception:
            current = None
        head = None
        try:
            backend_root = Path(__file__).resolve().parents[2]
            config = Config(str(backend_root / "alembic.ini"))
            config.set_main_option("script_location", str(backend_root / "alembic"))
            head = ScriptDirectory.from_config(config).get_current_head()
        except Exception:
            head = None
        return current, head


def _type_name(column: Column) -> str:
    return column.type.compile(dialect=default_engine.dialect).lower()


def _types_compatible(orm_type: str, db_type: str) -> bool:
    aliases = {
        "varchar": {"character varying", "varchar"},
        "string": {"character varying", "varchar"},
        "text": {"text"},
        "integer": {"integer", "int4"},
        "double precision": {"double precision", "float8"},
        "float": {"double precision", "float8", "real"},
        "boolean": {"boolean", "bool"},
        "json": {"json", "jsonb"},
        "timestamp without time zone": {"timestamp without time zone", "timestamp"},
    }
    if orm_type == db_type:
        return True
    for key, values in aliases.items():
        if key in orm_type and db_type in values:
            return True
    return False


def _safe_url(url: str) -> str:
    parsed = urlsplit(url)
    netloc = parsed.hostname or ""
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
