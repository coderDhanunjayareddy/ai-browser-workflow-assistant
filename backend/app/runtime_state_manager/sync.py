from __future__ import annotations

import time
from typing import Any

from app.runtime_state_manager.models import RuntimeTab, RuntimeWindow
from app.runtime_state_manager.registry import BrowserRuntimeRegistry


def synchronize_runtime(
    registry: BrowserRuntimeRegistry,
    *,
    session_id: str,
    page_context: Any,
    prior_steps: list[Any],
) -> tuple[list[RuntimeWindow], list[RuntimeTab], int]:
    started = time.perf_counter()
    windows, tabs = registry.synchronize(session_id, page_context, prior_steps)
    return windows, tabs, int((time.perf_counter() - started) * 1000)
