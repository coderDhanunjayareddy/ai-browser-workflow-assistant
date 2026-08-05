from __future__ import annotations

from urllib.parse import urlparse

from app.knowledge_extraction.models import ExtractionRecord


def validate_records(records: list[ExtractionRecord], required_fields: list[str]) -> list[ExtractionRecord]:
    seen_entities: set[str] = set()
    validated: list[ExtractionRecord] = []
    for record in records:
        failures: list[str] = []
        missing = [field for field in required_fields if not _field_present(record.fields.get(field))]
        if missing:
            failures.append("missing_required_fields:" + ",".join(missing))
        if record.source_page and not _valid_url(record.source_page):
            failures.append("broken_source_url")
        entity_key = _entity_key(record)
        if entity_key in seen_entities:
            failures.append("duplicate_entity")
        seen_entities.add(entity_key)
        if record.confidence < 0.55:
            failures.append("low_confidence")
        validation = {
            "valid": not failures,
            "failures": failures,
            "missing_fields": missing,
            "required_fields": required_fields,
        }
        validated.append(
            ExtractionRecord(
                id=record.id,
                source_page=record.source_page,
                producing_action=record.producing_action,
                producing_phase=record.producing_phase,
                extraction_type=record.extraction_type,
                fields=record.fields,
                confidence=record.confidence,
                validation=validation,
                timestamp_ms=record.timestamp_ms,
                field_evidence=record.field_evidence,
                entity_type=record.entity_type,
                entity=record.entity,
            )
        )
    return validated


def validation_summary(records: list[ExtractionRecord]) -> dict[str, object]:
    failures = [failure for record in records for failure in record.validation.get("failures", [])]
    return {
        "valid": not failures,
        "failure_count": len(failures),
        "failures": failures[:20],
        "valid_record_count": sum(1 for record in records if record.validation.get("valid")),
        "record_count": len(records),
    }


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _entity_key(record: ExtractionRecord) -> str:
    title = next((record.fields.get(key, "") for key in ("tool", "title", "name", "company") if record.fields.get(key)), "")
    return f"{record.extraction_type}|{title.lower()}|{record.source_page.rstrip('/').lower()}"


def _field_present(value: str | None) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text)
