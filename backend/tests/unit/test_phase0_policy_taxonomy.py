from app.policy.phase0_taxonomy import (
    CRITICAL_ACTION_RULES,
    SENSITIVE_DATA_RULES,
    PolicyDisposition,
    export_policy_contract,
    match_critical_actions,
)


def _ids(text: str) -> set[str]:
    return {rule.rule_id for rule in match_critical_actions(text)}


def test_critical_rule_ids_are_unique():
    ids = [rule.rule_id for rule in CRITICAL_ACTION_RULES]
    assert len(ids) == len(set(ids))


def test_sensitive_data_classes_are_unique():
    classes = [rule.data_class for rule in SENSITIVE_DATA_RULES]
    assert len(classes) == len(set(classes))


def test_external_send_requires_confirmation():
    assert "external_communication" in _ids("Send this email to finance@example.com")


def test_purchase_requires_confirmation():
    assert "financial_transaction" in _ids("Place order for INR 4,999")


def test_delete_requires_confirmation():
    assert "destructive_or_irreversible" in _ids("Permanently delete this workspace")


def test_password_and_otp_require_handoff():
    matches = match_critical_actions("Fill the password and OTP fields")
    assert any(rule.rule_id == "credential_or_challenge_entry" for rule in matches)
    assert any(rule.disposition is PolicyDisposition.handoff for rule in matches)


def test_file_upload_is_sensitive_transmission():
    assert "sensitive_data_transmission" in _ids("Upload the provided resume")


def test_plain_read_has_no_critical_match():
    assert match_critical_actions("Read the visible public pricing table") == ()


def test_export_is_json_safe_and_versioned():
    contract = export_policy_contract()
    assert contract["schema_version"] == "phase0.policy-taxonomy.v1"
    assert contract["critical_actions"]
    assert contract["sensitive_data"]
    assert all(isinstance(item["disposition"], str) for item in contract["critical_actions"])
