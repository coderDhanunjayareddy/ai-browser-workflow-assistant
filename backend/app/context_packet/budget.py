from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.semantic_page.serializers import stable_json


@dataclass(frozen=True)
class ContextPacketBudget:
    max_entities: int = 12
    max_targets: int = 20
    max_facts: int = 20
    max_controls: int = 20
    max_packet_chars: int = 12000


def trim_items(items: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    if len(items) <= limit:
        return items, 0
    return items[:limit], len(items) - limit


def packet_size_chars(data: Any) -> int:
    return len(stable_json(data))
