from __future__ import annotations

from app.execution_continuity.models import ActionRecord, ReplayFrame


def build_replay_frames(records: list[ActionRecord]) -> list[ReplayFrame]:
    return [
        ReplayFrame(
            frame_id=f"continuity_frame_{record.index}",
            action_signature=record.signature,
            url=record.url,
            result=record.result,
        )
        for record in records[-12:]
    ]
