from __future__ import annotations

from typing import Any


SUCCESS_PREFIXES = (
    "success",
    "clicked",
    "filled",
    "navigated",
    "navigating",
    "opened",
    "focused",
    "waited",
    "scrolled",
    "intent execution queue completed",
    "backend step completed",
)


def is_successful_execution_result(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith(SUCCESS_PREFIXES)
