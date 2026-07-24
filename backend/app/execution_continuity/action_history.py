from __future__ import annotations

import hashlib
import time
from typing import Any

from app.execution_continuity.models import ActionRecord, LoopSignal


SUCCESS_PREFIXES = ("success", "clicked", "filled", "navigating", "waited", "scrolled", "opened")


def build_action_history(prior_steps: list[Any]) -> list[ActionRecord]:
    records: list[ActionRecord] = []
    base_ms = int(time.time() * 1000) - len(prior_steps)
    for index, step in enumerate(prior_steps, 1):
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        action_type = str(data.get("action_type") or "unknown").lower()
        target = str(data.get("target_selector") or data.get("description") or "")
        value = data.get("value")
        page_url = data.get("page_url")
        signature = action_signature(action_type, target, value, page_url)
        records.append(
            ActionRecord(
                index=index,
                action_type=action_type,
                target=target,
                value=str(value) if value is not None else None,
                url=str(page_url) if page_url else None,
                selector_id=_selector_id(target),
                semantic_target=_semantic_target(data),
                timestamp_ms=base_ms + index,
                result=str(data.get("execution_result") or "unknown"),
                verification_result=_verification_result(data),
                signature=signature,
            )
        )
    return records


def action_signature(action_type: str, target: str | None, value: Any, url: str | None) -> str:
    normalized = "|".join([
        _compact(action_type).lower(),
        _compact(target).lower(),
        _compact(value).lower(),
        _compact(url).lower().rstrip("/"),
    ])
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def detect_loop(records: list[ActionRecord]) -> LoopSignal:
    if len(records) < 2:
        return LoopSignal(kind="none", confidence=0.0, reason="not_enough_history")

    recent = records[-6:]
    signatures = [record.signature for record in recent]
    urls = [record.url.rstrip("/") for record in recent if record.url]

    if len(signatures) >= 3 and len(set(signatures[-3:])) == 1:
        return LoopSignal(
            kind="repeat_action",
            confidence=0.96,
            reason="same action signature repeated three times",
            repeated_signature=signatures[-1],
        )

    if len(signatures) >= 4 and signatures[-4] == signatures[-2] and signatures[-3] == signatures[-1]:
        return LoopSignal(
            kind="oscillation",
            confidence=0.9,
            reason="action pattern oscillated A-B-A-B",
            repeated_signature=f"{signatures[-2]}:{signatures[-1]}",
        )

    if len(urls) >= 4 and urls[-4] == urls[-2] and urls[-3] == urls[-1]:
        return LoopSignal(
            kind="repeated_url",
            confidence=0.88,
            reason="browser URL pattern oscillated between two pages",
            repeated_signature=f"{urls[-2]}:{urls[-1]}",
        )

    if len(signatures) >= 4 and len(set(signatures[-4:])) <= 2 and not any(_is_success(record) for record in recent[-4:]):
        return LoopSignal(
            kind="no_progress",
            confidence=0.82,
            reason="recent actions had low variety and no success evidence",
            repeated_signature=signatures[-1],
        )

    return LoopSignal(kind="none", confidence=0.0, reason="progress_not_stalled")


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def _selector_id(target: str) -> str | None:
    if not target:
        return None
    if target.startswith("[data-selector-id="):
        return target.split("=", 1)[-1].strip("]'\"")
    return None


def _semantic_target(data: dict[str, Any]) -> str | None:
    text = str(data.get("description") or "")
    return _compact(text)[:140] or None


def _verification_result(data: dict[str, Any]) -> str | None:
    metadata = data.get("page_metadata") or {}
    if isinstance(metadata, dict):
        value = metadata.get("verification_result") or metadata.get("verified")
        return str(value) if value is not None else None
    return None


def _is_success(record: ActionRecord) -> bool:
    return record.result.lower().startswith(SUCCESS_PREFIXES)
