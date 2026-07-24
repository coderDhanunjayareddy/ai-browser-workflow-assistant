from __future__ import annotations

from app.browser_intelligence.models import BrowserStateModel, SemanticPageModel, SemanticWaitPlan


class IntelligentWaitingEngine:
    """Build semantic wait plans from page state instead of fixed delays."""

    def plan(self, page_model: SemanticPageModel, browser_state: BrowserStateModel) -> SemanticWaitPlan:
        text = " ".join(
            [page_model.title]
            + [element.label for element in page_model.elements[:40]]
        ).lower()
        signals = {
            "page_type": page_model.classification.page_type,
            "adapter": page_model.adapter,
            "search_result_count": len(page_model.search_results),
            "dialog_count": len(browser_state.dialogs),
            "element_count": len(page_model.elements),
        }
        if any(term in text for term in ("loading", "please wait", "spinner", "progress")):
            return SemanticWaitPlan("spinner_disappears", False, "loading_indicator_visible", 250, 8000, signals)
        if page_model.classification.page_type == "search_engine" and not page_model.search_results:
            return SemanticWaitPlan("search_results_loaded", False, "search_engine_without_organic_results", 250, 10000, signals)
        if any(element.kind == "table" for element in page_model.elements) and signals["element_count"] < 3:
            return SemanticWaitPlan("table_populated", False, "table_structure_detected_without_rows", 300, 10000, signals)
        if page_model.classification.page_type in {"dashboard", "jobs"} and signals["element_count"] < 5:
            return SemanticWaitPlan("react_render_completed", False, "dynamic_page_sparse", 250, 8000, signals)
        return SemanticWaitPlan("page_ready", True, "semantic_state_stable", 250, 5000, signals)
