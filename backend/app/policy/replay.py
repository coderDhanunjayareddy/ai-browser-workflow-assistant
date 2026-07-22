from __future__ import annotations

import time

from app.policy.models import GovernanceObject


def replay_governance(governance: GovernanceObject) -> tuple[GovernanceObject, int]:
    started = time.perf_counter()
    replayed = GovernanceObject.model_validate(governance.model_dump(mode="json"))
    return replayed, int((time.perf_counter() - started) * 1000)
