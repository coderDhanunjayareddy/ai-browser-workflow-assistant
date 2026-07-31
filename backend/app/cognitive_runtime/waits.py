from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.cognitive_runtime.models import EvidenceCollection


WAIT_KEYWORDS = {
    "browser": {"browser_wait", "waiting_browser", "page_loading", "tab_pending"},
    "user": {"waiting_user", "clarification_required", "approval_required"},
    "external": {"waiting_external", "external_confirmation", "webhook_pending"},
    "authentication": {"authentication_required", "login_required", "oauth_pending"},
    "file": {"file_pending", "download_pending", "upload_pending"},
    "network": {"network_pending", "request_timeout"},
    "approval": {"approval_required", "approval_pending"},
    "time": {"time_wait", "scheduled_wait", "timer_pending"},
}


@dataclass(frozen=True)
class WaitDiagnostics:
    active_waits: list[dict[str, Any]]
    primary_wait: str | None
    waiting: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WaitStateEvaluator:
    """Classifies wait states without polling or timers."""

    def evaluate(self, evidence: EvidenceCollection) -> WaitDiagnostics:
        waits: list[dict[str, Any]] = []
        for item in evidence.evidence:
            kind = _wait_kind(item.evidence_type)
            if kind is None:
                kind = _wait_kind(str(item.payload.get("wait_type") or item.payload.get("status") or ""))
            if kind is None:
                continue
            waits.append({
                "kind": kind,
                "evidence_id": item.evidence_id,
                "provider": item.provider,
                "reason": item.evidence_type,
            })
        primary = waits[0]["kind"] if waits else None
        return WaitDiagnostics(active_waits=waits, primary_wait=primary, waiting=bool(waits))


def _wait_kind(value: str) -> str | None:
    lowered = str(value).lower()
    for kind, markers in WAIT_KEYWORDS.items():
        if lowered in markers or any(marker in lowered for marker in markers):
            return kind
    return None
