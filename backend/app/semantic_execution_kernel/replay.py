from __future__ import annotations

from app.semantic_execution_kernel.models import ProgressLedgerEntry


def semantic_replay_frames(ledger: list[ProgressLedgerEntry]) -> list[dict[str, object]]:
    return [
        {
            "frame_id": f"semantic_replay_{index}",
            "semantic_action": entry.semantic_action,
            "entity_id": entry.entity_id,
            "status": entry.status,
            "evidence": entry.evidence[:4],
        }
        for index, entry in enumerate(ledger[-16:], 1)
    ]
