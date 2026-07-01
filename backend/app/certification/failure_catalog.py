"""
Phase F — Failure Catalog.

A structured, deduplicated knowledge base of every observed certification failure. Keyed
by (category, website, workflow); repeated occurrences update last_seen + count rather
than creating duplicates. This is the project's reliability knowledge base.

Deterministic: callers pass `seen_at` explicitly (no hidden clock), mirroring the rest of
the platform's testable time handling.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional


class Reproducibility:
    always       = "ALWAYS"
    intermittent = "INTERMITTENT"
    once         = "ONCE"


class ResolutionStatus:
    open        = "OPEN"
    mitigated   = "MITIGATED"     # recovered at runtime (deterministic recovery)
    resolved    = "RESOLVED"
    known_limit = "KNOWN_LIMITATION"


@dataclass
class FailureRecord:
    catalog_id:       str
    category:         str
    website:          str
    workflow:         str
    reproducibility:  str
    recovery_outcome: str
    resolution_status: str
    first_seen:       float
    last_seen:        float
    occurrences:      int = 1
    detail:           str = ""
    notes:            list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_id":        self.catalog_id,
            "category":          self.category,
            "website":           self.website,
            "workflow":          self.workflow,
            "reproducibility":   self.reproducibility,
            "recovery_outcome":  self.recovery_outcome,
            "resolution_status": self.resolution_status,
            "first_seen":        self.first_seen,
            "last_seen":         self.last_seen,
            "occurrences":       self.occurrences,
            "detail":            self.detail,
            "notes":             self.notes,
        }


def _key(category: str, website: str, workflow: str) -> str:
    return f"{category}::{website}::{workflow}"


class FailureCatalog:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_key: dict[str, FailureRecord] = {}

    def record(self, *, category: str, website: str, workflow: str, seen_at: float,
               reproducibility: str = Reproducibility.once,
               recovery_outcome: str = "none",
               resolution_status: str = ResolutionStatus.open,
               detail: str = "", note: Optional[str] = None) -> FailureRecord:
        key = _key(category, website, workflow)
        with self._lock:
            rec = self._by_key.get(key)
            if rec is None:
                rec = FailureRecord(
                    catalog_id=f"fail-{len(self._by_key) + 1:04d}",
                    category=category, website=website, workflow=workflow,
                    reproducibility=reproducibility, recovery_outcome=recovery_outcome,
                    resolution_status=resolution_status, first_seen=seen_at, last_seen=seen_at,
                    occurrences=1, detail=detail,
                )
                self._by_key[key] = rec
            else:
                rec.occurrences += 1
                rec.last_seen = seen_at
                rec.recovery_outcome = recovery_outcome
                rec.resolution_status = resolution_status
                if detail:
                    rec.detail = detail
                # repeated occurrence => at least intermittent; promote to always on many hits
                if rec.reproducibility == Reproducibility.once:
                    rec.reproducibility = Reproducibility.intermittent
                if rec.occurrences >= 3:
                    rec.reproducibility = Reproducibility.always
            if note:
                rec.notes.append(note)
            return rec

    def get(self, catalog_id: str) -> Optional[FailureRecord]:
        with self._lock:
            for rec in self._by_key.values():
                if rec.catalog_id == catalog_id:
                    return rec
            return None

    def list_all(self) -> list[FailureRecord]:
        with self._lock:
            return sorted(self._by_key.values(), key=lambda r: r.catalog_id)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            recs = list(self._by_key.values())
        by_category: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for r in recs:
            by_category[r.category] = by_category.get(r.category, 0) + 1
            by_status[r.resolution_status] = by_status.get(r.resolution_status, 0) + 1
        return {
            "total_distinct":   len(recs),
            "total_occurrences": sum(r.occurrences for r in recs),
            "by_category":      by_category,
            "by_resolution":    by_status,
            "records":          [r.to_dict() for r in sorted(recs, key=lambda r: r.catalog_id)],
        }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._by_key.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_catalog = FailureCatalog()


def record(**kwargs) -> FailureRecord:
    return _catalog.record(**kwargs)

def get(catalog_id: str) -> Optional[FailureRecord]:
    return _catalog.get(catalog_id)

def list_all() -> list[FailureRecord]:
    return _catalog.list_all()

def summary() -> dict[str, Any]:
    return _catalog.summary()

def _reset_for_testing() -> None:
    _catalog._reset_for_testing()
