from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileUploadBrokerPolicy:
    schema_version: str
    requires_user_selected_file: bool
    allowed_file_kinds: list[str] = field(default_factory=list)
    blocked_followup_actions: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_file_upload_broker_policy(task: str) -> FileUploadBrokerPolicy:
    text = " ".join(str(task or "").split()).lower()
    allowed = []
    if "pdf" in text:
        allowed.append("pdf")
    if any(term in text for term in ("image", "png", "jpg", "jpeg")):
        allowed.append("image")
    if any(term in text for term in ("csv", "spreadsheet")):
        allowed.append("spreadsheet")
    if not allowed:
        allowed.append("user_selected_file")
    return FileUploadBrokerPolicy(
        schema_version="file_upload_broker_policy.v1",
        requires_user_selected_file=True,
        allowed_file_kinds=allowed,
        blocked_followup_actions=["payment", "checkout", "delete", "send_message", "public_submit_without_upload_acceptance"],
        required_evidence=[
            "upload_target_selector",
            "upload_backed_by_file_input",
            "filename",
            "upload_files_count",
            "upload_accepted",
            "upload_status_text",
            "result_page_path",
        ],
    )
