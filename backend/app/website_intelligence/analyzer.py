"""
Phase E — Website Intelligence Analyzer (facade).

Runs every deterministic analyzer over a DOM snapshot and assembles a
WebsiteIntelligenceResult. Pure read-only analysis; no browser actions.
"""
from __future__ import annotations

import time
from typing import Any, Optional, Union

from app.website_intelligence import dom_snapshot
from app.website_intelligence import semantic_analyzer
from app.website_intelligence import form_intelligence
from app.website_intelligence import table_intelligence
from app.website_intelligence import navigation_intelligence
from app.website_intelligence import dialog_intelligence
from app.website_intelligence import interactive_registry
from app.website_intelligence import execution_hints
from app.website_intelligence.models import DomNode, WebsiteIntelligenceResult


def _as_node(source: Union[DomNode, dict]) -> DomNode:
    if isinstance(source, DomNode):
        return source
    return dom_snapshot.from_dict(source)


def analyze(source: Union[DomNode, dict], *, url: str = "", title: str = "") -> WebsiteIntelligenceResult:
    t0 = time.perf_counter()
    root = _as_node(source)

    page = semantic_analyzer.analyze_page(root, url=url, title=title)
    forms = form_intelligence.analyze_forms(root)
    tables = table_intelligence.analyze_tables(root)
    navigation = navigation_intelligence.analyze_navigation(root)
    dialogs = dialog_intelligence.analyze_dialogs(root)
    registry = interactive_registry.build_registry(root)
    hints = execution_hints.build_hints(root, page, forms, tables, navigation, dialogs)

    latency_ms = round((time.perf_counter() - t0) * 1000, 3)
    stats = {
        "dom_nodes":           root.node_count(),
        "semantic_sections":   len(page.sections),
        "forms":               len(forms),
        "tables":              len(tables),
        "dialogs":             len(dialogs),
        "interactive_elements": len(registry),
        "navigation_items":    len(navigation.primary) + len(navigation.tabs) + len(navigation.breadcrumbs),
        "hints":               len(hints),
        "type_counts":         page.type_counts,
    }
    return WebsiteIntelligenceResult(
        url=url, title=title, page=page, forms=forms, tables=tables, navigation=navigation,
        dialogs=dialogs, registry=registry, hints=hints, stats=stats, latency_ms=latency_ms,
    )


def analyze_html(html: str, *, url: str = "", title: str = "") -> WebsiteIntelligenceResult:
    return analyze(dom_snapshot.from_html(html), url=url, title=title)


def analyze_live(page: Any, *, url: str = "", title: str = "") -> WebsiteIntelligenceResult:
    """Capture the live page (one read-only evaluate) and analyze it."""
    node = dom_snapshot.capture(page)
    try:
        url = url or page.url
    except Exception:
        pass
    try:
        title = title or page.title()
    except Exception:
        pass
    return analyze(node, url=url, title=title)
