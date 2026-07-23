from __future__ import annotations

from app.capability_platform.browser_registry import certification_status, get_browser_capability
from app.execution_gateway.browser import exec_timeline, metrics, replay, wave4_enterprise
from app.feature_flags import get_flag_state


WAVE4_CAPABILITIES = {
    "browser.adapters.google_workspace": "V4_GOOGLE_WORKSPACE_ADAPTER",
    "browser.adapters.microsoft365": "V4_MICROSOFT365_ADAPTER",
    "browser.adapters.github_advanced": "V4_GITHUB_ADVANCED_ADAPTER",
    "browser.adapters.jira": "V4_JIRA_ADAPTER",
    "browser.adapters.confluence": "V4_CONFLUENCE_ADAPTER",
    "browser.adapters.slack": "V4_SLACK_ADAPTER",
    "browser.adapters.notion": "V4_NOTION_ADAPTER",
    "browser.adapters.figma": "V4_FIGMA_ADAPTER",
    "browser.adapters.canva": "V4_CANVA_ADAPTER",
    "browser.adapters.salesforce": "V4_SALESFORCE_ADAPTER",
    "browser.auth.enterprise_sso": "V4_SSO_AUTH",
    "browser.auth.mfa_otp_handoff": "V4_MFA_OTP_HANDOFF",
    "browser.enterprise_file_workflows": "V4_ENTERPRISE_FILE_WORKFLOWS",
    "browser.site_optimization.framework": "V4_SITE_OPTIMIZATION_FRAMEWORK",
}


def test_wave4_capabilities_registered_certified_and_shadow_flagged():
    for capability_id, flag in WAVE4_CAPABILITIES.items():
        capability = get_browser_capability(capability_id)
        assert capability is not None
        assert capability.feature_flag == flag
        assert capability.maturity_level == 4
        assert capability.target_maturity_level == 4
        assert capability.rollout_status == "beta"
        assert certification_status(capability) == "certified"
        assert get_flag_state(flag).value == "shadow"
        assert capability.benchmarks
        assert capability.metrics


def test_adapter_profiles_and_url_detection_are_deterministic():
    assert wave4_enterprise.parse_payload("plain") == {"text": "plain"}
    assert wave4_enterprise.parse_payload('{"adapter":"jira"}') == {"adapter": "jira"}
    assert wave4_enterprise.adapter_profile("slack").capability_id == "browser.adapters.slack"
    assert wave4_enterprise.adapter_for_url("https://docs.google.com/document/d/1").key == "google_workspace"
    assert wave4_enterprise.adapter_for_url("https://acme.lightning.force.com/lightning/r/Account/1").key == "salesforce"
    assert wave4_enterprise.adapter_for_url("https://example.com") is None


def test_wave4_telemetry_and_replay_certification_hooks():
    metrics._reset_for_testing()
    exec_timeline._reset_for_testing()
    for capability_id in WAVE4_CAPABILITIES:
        metrics.record_capability(capability_id, succeeded=True)
        exec_timeline.record("wave4-exec", capability_id, "completed", detail={"capability": capability_id})
    exported = replay.export_replay("wave4-exec")
    assert exported["validation"]["valid"] is True
    for capability_id in WAVE4_CAPABILITIES:
        assert exported["metrics"]["capability_counts"][capability_id]["succeeded"] == 1
