from __future__ import annotations

import time
from typing import Any

from app.mission_completion.models import CompletionDecision, CompletionEvidence


def build_replay(
    *,
    session_id: str,
    decision: CompletionDecision,
    reason: str,
    evidence: CompletionEvidence,
    report_artifact_id: str | None,
) -> list[dict[str, Any]]:
    return [
        {
            "event": "mission_completion.decision",
            "session_id": session_id,
            "decision": decision.value,
            "reason": reason,
            "evidence": evidence.to_dict(),
            "report_artifact_id": report_artifact_id,
            "timestamp_ms": int(time.time() * 1000),
        }
    ]
