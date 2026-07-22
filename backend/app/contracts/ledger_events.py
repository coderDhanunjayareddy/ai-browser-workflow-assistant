from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import Field

from app.contracts.base import VersionedContract
from app.contracts.versions import RUN_LEDGER_EVENT_V1


class LedgerEvent(VersionedContract):
    schema_version: str = RUN_LEDGER_EVENT_V1
    producer: str = "backend.v3"
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    step_index: int = 0
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    links: dict[str, Any] = Field(default_factory=dict)
