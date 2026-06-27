"""
V8.9 Browser Runtime Layer — RuntimePersistence (feature-flagged stub).

Follows the V7.0 / V8.5 / V8.8 pattern: a disabled-by-default feature flag.
Runtime sessions are transient and in-memory by design — there is intentionally
NO durable persistence in V8.9. This stub exists so a later milestone can flip
the flag without changing call sites.

When RUNTIME_PERSISTENCE = False (default):
  - All session/cache/event state is in-memory only.
  - save/load/delete are no-ops.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.runtime.models import RuntimeSession

# Feature flag — disabled by default.
RUNTIME_PERSISTENCE: bool = False


class RuntimePersistence:
    """No-op persistence facade. Active only if RUNTIME_PERSISTENCE is True."""

    def enabled(self) -> bool:
        return RUNTIME_PERSISTENCE

    def save(self, session: "RuntimeSession") -> None:
        if not RUNTIME_PERSISTENCE:
            return None
        return None

    def load_for_mission(self, mission_id: str) -> list:
        if not RUNTIME_PERSISTENCE:
            return []
        return []

    def delete_for_runtime(self, runtime_id: str) -> int:
        if not RUNTIME_PERSISTENCE:
            return 0
        return 0
