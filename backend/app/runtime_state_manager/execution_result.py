from __future__ import annotations

import re
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
    # The extension appends authoritative outcome markers to adapter-specific
    # messages. CDP dispatch wording is not a legacy success prefix, and a
    # dispatch acknowledgement alone does not prove the intended effect.
    verification = re.findall(r"(?:^|\n)\s*verification:\s*([^\n]+)", text)
    execution = re.findall(r"(?:^|\n)\s*execution:\s*([^\n]+)", text)
    if execution and execution[-1].strip() != "success":
        return False
    if verification:
        return verification[-1].strip() == "verified"
    return text.startswith(SUCCESS_PREFIXES)
