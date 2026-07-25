from __future__ import annotations

import hashlib
import time
from typing import Any

from app.knowledge_extraction.models import ExtractionRecord, KnowledgeArtifact
from app.knowledge_extraction.validator import validation_summary


def synthesize_knowledge(records: list[ExtractionRecord], required_fields: list[str], task: str) -> KnowledgeArtifact | None:
    valid_records = [record for record in records if record.validation.get("valid")]
    if not valid_records:
        return None
    rows = [{field: record.fields.get(field, "") for field in required_fields} for record in valid_records]
    content: dict[str, Any] = {
        "columns": required_fields,
        "rows": rows,
        "record_count": len(valid_records),
        "task": task[:500],
    }
    artifact_type = "comparison_table" if len(required_fields) > 2 else "summary"
    now = int(time.time() * 1000)
    return KnowledgeArtifact(
        id=_id("knowledge", str(rows), str(now)),
        artifact_type=artifact_type,  # type: ignore[arg-type]
        records=valid_records,
        content=content,
        validation=validation_summary(valid_records),
        timestamp_ms=now,
    )


def _id(*parts: str) -> str:
    return "knowledge_" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
