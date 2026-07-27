from __future__ import annotations

import os
import sys
from typing import Any


def diagnostic_terminal_enabled(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def safe_print(message: Any, *, flush: bool = True) -> None:
    text = str(message)
    try:
        print(text, flush=flush)
    except UnicodeEncodeError:
        stream = getattr(sys, "stdout", None)
        encoding = getattr(stream, "encoding", None) or "utf-8"
        safe = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace")
        print(safe, flush=flush)
