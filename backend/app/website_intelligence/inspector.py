"""
Phase E — Website Intelligence Inspector.

Read-only surfaces over a WebsiteIntelligenceResult for REST: the semantic tree, forms,
tables, dialogs, navigation, the interactive registry, execution hints, and locator
metadata. Plus a compact summary for the mission inspector / browser diagnostics.
"""
from __future__ import annotations

from typing import Union

from app.website_intelligence import analyzer as wi_analyzer
from app.website_intelligence.models import DomNode, WebsiteIntelligenceResult


def analyze_html(html: str, *, url: str = "", title: str = "") -> WebsiteIntelligenceResult:
    return wi_analyzer.analyze_html(html, url=url, title=title)


def analyze_snapshot(snapshot: Union[DomNode, dict], *, url: str = "", title: str = "") -> WebsiteIntelligenceResult:
    return wi_analyzer.analyze(snapshot, url=url, title=title)


def semantic_tree(result: WebsiteIntelligenceResult) -> dict:
    return result.page.to_dict()


def forms(result: WebsiteIntelligenceResult) -> list[dict]:
    return [f.to_dict() for f in result.forms]


def tables(result: WebsiteIntelligenceResult) -> list[dict]:
    return [t.to_dict() for t in result.tables]


def dialogs(result: WebsiteIntelligenceResult) -> list[dict]:
    return [d.to_dict() for d in result.dialogs]


def navigation(result: WebsiteIntelligenceResult) -> dict:
    return result.navigation.to_dict()


def registry(result: WebsiteIntelligenceResult) -> list[dict]:
    return [e.to_dict() for e in result.registry]


def hints(result: WebsiteIntelligenceResult) -> list[dict]:
    return [h.to_dict() for h in result.hints]


def locator_metadata(result: WebsiteIntelligenceResult) -> list[dict]:
    """Flat list of {semantic_id, label, locator} for every interactive element."""
    out = []
    for e in result.registry:
        out.append({
            "semantic_id": e.semantic_id, "label": e.label, "category": e.category.value,
            "locator": e.locator.to_dict() if e.locator else None,
        })
    return out


def summary(result: WebsiteIntelligenceResult) -> dict:
    """Compact summary for the mission inspector / browser diagnostics."""
    blocking_dialogs = [d for d in result.dialogs if d.blocking and d.visible]
    return {
        "url":                  result.url,
        "title":                result.title,
        "sections":             result.page.sections,
        "forms":                len(result.forms),
        "tables":               len(result.tables),
        "dialogs":              len(result.dialogs),
        "blocking_dialogs":     len(blocking_dialogs),
        "interactive_elements": len(result.registry),
        "navigation_items":     len(result.navigation.primary),
        "hints":                len(result.hints),
        "type_counts":          result.page.type_counts,
        "latency_ms":           result.latency_ms,
    }
