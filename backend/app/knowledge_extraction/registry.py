from __future__ import annotations

import threading

from app.knowledge_extraction.models import ExtractionRecord, PageReadArtifact


class ExtractionRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reads: dict[str, list[PageReadArtifact]] = {}
        self._records: dict[str, list[ExtractionRecord]] = {}

    def merge(self, session_id: str, read: PageReadArtifact, records: list[ExtractionRecord]) -> tuple[list[PageReadArtifact], list[ExtractionRecord], int]:
        with self._lock:
            reads = [*self._reads.get(session_id, []), read]
            deduped_reads = _dedupe_reads(reads)
            existing = self._records.get(session_id, [])
            merged = _dedupe_records([*existing, *records])
            duplicates = len(existing) + len(records) - len(merged)
            self._reads[session_id] = deduped_reads[-50:]
            self._records[session_id] = merged[-200:]
            return self._reads[session_id], self._records[session_id], max(duplicates, 0)

    def invalidate(self, session_id: str, record_id: str) -> None:
        with self._lock:
            self._records[session_id] = [record for record in self._records.get(session_id, []) if record.id != record_id]

    def get_records(self, session_id: str) -> list[ExtractionRecord]:
        with self._lock:
            return list(self._records.get(session_id, []))


def _dedupe_reads(reads: list[PageReadArtifact]) -> list[PageReadArtifact]:
    seen: set[str] = set()
    result: list[PageReadArtifact] = []
    for read in reads:
        key = read.canonical_url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(read)
    return result


def _dedupe_records(records: list[ExtractionRecord]) -> list[ExtractionRecord]:
    by_key: dict[str, ExtractionRecord] = {}
    for record in records:
        item_key = str(record.entity.get("item_key") or "") if isinstance(record.entity, dict) else ""
        if item_key:
            key = f"{record.extraction_type}|collection_item|{item_key}"
        else:
            title = next((record.fields.get(key, "") for key in ("tool", "title", "name", "company") if record.fields.get(key)), "")
            key = f"{record.extraction_type}|{record.source_page.rstrip('/').lower()}|{title.lower()}"
        existing = by_key.get(key)
        if existing is None or record.confidence >= existing.confidence:
            by_key[key] = record
    return list(by_key.values())
