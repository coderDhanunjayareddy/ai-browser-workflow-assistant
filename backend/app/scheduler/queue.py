from __future__ import annotations

from datetime import datetime, timezone

from app.feature_flags import is_active
from app.scheduler.jobs import ScheduledWorkItem


class InMemorySchedulerQueue:
    """Inactive V3.0 scheduler queue abstraction.

    Queue mutation is allowed for tests and future consumers, but production
    workflow must not route through it until V3_SCHEDULER is active.
    """

    def __init__(self):
        self._items: dict[str, ScheduledWorkItem] = {}

    def enqueue(self, item: ScheduledWorkItem) -> ScheduledWorkItem:
        self._items[item.id] = item
        return item

    def due_items(self, now: datetime | None = None) -> list[ScheduledWorkItem]:
        if not is_active("V3_SCHEDULER"):
            return []
        current = now or datetime.now(timezone.utc)
        return [
            item for item in self._items.values()
            if item.status in {"pending", "delayed"} and item.earliest_start_at <= current
        ]

    def get(self, item_id: str) -> ScheduledWorkItem | None:
        return self._items.get(item_id)

    def mark(self, item_id: str, status: str) -> ScheduledWorkItem | None:
        item = self._items.get(item_id)
        if item is None:
            return None
        item.status = status  # type: ignore[assignment]
        item.updated_at = datetime.now(timezone.utc)
        return item
