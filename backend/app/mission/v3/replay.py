from __future__ import annotations

import time

from app.contracts.ledger_events import LedgerEvent
from app.mission.v3.fsm import MissionStateMachine
from app.mission.v3.models import MissionSnapshot


def replay_mission(run_id: str, events: list[LedgerEvent]) -> tuple[MissionSnapshot, int]:
    started = time.perf_counter()
    fsm = MissionStateMachine.create(run_id=run_id)
    for event in sorted(events, key=lambda item: (item.step_index, item.created_at, item.event_id)):
        if event.run_id != run_id or event.event_type == "mission.updated":
            continue
        fsm.apply_event(
            event_type=event.event_type,
            payload=event.payload,
            event_id=event.event_id,
            step_index=event.step_index,
        )
    return fsm.clone_snapshot(), int((time.perf_counter() - started) * 1000)
