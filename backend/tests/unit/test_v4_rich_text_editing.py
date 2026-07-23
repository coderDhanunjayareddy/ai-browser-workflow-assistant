from __future__ import annotations

from app.capability_platform.browser_registry import get_browser_capability
from app.execution_gateway.browser import exec_timeline, metrics, replay, rich_text
from app.feature_flags import get_flag_state


class FakeLocator:
    def __init__(self) -> None:
        self.focused = False
        self.scrolled = False

    def element_handle(self):
        return {"id": "editor"}

    def scroll_into_view_if_needed(self) -> None:
        self.scrolled = True

    def focus(self) -> None:
        self.focused = True


class FakePage:
    def __init__(self) -> None:
        self.text = ""

    def evaluate(self, script: str, arg=None):
        if "return 'quill'" in script:
            return "prosemirror"
        if "document.execCommand" in script:
            payload = arg[1]
            if payload["mode"] == "replace":
                self.text = ""
            self.text += payload["text"]
            return True
        if "return (root.textContent" in script:
            return self.text
        raise AssertionError("unexpected script")


def test_rich_text_capability_registered_as_wave2_only_addition():
    capability = get_browser_capability("browser.editors.rich_text")
    assert capability is not None
    assert capability.feature_flag == "V4_RICH_TEXT_EDITING"
    assert capability.maturity_level == 4
    assert capability.target_maturity_level == 4
    assert "wave2.rich_text.contenteditable" in capability.benchmarks
    assert get_flag_state("V4_RICH_TEXT_EDITING").value == "shadow"


def test_parse_rich_text_payload_from_plain_text():
    payload = rich_text.parse_payload("Hello editor")
    assert payload.text == "Hello editor"
    assert payload.mode == "replace"
    assert payload.preserve_formatting is True


def test_parse_rich_text_payload_from_json():
    payload = rich_text.parse_payload('{"text":"Hello","html":"<b>Hello</b>","mode":"append","shortcuts":["ctrl+b"]}')
    assert payload.text == "Hello"
    assert payload.html == "<b>Hello</b>"
    assert payload.mode == "append"
    assert payload.shortcuts == ("ctrl+b",)


def test_execute_rich_text_records_validated_editor_result():
    locator = FakeLocator()
    result = rich_text.execute(FakePage(), locator, rich_text.parse_payload('{"text":"Draft body","mode":"replace"}'))
    assert result.success is True
    assert result.validated is True
    assert result.editor_kind == "prosemirror"
    assert result.inserted_length == len("Draft body")
    assert locator.focused is True
    assert locator.scrolled is True


def test_rich_text_telemetry_and_replay_are_compatible():
    metrics._reset_for_testing()
    exec_timeline._reset_for_testing()
    metrics.record_capability("browser.editors.rich_text", succeeded=True)
    exec_timeline.record("rich-exec", "rich-step", "started", order=1, detail={"capability": "browser.editors.rich_text"})
    exec_timeline.record("rich-exec", "rich-step", "validated", order=1, detail={"passed": True})
    exec_timeline.record("rich-exec", "rich-step", "completed", order=1)
    exported = replay.export_replay("rich-exec")
    assert exported["validation"]["valid"] is True
    assert exported["metrics"]["capability_counts"]["browser.editors.rich_text"]["succeeded"] == 1
