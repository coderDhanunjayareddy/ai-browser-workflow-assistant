from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(data: Any, *, length: int = 16) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()[:length]
