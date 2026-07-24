from __future__ import annotations

from app.execution_continuity.action_history import detect_loop
from app.execution_continuity.models import ActionRecord, MissionProgress, ProgressValidation


def validate_progress(records: list[ActionRecord], mission: MissionProgress) -> ProgressValidation:
    loop = detect_loop(records)
    recent = records[-5:]
    successful_recent = [record for record in recent if record.result.lower().startswith(("success", "clicked", "filled", "navigating", "opened"))]
    unique_recent = {record.signature for record in recent}
    progress_increased = bool(successful_recent) and (len(unique_recent) > 1 or mission.progress_percent > 0)
    no_progress_count = _no_progress_count(records)

    if loop.detected:
        return ProgressValidation(
            progress_increased=False,
            no_progress_count=no_progress_count,
            loop_signal=loop,
            recommendation="replan",
            reason=loop.reason,
        )
    if no_progress_count >= 3:
        return ProgressValidation(
            progress_increased=False,
            no_progress_count=no_progress_count,
            loop_signal=loop,
            recommendation="recover",
            reason="three recent actions lack completion evidence",
        )
    if no_progress_count:
        return ProgressValidation(
            progress_increased=progress_increased,
            no_progress_count=no_progress_count,
            loop_signal=loop,
            recommendation="retry",
            reason="recent progress evidence is weak",
        )
    return ProgressValidation(
        progress_increased=True,
        no_progress_count=0,
        loop_signal=loop,
        recommendation="continue",
        reason="recent browser evidence indicates progress",
    )


def _no_progress_count(records: list[ActionRecord]) -> int:
    count = 0
    last_signature = None
    for record in reversed(records):
        successful = record.result.lower().startswith(("success", "clicked", "filled", "navigating", "opened"))
        if successful and record.signature != last_signature:
            break
        count += 1
        last_signature = record.signature
    return count
