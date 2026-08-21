from app.file_upload_broker.policy import build_file_upload_broker_policy


def test_generic_file_remains_local_file_without_assuming_document() -> None:
    policy = build_file_upload_broker_policy("Attach the approved file without sending it.")
    assert policy.schema_version == "content_insertion_broker_policy.v2"
    assert policy.requested_content_kinds == ["local_file"]
    assert policy.requires_user_selected_file is True


def test_content_kinds_are_capabilities_not_provider_names() -> None:
    policy = build_file_upload_broker_policy(
        "Add an image, video, audio, contact, poll, event, sticker, GIF, and emoji."
    )
    assert policy.requested_content_kinds == [
        "image", "video", "audio", "contact", "poll", "event", "sticker", "gif", "emoji"
    ]
    assert "selection_sends_immediately" in policy.supported_effect_classes
    assert "selection_sends_immediately" in policy.confirmation_before_selection_effects


def test_profile_does_not_accidentally_match_file() -> None:
    policy = build_file_upload_broker_policy("Open the member profile.")
    assert policy.requested_content_kinds == ["local_file"]


def test_binding_evidence_covers_content_identity_and_destination_scope() -> None:
    policy = build_file_upload_broker_policy("Attach the synthetic PDF document.")
    for field in (
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
    ):
        assert field in policy.required_evidence

