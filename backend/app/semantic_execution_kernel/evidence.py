from __future__ import annotations

from typing import Any


def evidence_for_step(step: Any) -> list[str]:
    data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
    result = str(data.get("execution_result") or "")
    evidence: list[str] = []
    if result.lower().startswith(("success", "clicked", "filled", "navigating", "opened", "waited", "scrolled")):
        evidence.append(f"execution_result:{result[:80]}")
    if data.get("page_url"):
        evidence.append(f"url:{str(data.get('page_url'))[:180]}")
    metadata = data.get("page_metadata") or {}
    if isinstance(metadata, dict):
        for key in ("verification_result", "verified", "download_status", "upload_status"):
            if metadata.get(key):
                evidence.append(f"{key}:{str(metadata[key])[:80]}")
    return evidence


def has_completion_evidence(step: Any) -> bool:
    return bool(evidence_for_step(step))
