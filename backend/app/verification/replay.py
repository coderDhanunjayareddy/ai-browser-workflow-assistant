from __future__ import annotations

import time

from app.verification.models import ValidationObject


def replay_validation(validation: ValidationObject) -> tuple[ValidationObject, int]:
    """Reconstruct a Validation Object from persisted evidence.

    V3.4 stores the deterministic evidence and result together; replay validates
    serialization stability without re-reading live browser state.
    """
    started = time.perf_counter()
    replayed = ValidationObject.model_validate(validation.model_dump(mode="json"))
    return replayed, int((time.perf_counter() - started) * 1000)
