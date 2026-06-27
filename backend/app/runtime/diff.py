"""
V8.9 Browser Runtime Layer — ContextDiffEngine.

Computes an incremental ContextDiff between two ContextSnapshots so that only
changed context fields ever travel to the backend (instead of the full ReadView).

Pure function. No state. No AI. No network.

Per the 6 cached context fields:
  old=None, new=value     → added
  old=value, new=None     → removed
  old=value, new=value'   → modified (when value != value')
  unchanged               → ignored
"""
from __future__ import annotations

from typing import Optional

from app.runtime.models import CONTEXT_FIELDS, ContextDiff, ContextSnapshot


class ContextDiffEngine:

    def compute(
        self,
        old: Optional[ContextSnapshot],
        new: ContextSnapshot,
    ) -> ContextDiff:
        diff = ContextDiff()

        for fname in CONTEXT_FIELDS:
            new_val = new.field_value(fname)
            old_val = old.field_value(fname) if old is not None else None

            if old_val is None and new_val is None:
                continue
            if old_val is None and new_val is not None:
                diff.added[fname] = new_val
            elif old_val is not None and new_val is None:
                diff.removed[fname] = old_val
            elif old_val != new_val:
                diff.modified[fname] = new_val
            # else unchanged → ignored

        return diff


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = ContextDiffEngine()


def compute(old: Optional[ContextSnapshot], new: ContextSnapshot) -> ContextDiff:
    return _engine.compute(old, new)
