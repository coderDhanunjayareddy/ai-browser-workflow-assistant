from __future__ import annotations

import hashlib
from typing import Any

from app.runtime_state_manager.models import RuntimeArtifact


def build_runtime_artifacts(page_context: Any, prior_steps: list[Any]) -> list[RuntimeArtifact]:
    artifacts: list[RuntimeArtifact] = []
    for index, step in enumerate(prior_steps, 1):
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        action_type = str(data.get("action_type") or "")
        result = str(data.get("execution_result") or "")
        page_url = str(data.get("page_url") or "")
        metadata = data.get("page_metadata") or {}
        if action_type == "open_new_tab" and _success(result):
            artifacts.append(_artifact("opened_page", "OPEN", action_type, page_url, {"url": str(data.get("value") or page_url)}, index))
        if action_type in {"fill", "select_option", "choose_date"} and _success(result):
            artifacts.append(_artifact("form_field", "VALIDATE", action_type, page_url, {"selector": str(data.get("target_selector") or "")}, index))
        if isinstance(metadata, dict):
            for key, artifact_type in {
                "download": "download",
                "download_path": "download",
                "uploaded_file": "upload",
                "upload_status": "upload",
                "screenshot": "screenshot",
                "report": "report",
                "validation_result": "validation_result",
            }.items():
                if metadata.get(key):
                    artifacts.append(_artifact(artifact_type, _owner_phase(artifact_type), action_type, page_url, {key: str(metadata[key])}, index))
    for index, block in enumerate(list(getattr(page_context, "content_blocks", []) or [])[:10], 1):
        data = block.model_dump() if hasattr(block, "model_dump") else dict(block)
        text = " ".join(str(data.get("text") or "").split())
        if text:
            artifacts.append(_artifact("visible_record", "READ", "observe", str(getattr(page_context, "url", "") or ""), {"text": text[:240]}, 1000 + index))
    return _dedupe(artifacts)


def _artifact(artifact_type: str, owner_phase: str, action: str, page: str, payload: dict[str, str], index: int) -> RuntimeArtifact:
    raw = f"{artifact_type}|{owner_phase}|{action}|{page}|{payload}|{index}"
    return RuntimeArtifact(
        logical_id=f"artifact_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:12]}",
        artifact_type=artifact_type,
        owner_phase=owner_phase,
        producing_action=action,
        producing_page=page or None,
        validation_status="valid" if payload else "unknown",
        completion_status="complete" if payload else "pending",
        payload=payload,
    )


def _owner_phase(artifact_type: str) -> str:
    return {
        "download": "VALIDATE",
        "upload": "VALIDATE",
        "screenshot": "VALIDATE",
        "report": "REPORT",
        "validation_result": "VALIDATE",
    }.get(artifact_type, "EXTRACT")


def _success(result: str) -> bool:
    return result.lower().startswith(("success", "opened", "clicked", "filled", "navigating", "waited", "scrolled"))


def _dedupe(artifacts: list[RuntimeArtifact]) -> list[RuntimeArtifact]:
    seen: set[str] = set()
    out: list[RuntimeArtifact] = []
    for artifact in artifacts:
        key = f"{artifact.artifact_type}|{artifact.producing_page}|{artifact.payload}"
        if key in seen:
            continue
        seen.add(key)
        out.append(artifact)
    return out
