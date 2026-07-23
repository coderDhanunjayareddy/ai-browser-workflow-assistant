from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Wave3Result:
    capability_id: str
    success: bool
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 3),
            "details": dict(self.details),
            "error": self.error,
        }


def parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {"text": raw}
        except json.JSONDecodeError:
            return {"text": raw}
    return {}


def detect_visual_surface(classes: str, tag_name: str = "", attrs: dict[str, str] | None = None) -> str:
    attrs = attrs or {}
    haystack = f"{tag_name} {classes} {' '.join(attrs.values())}".lower()
    if "canvas" in haystack:
        return "canvas"
    if "svg" in haystack or tag_name.lower() in {"svg", "path", "g", "circle", "rect", "line", "polyline", "polygon"}:
        return "svg"
    if "pdf" in haystack:
        return "pdf"
    if any(name in haystack for name in ("chart", "highcharts", "apexcharts", "echarts", "d3")):
        return "chart"
    if any(name in haystack for name in ("leaflet", "mapbox", "gm-style", "google-map")):
        return "map"
    if tag_name.lower() in {"video", "audio"}:
        return "media"
    return "unknown"


def execute_canvas(page: Any, locator: Any, payload: dict[str, Any]) -> Wave3Result:
    return _coordinate_action(page, locator, payload, "browser.canvas", expected_tag="canvas")


def execute_svg(page: Any, locator: Any, payload: dict[str, Any]) -> Wave3Result:
    return _coordinate_action(page, locator, payload, "browser.svg.interaction", expected_tag="svg")


def execute_chart(page: Any, locator: Any, payload: dict[str, Any]) -> Wave3Result:
    return _coordinate_action(page, locator, payload, "browser.charts.graphs")


def execute_map(page: Any, locator: Any, payload: dict[str, Any]) -> Wave3Result:
    return _coordinate_action(page, locator, payload, "browser.maps.interactive")


def execute_pdf_viewer(page: Any, locator: Any | None, payload: dict[str, Any]) -> Wave3Result:
    start = time.perf_counter()
    operation = str(payload.get("operation") or "detect")
    try:
        handle = locator.element_handle() if locator is not None else None
        state = page.evaluate(
            """([el, operation, query]) => {
              const root = el || document;
              const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
              const embeds = Array.from(document.querySelectorAll('embed[type="application/pdf"], iframe[src$=".pdf"], object[type="application/pdf"], pdf-viewer'));
              const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="search"]'));
              if (operation === 'search') {
                const search = buttons.find((node) => /search|find/i.test(node.getAttribute('aria-label') || node.getAttribute('title') || node.textContent || ''));
                if (search instanceof HTMLElement) search.click();
              }
              return {
                viewer_detected: embeds.length > 0 || location.href.toLowerCase().includes('.pdf') || text.toLowerCase().includes('page'),
                embed_count: embeds.length,
                text_match: query ? text.toLowerCase().includes(String(query).toLowerCase()) : null,
                operation,
                root_tag: root.tagName || 'document',
              };
            }""",
            [handle, operation, payload.get("query") or payload.get("text") or ""],
        )
        success = bool(state.get("viewer_detected")) and (state.get("text_match") is not False)
        return _result("browser.pdf.viewer", success, start, dict(state))
    except Exception as exc:  # noqa: BLE001
        return _result("browser.pdf.viewer", False, start, {}, str(exc)[:200])


def execute_media(page: Any, locator: Any, payload: dict[str, Any]) -> Wave3Result:
    start = time.perf_counter()
    operation = str(payload.get("operation") or "status")
    try:
        handle = locator.element_handle()
        state = page.evaluate(
            """([el, payload]) => {
              if (!(el instanceof HTMLMediaElement)) return { success: false, error: 'not_media' };
              const operation = String(payload.operation || 'status');
              if (operation === 'play') el.play?.();
              if (operation === 'pause') el.pause();
              if (operation === 'seek') el.currentTime = Number(payload.current_time ?? payload.time ?? 0);
              if (operation === 'volume') el.volume = Math.max(0, Math.min(1, Number(payload.volume ?? 1)));
              if (operation === 'fullscreen') el.requestFullscreen?.();
              return {
                success: true,
                operation,
                paused: el.paused,
                current_time: Math.round(el.currentTime * 1000) / 1000,
                volume: el.volume,
                duration: Number.isFinite(el.duration) ? el.duration : null,
              };
            }""",
            [handle, payload],
        )
        success = bool(state.get("success"))
        return _result("browser.media.controls", success, start, dict(state), None if success else str(state.get("error") or "media_failed"))
    except Exception as exc:  # noqa: BLE001
        return _result("browser.media.controls", False, start, {}, str(exc)[:200])


