from __future__ import annotations

import re


def affirmative_task_text(task: str) -> str:
    """Remove explicit negative-action clauses before intent classification.

    A sentence such as "Do not type, attach, or send anything" is a safety
    boundary, not three requested actions. Keeping this normalization shared
    prevents independent planning layers from disagreeing about that intent.
    """
    text = str(task or "").lower()
    return re.sub(
        r"\b(?:do\s+not|don't|never|without)\b[^.!?]*(?:[.!?]|$)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
