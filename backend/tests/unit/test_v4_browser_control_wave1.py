from __future__ import annotations

from app.capability_platform.browser_registry import (
    browser_capability_manifest,
    certification_report,
    get_browser_capability,
)
from app.execution_gateway.browser import auth_handoff, capabilities, exec_timeline, replay, smart_waits
from app.feature_flags import get_flag_state, v4_flag_snapshot


class FakeLocator:
    def __init__(self) -> None:
        self.waits: list[tuple[str, int]] = []

    def wait_for(self, *, state: str, timeout: int) -> None:
        self.waits.append((state, timeout))


class FakePage:
    url = "https://example.test"

    def __init__(self, *, auth: bool = False) -> None:
        self.auth = auth
        self.locator_obj = FakeLocator()
        self.wait_count = 0

    def title(self) -> str:
        return "Sign in" if self.auth else "Ready"

    def locator(self, selector: str) -> FakeLocator:
        self.selector = selector
        return self.locator_obj

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_count += 1

    def evaluate(self, script: str):
        if "passwordFields" in script:
            return {
                "text": "Sign in with your password" if self.auth else "Dashboard",
                "passwordFields": 1 if self.auth else 0,
                "otpFields": 0,
                "url": self.url,
                "title": self.title(),
            }
        return {
            "ready_state": "complete",
            "overlay_count": 0,
            "signature": f"{self.url}|{self.title()}|100|5|0",
        }


def test_v4_flags_default_to_safe_states():
    flags = v4_flag_snapshot()
    assert flags["V4_SMART_WAITS"] == "off"
    assert flags["V4_BROWSER_OBSERVABILITY"] == "shadow"
    assert get_flag_state("V4_CAPABILITY_CERTIFICATION").value == "shadow"


def test_browser_capability_registry_has_complete_wave1_records():
    manifest = browser_capability_manifest()
    assert len(manifest) >= 16
    smart_waits_record = get_browser_capability("browser.waits.smart")
    assert smart_waits_record is not None
    assert smart_waits_record.feature_flag == "V4_SMART_WAITS"
    assert smart_waits_record.target_maturity_level == 5
    for record in manifest:
        assert record["capability_id"]
        assert record["version"]
        assert record["dependencies"]
        assert record["benchmarks"]
        assert record["metrics"]
        assert record["supported_browsers"]
        assert record["supported_websites"]
        assert record["rollout_status"]
        assert record["certification_status"]


def test_certification_report_counts_capabilities():
    report = certification_report()
    assert report["schema_version"] == "browser_capability_certification.v1"
    assert report["wave"] == "v4_wave_1_control_bedrock"
    assert report["capability_count"] == len(report["capabilities"])
    assert sum(report["status_counts"].values()) == report["capability_count"]


def test_get_capabilities_includes_wave1_metadata_without_changing_phasec_contract():
    caps = capabilities.get_capabilities()
    assert caps["adapter"] == "playwright"
    assert caps["supported_actions"] == list(capabilities.SUPPORTED_ACTIONS)
    assert "v4_wave_1" in caps
    assert caps["v4_wave_1"]["flags"]["V4_SMART_WAITS"] == "off"
    assert caps["v4_wave_1"]["certification"]["capability_count"] >= 16


def test_smart_wait_ready_uses_bounded_dom_stability():
    result = smart_waits.wait_for_ready(FakePage(), timeout_ms=500)
    assert result.ready is True
    assert result.reason == "dom_stable"
    assert result.duration_ms >= 0
    assert result.signals["overlay_count"] == 0


def test_smart_wait_selector_state_reports_selector():
    page = FakePage()
    result = smart_waits.wait_for_selector_state(page, "#save", state="visible", timeout_ms=1234)
    assert result.ready is True
    assert result.signals == {"selector": "#save", "state": "visible"}
    assert page.locator_obj.waits == [("visible", 1234)]


def test_auth_handoff_detects_password_page_without_secret_capture():
    signal = auth_handoff.detect_auth_handoff(FakePage(auth=True))
    assert signal.required is True
    assert signal.reason == "password_required"
    assert "password_fields" in signal.evidence
    assert "password_value" not in signal.evidence


def test_auth_handoff_ignores_normal_page():
    signal = auth_handoff.detect_auth_handoff(FakePage(auth=False))
    assert signal.required is False
    assert signal.reason == "not_auth"


def test_replay_export_validates_timeline_sequence():
    exec_timeline._reset_for_testing()
    exec_timeline.record("exec-v4", "step-1", "started", order=1)
    exec_timeline.record("exec-v4", "step-1", "validated", order=1, detail={"passed": True})
    exec_timeline.record("exec-v4", "step-1", "completed", order=1)
    exported = replay.export_replay("exec-v4")
    assert exported["schema_version"] == "browser_replay.v1"
    assert exported["validation"]["valid"] is True
    assert exported["validation"]["step_count"] == 1


def test_replay_validation_detects_missing_terminal_event():
    validation = replay.validate_replay({
        "events": [{"execution_id": "exec-v4", "step_id": "step-1", "event_type": "started"}],
    })
    assert validation["valid"] is False
    assert "step_without_terminal_event:step-1" in validation["errors"]