def execute_file_preview(page: Any, locator: Any | None, payload: dict[str, Any]) -> Wave3Result:
    start = time.perf_counter()
    try:
        handle = locator.element_handle() if locator is not None else None
        state = page.evaluate(
            """([el, expected]) => {
              const root = el || document;
              const selector = 'img, embed, object, iframe, video, audio, canvas, [role="dialog"], .preview, [data-testid*="preview"]';
              const previews = Array.from(document.querySelectorAll(selector)).filter((node) => {
                const rect = node.getBoundingClientRect?.();
                return !rect || (rect.width > 0 && rect.height > 0);
              });
              const text = (root.textContent || document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
              return {
                preview_detected: previews.length > 0,
                preview_count: previews.length,
                expected_match: expected ? text.toLowerCase().includes(String(expected).toLowerCase()) : null,
                root_tag: root.tagName || 'document',
              };
            }""",
            [handle, payload.get("expected_text") or payload.get("text") or ""],
        )
        success = bool(state.get("preview_detected")) and (state.get("expected_match") is not False)
        return _result("browser.file.preview", success, start, dict(state))
    except Exception as exc:  # noqa: BLE001
        return _result("browser.file.preview", False, start, {}, str(exc)[:200])


def execute_visual_region(page: Any, locator: Any | None, payload: dict[str, Any]) -> Wave3Result:
    start = time.perf_counter()
    mode = str(payload.get("mode") or ("element" if locator is not None else "viewport"))
    try:
        if mode == "element" and locator is not None:
            image = locator.screenshot(timeout=int(payload.get("timeout_ms", 30_000)))
            details = {"mode": mode, "bytes": len(image), "target": "element"}
        elif mode == "region":
            clip = {
                "x": float(payload.get("x", 0)),
                "y": float(payload.get("y", 0)),
                "width": float(payload.get("width", 1)),
                "height": float(payload.get("height", 1)),
            }
            image = page.screenshot(clip=clip, timeout=int(payload.get("timeout_ms", 30_000)))
            details = {"mode": mode, "bytes": len(image), "clip": clip}
        else:
            image = page.screenshot(full_page=bool(payload.get("full_page", False)), timeout=int(payload.get("timeout_ms", 30_000)))
            details = {"mode": "viewport", "bytes": len(image), "full_page": bool(payload.get("full_page", False))}
        return _result("browser.visual_regions", True, start, details)
    except Exception as exc:  # noqa: BLE001
        return _result("browser.visual_regions", False, start, {"mode": mode}, str(exc)[:200])


def _coordinate_action(page: Any, locator: Any, payload: dict[str, Any], capability_id: str, expected_tag: str | None = None) -> Wave3Result:
    start = time.perf_counter()
    operation = str(payload.get("operation") or "click")
    try:
        handle = locator.element_handle()
        if handle is None:
            return _result(capability_id, False, start, {}, "target_not_found")
        box = locator.bounding_box()
        if not box:
            return _result(capability_id, False, start, {}, "target_not_visible")
        tag_name = str(page.evaluate("(el) => el.tagName ? el.tagName.toLowerCase() : ''", handle))
        if expected_tag == "canvas" and tag_name != "canvas":
            return _result(capability_id, False, start, {"tag_name": tag_name}, "canvas_not_found")
        if expected_tag == "svg" and tag_name != "svg":
            tag_name = str(page.evaluate("(el) => el.closest('svg') ? 'svg' : el.tagName.toLowerCase()", handle))
            if tag_name != "svg":
                return _result(capability_id, False, start, {"tag_name": tag_name}, "svg_not_found")
        x = float(payload.get("x", box["width"] / 2))
        y = float(payload.get("y", box["height"] / 2))
        abs_x = box["x"] + x
        abs_y = box["y"] + y
        if operation == "hover":
            page.mouse.move(abs_x, abs_y)
        elif operation == "drag":
            to_x = box["x"] + float(payload.get("to_x", x))
            to_y = box["y"] + float(payload.get("to_y", y))
            page.mouse.move(abs_x, abs_y)
            page.mouse.down()
            page.mouse.move(to_x, to_y, steps=int(payload.get("steps", 5)))
            page.mouse.up()
        elif operation == "draw":
            points = payload.get("points") if isinstance(payload.get("points"), list) else []
            page.mouse.move(abs_x, abs_y)
            page.mouse.down()
            for point in points:
                if isinstance(point, dict):
                    page.mouse.move(box["x"] + float(point.get("x", x)), box["y"] + float(point.get("y", y)))
            page.mouse.up()
        else:
            page.mouse.click(abs_x, abs_y)
        return _result(capability_id, True, start, {
            "operation": operation,
            "tag_name": tag_name,
            "x": round(x, 3),
            "y": round(y, 3),
            "absolute_x": round(abs_x, 3),
            "absolute_y": round(abs_y, 3),
            "width": round(float(box["width"]), 3),
            "height": round(float(box["height"]), 3),
        })
    except Exception as exc:  # noqa: BLE001
        return _result(capability_id, False, start, {"operation": operation}, str(exc)[:200])


def _result(capability_id: str, success: bool, start: float, details: dict[str, Any], error: str | None = None) -> Wave3Result:
    return Wave3Result(
        capability_id=capability_id,
        success=success,
        duration_ms=(time.perf_counter() - start) * 1000,
        details=details,
        error=error,
    )
