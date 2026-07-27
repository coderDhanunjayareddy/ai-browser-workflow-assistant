from __future__ import annotations

from typing import Any

from app.mission_completion.criteria import build_mission_plan as _build_mission_plan
from app.mission_completion.models import MissionPlan


def create_mission_plan(
    *,
    mission_id: str,
    objective: str,
    phase_state: Any = None,
) -> MissionPlan:
    """Mission Intelligence-owned Mission Plan creation entrypoint."""
    return _build_mission_plan(
        mission_id=mission_id,
        objective=objective,
        phase_state=phase_state,
    )
