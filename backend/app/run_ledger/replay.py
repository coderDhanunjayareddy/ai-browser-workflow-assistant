from __future__ import annotations

from app.contracts.ledger_events import LedgerEvent


def replay_events(events: list[LedgerEvent]) -> list[LedgerEvent]:
    return sorted(events, key=lambda event: (event.step_index, event.created_at, event.event_id))
