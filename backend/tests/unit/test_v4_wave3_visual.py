from __future__ import annotations

from app.capability_platform.browser_registry import certification_status, get_browser_capability
from app.execution_gateway.browser import exec_timeline, metrics, replay, wave3_visual
from app.feature_flags import get_flag_state


WAVE3_CAPABILITIES = {
    "browser.canvas": "V4_CANVAS",
    "browser.svg.interaction": "V4_SVG_INTERACTION",
    "browser.pdf.viewer": "V4_PDF_VIEWER",
    "browser.charts.graphs": "V4_CHARTS",
    "browser.maps.interactive": "V4_MAPS",
    "browser.media.controls": "V4_MEDIA_CONTROLS",
    "browser.file.preview": "V4_FILE_PREVIEW",
    "browser.visual_regions": "V4_VISUAL_REGIONS",
}


class FakeMouse:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def click(self, x: float, y: float) -> None:
        self.events.append(("click", x, y))

    def move(self, x: float, y: float, steps: int | None = None) -> None:
        self.events.append(("move", x, y, steps))

    def down(self) -> None:
        self.events.append(("down",))

    def up(self) -> None:
        self.events.append(("up",))


class FakeLocator:
    def __init__(self, tag: str = "canvas") -> None:
        self.tag = tag

    def element_handle(self):
        return {"tag": self.tag}

    def bounding_box(self):
        return {"x": 10, "y": 20, "width": 100, "height": 80}

    def screenshot(self, **_kwargs):
        return b"element-png"


class FakePage:
    def __init__(self) -> None:
        self.mouse = FakeMouse()

    def evaluate(self, script: str, arg=None):
        if "tagName" in script:
            handle = arg
            return handle.get("tag", "canvas")
        raise AssertionError("unexpected script")

    def screenshot(self, **_kwargs):
        return b"viewport-png"


def test_wave3_capabilities_registered_certified_and_shadow_flagged():
    for capability_id, flag in WAVE3_CAPABILITIES.items():
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


def test_visual_payload_and_surface_detection_are_deterministic():
    assert wave3_visual.parse_payload("plain") == {"text": "plain"}
    assert wave3_visual.parse_payload('{"operation":"hover","x":1}') == {"operation": "hover", "x": 1}
    assert wave3_visual.detect_visual_surface("chartjs", "div") == "chart"
    assert wave3_visual.detect_visual_surface("leaflet-container", "div") == "map"
    assert wave3_visual.detect_visual_surface("", "video") == "media"
    assert wave3_visual.detect_visual_surface("", "canvas") == "canvas"


def test_canvas_coordinate_action_and_visual_region_capture():
    page = FakePage()
    result = wave3_visual.execute_canvas(page, FakeLocator("canvas"), {"operation": "click", "x": 7, "y": 9})
    assert result.success is True
    assert result.details["absolute_x"] == 17
    assert result.details["absolute_y"] == 29
    assert page.mouse.events == [("click", 17.0, 29.0)]

    capture = wave3_visual.execute_visual_region(page, FakeLocator("canvas"), {"mode": "element"})
    assert capture.success is True
    assert capture.details["bytes"] == len(b"element-png")


def test_wave3_telemetry_and_replay_certification_hooks():
    metrics._reset_for_testing()
    exec_timeline._reset_for_testing()
    for capability_id in WAVE3_CAPABILITIES:
        metrics.record_capability(capability_id, succeeded=True)
        exec_timeline.record("wave3-exec", capability_id, "completed", detail={"capability": capability_id})
    exported = replay.export_replay("wave3-exec")
    assert exported["validation"]["valid"] is True
    for capability_id in WAVE3_CAPABILITIES:
        assert exported["metrics"]["capability_counts"][capability_id]["succeeded"] == 1
