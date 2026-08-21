from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileUploadBrokerPolicy:
    schema_version: str
    requires_user_selected_file: bool
    requested_content_kinds: list[str] = field(default_factory=list)
    supported_effect_classes: list[str] = field(default_factory=list)
    confirmation_before_selection_effects: list[str] = field(default_factory=list)
    allowed_file_kinds: list[str] = field(default_factory=list)
    blocked_followup_actions: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_file_upload_broker_policy(task: str) -> FileUploadBrokerPolicy:
    text = " ".join(str(task or "").split()).lower()
    contains = lambda term: re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    requested: list[str] = []
    kind_terms = (
        ("local_file", ("file", "attachment")),
        ("document", ("document", "pdf", "doc", "spreadsheet", "csv")),
        ("image", ("image", "photo", "png", "jpg", "jpeg")),
        ("video", ("video", "mp4")),
        ("audio", ("audio", "voice note", "sound", "mp3", "wav")),
        ("camera", ("camera", "take a photo", "record a video")),
        ("contact", ("contact", "vcard")),
        ("poll", ("poll", "survey")),
        ("event", ("event", "calendar invite")),
        ("sticker", ("sticker",)),
        ("gif", ("gif",)),
        ("emoji", ("emoji", "emoticon")),
    )
    for kind, terms in kind_terms:
        if any(contains(term) for term in terms):
            requested.append(kind)
    if len(requested) > 1 and "local_file" in requested:
        requested.remove("local_file")
    if not requested:
        requested.append("local_file")

    allowed: list[str] = []
    if contains("pdf"):
        allowed.append("pdf")
    if any(contains(term) for term in ("image", "png", "jpg", "jpeg")):
        allowed.append("image")
    if any(contains(term) for term in ("csv", "spreadsheet")):
        allowed.append("spreadsheet")
    if not allowed:
        allowed.append("user_selected_file")
    return FileUploadBrokerPolicy(
        schema_version="content_insertion_broker_policy.v2",
        requires_user_selected_file=any(kind in {"local_file", "document", "image", "video", "audio"} for kind in requested),
        requested_content_kinds=requested,
        supported_effect_classes=[
            "preview_then_send",
            "selection_sends_immediately",
            "inserts_into_composer",
            "structured_draft",
            "device_capture",
        ],
        confirmation_before_selection_effects=["selection_sends_immediately", "device_capture"],
        allowed_file_kinds=allowed,
        blocked_followup_actions=["payment", "checkout", "delete", "send_message", "public_submit_without_upload_acceptance"],
        required_evidence=[
            "upload_target_selector",
            "upload_backed_by_file_input",
            "content_kind",
            "insertion_effect",
            "binding_id",
            "content_sha256",
            "filename",
            "mime_type",
            "size_bytes",
            "destination_origin",
            "destination_entity",
            "idempotency_key",
            "upload_files_count",
            "upload_accepted",
            "upload_status_text",
            "result_page_path",
        ],
    )
