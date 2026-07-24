from __future__ import annotations

from typing import Any

from app.execution_continuity.goal_tracker import build_mission_progress
from app.execution_continuity.models import MissionProgress


class MissionProgressTracker:
    def build(self, task: str, prior_steps: list[Any]) -> MissionProgress:
        return build_mission_progress(task, prior_steps)
