from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class VersionedContract(BaseModel):
    schema_version: str
    producer: str
    created_at: datetime = Field(default_factory=utc_now)
    run_id: str
