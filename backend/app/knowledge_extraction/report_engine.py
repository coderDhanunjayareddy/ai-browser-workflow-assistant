from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.knowledge_extraction.models import KnowledgeArtifact, ReportArtifact


def generate_report(knowledge: KnowledgeArtifact | None, *, output_format: str = "markdown") -> ReportArtifact | None:
    if knowledge is None:
        return None
    columns = [str(col) for col in knowledge.content.get("columns", [])]
    rows = list(knowledge.content.get("rows", []))
    if output_format == "json":
        content = json.dumps({"columns": columns, "rows": rows}, indent=2)
        fmt = "json"
    elif output_format == "csv":
        content = _csv(columns, rows)
        fmt = "csv"
    else:
        content = _markdown_table(columns, rows)
        fmt = "markdown"
    now = int(time.time() * 1000)
    return ReportArtifact(
        id=_id("report", knowledge.id, content),
        format=fmt,  # type: ignore[arg-type]
        content=content,
        structured={"columns": columns, "rows": rows},
        source_knowledge_id=knowledge.id,
        completion_status="complete" if content else "failed",
        timestamp_ms=now,
    )


def _markdown_table(columns: list[str], rows: list[Any]) -> str:
    if not columns:
        return ""
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        values = [_cell(dict(row).get(column, "")) for column in columns]
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep, *body])


def _csv(columns: list[str], rows: list[Any]) -> str:
    lines = [",".join(columns)]
    for row in rows:
        values = [str(dict(row).get(column, "")).replace('"', '""') for column in columns]
        lines.append(",".join(f'"{value}"' for value in values))
    return "\n".join(lines)


def _cell(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split()).replace("|", "\\|")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _id(*parts: str) -> str:
    return "report_" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
