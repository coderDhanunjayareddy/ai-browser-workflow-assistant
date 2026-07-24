from __future__ import annotations

from app.browser_intelligence.models import SemanticPageModel, VisualGroundingTarget
from app.browser_intelligence.selector_engine import stable_id


class VisualGroundingEngine:
    """Fuse DOM/accessibility/visual metadata into unified targets.

    OCR and screenshot reasoning are represented as metadata hooks only here; no
    vision model or OCR dependency is invoked by Browser Intelligence.
    """

    def ground(self, page_model: SemanticPageModel) -> list[VisualGroundingTarget]:
        targets: list[VisualGroundingTarget] = []
        for element in page_model.elements[:80]:
            source = "dom_accessibility"
            if element.metadata.get("bounding_box"):
                source = "dom_accessibility_region"
            targets.append(
                VisualGroundingTarget(
                    target_id=stable_id("vg", f"{element.element_id}|{element.label}"),
                    source=source,
                    label=element.label,
                    selector_id=element.selector_id,
                    selector=element.selector,
                    confidence=min(1.0, round(element.confidence + 0.03, 2)),
                    region=dict(element.metadata.get("bounding_box") or {}),
                    metadata={
                        "semantic_kind": element.kind,
                        "ocr_available": False,
                        "screenshot_region_available": bool(element.metadata.get("bounding_box")),
                    },
                )
            )
        return targets
