from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class RetrySchedule:
    should_retry: bool
    next_attempt_at: datetime | None
    reason: str


def schedule_retry(attempt: int, max_attempts: int, delay_seconds: int = 1) -> RetrySchedule:
    if attempt >= max_attempts:
        return RetrySchedule(False, None, "max_attempts_reached")
    return RetrySchedule(
        True,
        datetime.now(timezone.utc) + timedelta(seconds=max(0, delay_seconds)),
        "retry_scheduled",
    )
