from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from app.browser_intelligence.adapters import AdapterRegistry
from app.browser_intelligence.models import (
    BrowserStateModel,
    PageClassification,
    SemanticPageModel,
)
from app.browser_intelligence.selector_engine import SelectorIntelligenceEngine


class PageUnderstandingEngine:
    def __init__(self, adapters: AdapterRegistry | None = None) -> None:
        self.adapters = adapters or AdapterRegistry()
        self.selectors = SelectorIntelligenceEngine()

    def build_page_model(self, page_context: Any) -> SemanticPageModel:
        started = time.perf_counter()
        classification = classify_page(page_context)
        adapter = self.adapters.select(page_context)
        selector_candidates = self.selectors.build_candidates(page_context)
        adapter_result = adapter.extract(page_context, self.selectors)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SemanticPageModel(
            schema_version="browser_intelligence.page_model.v1",
            url=str(getattr(page_context, "url", "") or ""),
            title=str(getattr(page_context, "title", "") or ""),
            classification=classification,
            adapter=adapter_result.adapter_name,
            elements=adapter_result.semantic_elements[:150],
            search_results=adapter_result.search_results,
            selector_candidates=selector_candidates,
            telemetry={
                "extraction_latency_ms": elapsed_ms,
                "classification_confidence": classification.confidence,
                "adapter_metadata": adapter_result.metadata,
                "visible_element_count": len(adapter_result.semantic_elements),
                "selector_candidate_count": len(selector_candidates),
            },
        )

    def build_browser_state(self, page_context: Any, page_model: SemanticPageModel) -> BrowserStateModel:
        metadata = getattr(page_context, "metadata", {}) or {}
        auth_state = "authenticated" if _looks_authenticated(page_context) else "unknown"
        return BrowserStateModel(
            current_url=page_model.url,
            title=page_model.title,
            page_type=page_model.classification.page_type,
            open_tabs=_coerce_json_list(metadata.get("open_tabs")),
            active_tab=_coerce_json_dict(metadata.get("active_tab")),
            navigation_history=_coerce_string_list(metadata.get("navigation_history")),
            frames=_coerce_json_list(metadata.get("frames")),
            dialogs=_dialog_state(page_model),
            downloads=_coerce_json_list(metadata.get("downloads")),
            uploads=_coerce_json_list(metadata.get("uploads")),
            authentication_state=auth_state,
            scroll_state=_coerce_json_dict(metadata.get("scroll_state")) or {},
            focused_element=metadata.get("focused_element"),
            pending_actions=[],
        )


def classify_page(page_context: Any) -> PageClassification:
    url = str(getattr(page_context, "url", "") or "")
    title = str(getattr(page_context, "title", "") or "")
    visible = str(getattr(page_context, "visible_text", "") or "")[:2000]
    parsed = urlparse(url)
    text = f"{title}\n{visible}".lower()
    evidence: list[str] = []

    if parsed.netloc.endswith("google.com") and parsed.path.startswith("/search"):
        return PageClassification("search_engine", 0.96, ("google_search_url",))
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/search"):
        return PageClassification("search_engine", 0.9, ("bing_search_url",))
    if "linkedin.com" in parsed.netloc and "/jobs" in parsed.path:
        return PageClassification("jobs", 0.92, ("linkedin_jobs_url",))
    if any(term in text for term in ("sign in", "log in", "password")):
        evidence.append("auth_terms")
        return PageClassification("login", 0.82, tuple(evidence))
    if any(term in text for term in ("sign up", "create account", "register")):
        evidence.append("signup_terms")
        return PageClassification("signup", 0.78, tuple(evidence))
    if any(term in text for term in ("documentation", "quickstart", "api reference", "docs")):
        evidence.append("documentation_terms")
        return PageClassification("documentation", 0.78, tuple(evidence))
    if any(term in text for term in ("settings", "profile", "preferences")):
        evidence.append("settings_terms")
        return PageClassification("settings", 0.66, tuple(evidence))
    if any(term in text for term in ("dashboard", "analytics", "overview")):
        evidence.append("dashboard_terms")
        return PageClassification("dashboard", 0.64, tuple(evidence))
    if ".pdf" in parsed.path.lower() or "pdf viewer" in text:
        return PageClassification("pdf", 0.8, ("pdf_signal",))
    return PageClassification("unknown", 0.35, ())


def _looks_authenticated(page_context: Any) -> bool:
    text = f"{getattr(page_context, 'title', '')} {getattr(page_context, 'visible_text', '')[:1000]}".lower()
    return any(term in text for term in ("dashboard", "account", "profile", "settings", "sign out", "logout"))


def _dialog_state(page_model: SemanticPageModel) -> list[dict[str, Any]]:
    return [
        {"element_id": element.element_id, "label": element.label, "selector": element.selector}
        for element in page_model.elements
        if element.kind == "dialog"
    ]


def _coerce_json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _coerce_json_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []
