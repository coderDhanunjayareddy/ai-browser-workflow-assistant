from __future__ import annotations

from app.capability_platform.browser_registry import certification_status, get_browser_capability
from app.execution_gateway.browser import exec_timeline, metrics, replay, wave2_core
from app.feature_flags import get_flag_state


WAVE2_CORE_CAPABILITIES = {
    "browser.editors.monaco": "V4_MONACO_EDITOR",
    "browser.editors.codemirror": "V4_CODEMIRROR_EDITOR",
    "browser.drag_drop": "V4_DRAG_DROP",
    "browser.lists.virtual": "V4_VIRTUAL_LISTS",
    "browser.shadow_dom.open": "V4_SHADOW_DOM",
    "browser.scroll.infinite": "V4_INFINITE_SCROLL",
    "browser.advanced_keyboard": "V4_ADVANCED_KEYBOARD",
    "browser.clipboard": "V4_CLIPBOARD",
}


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    def press(self, key: str) -> None:
        self.pressed.append(key)


class FakePage:
    def __init__(self) -> None:
        self.keyboard = FakeKeyboard()
        self.scroll_calls = 0
        self.clipboard_text = ""

    def evaluate(self, script: str, arg=None):
        if "bodyText.length" in script:
            self.scroll_calls += 1
            return {"signature": f"sig-{self.scroll_calls}", "found": self.scroll_calls == 2, "atEnd": False}
        if "navigator.clipboard" in script:
            self.clipboard_text = arg
            return None
        raise AssertionError("unexpected script")

    def wait_for_timeout(self, _ms: int) -> None:
        return None


class FakeLocator:
    def __init__(self) -> None:
        self.dragged_to = None

    def drag_to(self, target, timeout: int) -> None:
        self.dragged_to = (target, timeout)


def test_wave2_core_capabilities_registered_and_shadow_flagged():
    for capability_id, flag in WAVE2_CORE_CAPABILITIES.items():
        capability = get_browser_capability(capability_id)
        assert capability is not None
        assert capability.feature_flag == flag
        assert capability.maturity_level == 4
        assert capability.target_maturity_level == 4
        assert capability.rollout_status == "beta"
        assert certification_status(capability) == "certified"
        assert get_flag_state(flag).value == "shadow"
        assert capability.benchmarks
        assert capability.supported_browsers
        assert capability.supported_websites


def test_parse_payload_and_editor_detection_are_deterministic():
    assert wave2_core.parse_payload("plain") == {"text": "plain"}
    assert wave2_core.parse_payload('{"text":"hello","mode":"append"}') == {"text": "hello", "mode": "append"}
    assert wave2_core.editor_kind_from_classes("monaco-editor") == "monaco"
    assert wave2_core.editor_kind_from_classes("cm-editor") == "codemirror"
    assert wave2_core.editor_kind_from_classes("other", {"role": "textbox"}) == "unknown"


def test_keyboard_drag_scroll_clipboard_results_are_observable():
    page = FakePage()
    keyboard = wave2_core.execute_keyboard(page, {"sequence": ["Tab", "Control+A"]})
    assert keyboard.success is True
    assert page.keyboard.pressed == ["Tab", "Control+A"]

    source = FakeLocator()
    target = object()
    dragged = wave2_core.execute_drag_drop(page, source, target, {"timeout_ms": 123})
    assert dragged.success is True
    assert source.dragged_to == (target, 123)

    scrolled = wave2_core.execute_infinite_scroll(page, {"target_text": "needle", "max_steps": 3, "settle_ms": 0})
    assert scrolled.success is True
    assert scrolled.details["found"] is True

    pasted = wave2_core.execute_clipboard(page, {"operation": "paste", "text": "copied"})
    assert pasted.success is True
    assert page.clipboard_text == "copied"
    assert page.keyboard.pressed[-1] == "Control+V"


def test_wave2_core_telemetry_and_replay_certification_hooks():
    metrics._reset_for_testing()
    exec_timeline._reset_for_testing()
    for capability_id in WAVE2_CORE_CAPABILITIES:
        metrics.record_capability(capability_id, succeeded=True)
        exec_timeline.record("wave2-exec", capability_id, "completed", detail={"capability": capability_id})
    exported = replay.export_replay("wave2-exec")
    assert exported["validation"]["valid"] is True
    for capability_id in WAVE2_CORE_CAPABILITIES:
        assert exported["metrics"]["capability_counts"][capability_id]["succeeded"] == 1
