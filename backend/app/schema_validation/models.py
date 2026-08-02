from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SchemaSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SchemaComparison:
    object_type: str
    object_name: str
    status: str
    severity: SchemaSeverity
    detail: str
    orm_value: str | None = None
    database_value: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "object_type": self.object_type,
            "object_name": self.object_name,
            "status": self.status,
            "severity": self.severity.value,
            "detail": self.detail,
            "orm_value": self.orm_value,
            "database_value": self.database_value,
        }


@dataclass(frozen=True)
class DriftReport:
    schema_version: str
    database_url_safe: str
    comparisons: list[SchemaComparison] = field(default_factory=list)
    alembic_current: str | None = None
    alembic_head: str | None = None

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.comparisons if item.severity == SchemaSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.comparisons if item.severity == SchemaSeverity.WARNING)

    @property
    def compatible(self) -> bool:
        migration_compatible = self.alembic_head is None or self.alembic_current == self.alembic_head
        return self.error_count == 0 and migration_compatible

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "database_url_safe": self.database_url_safe,
            "alembic_current": self.alembic_current,
            "alembic_head": self.alembic_head,
            "compatible": self.compatible,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "comparisons": [item.to_dict() for item in self.comparisons],
        }

    def to_markdown(self) -> str:
        lines = [
            "# Schema Inventory",
            "",
            f"- Schema version: `{self.schema_version}`",
            f"- Alembic current: `{self.alembic_current or 'unknown'}`",
            f"- Alembic head: `{self.alembic_head or 'unknown'}`",
            f"- Compatible: `{self.compatible}`",
            "",
            "| Object | Status | Severity | ORM | Database | Detail |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in self.comparisons:
            lines.append(
                "| "
                + " | ".join(
                    [
                        item.object_name,
                        item.status,
                        item.severity.value,
                        item.orm_value or "",
                        item.database_value or "",
                        item.detail.replace("|", "\\|"),
                    ]
                )
                + " |"
            )
        return "\n".join(lines) + "\n"
