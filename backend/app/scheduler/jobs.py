from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field

from app.contracts.base import VersionedContract
from app.contracts.versions import SCHEDULED_WORK_ITEM_V1


WorkStatus = Literal["pending", "running", "delayed", "completed", "failed", "cancelled"]


class ScheduledWorkItem(VersionedContract):
    schema_version: str = SCHEDULED_WORK_ITEM_V1
    producer: str = "backend.scheduler"
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: str
    status: WorkStatus = "pending"
    dependency_ids: list[str] = Field(default_factory=list)
    earliest_start_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempt: int = 0
    max_attempts: int = 1
    payload: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
