from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


SHARED_DIR = Path(__file__).resolve().parents[3] / "shared"
MANIFEST_PATH = SHARED_DIR / "v3_capabilities.json"
V4_BROWSER_MANIFEST_PATH = SHARED_DIR / "v4_browser_capabilities.json"


@lru_cache(maxsize=1)
def load_capability_manifest() -> list[dict[str, Any]]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("capability manifest must be a list")
    return data


@lru_cache(maxsize=1)
def load_v4_browser_capability_manifest() -> list[dict[str, Any]]:
    with V4_BROWSER_MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError("v4 browser capability manifest must be a list")
    required = {
        "capability_id",
        "version",
        "category",
        "description",
        "dependencies",
        "feature_flag",
        "maturity_level",
        "target_maturity_level",
        "supported_browsers",
        "supported_websites",
        "benchmarks",
        "metrics",
        "known_limitations",
        "rollout_status",
        "safety_constraints",
        "failure_classes",
        "owner",
    }
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"v4 browser capability at index {index} must be an object")
        missing = required.difference(entry)
        if missing:
            raise ValueError(
                f"v4 browser capability {entry.get('capability_id', index)!r} missing fields: {sorted(missing)}"
            )
    return data
