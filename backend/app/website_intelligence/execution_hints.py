"""
Phase E — Execution Hints (advisory only).

Produces optional, advisory hints for the execution layer from the semantic models:
preferred validation, recommended wait strategy, likely loading indicator, and expected
navigation/dialog/download/upload. Hints are ADVISORY — the gateway remains authoritative
and Phase E never executes anything.
"""
from __future__ import annotations

from app.website_intelligence.models import (
    DomNode, ExecutionHint, FormModel, TableModel, NavigationModel, DialogModel, PageModel,
)

_LOADING_HINTS = ("spinner", "loading", "skeleton", "progress", "loader")


def build_hints(
    root: DomNode,
    page: PageModel,
    forms: list[FormModel],
    tables: list[TableModel],
    navigation: NavigationModel,
    dialogs: list[DialogModel],
) -> list[ExecutionHint]:
    hints: list[ExecutionHint] = []

    # loading indicator present on the page
    if root.find_first(lambda n: n.class_contains(*_LOADING_HINTS) or n.role == "progressbar") is not None:
        hints.append(ExecutionHint("loading_indicator", target="page", value="present", confidence=0.8))

    # forms → preferred validation after submit + expected upload
    for f in forms:
        hints.append(ExecutionHint("preferred_validation", target=f.form_id,
                                   value="text_contains:success | url_changed", confidence=0.6))
        if f.submit_label:
            hints.append(ExecutionHint("expected_navigation", target=f.form_id,
                                       value=f"submit:{f.submit_label}", confidence=0.5))
        if f.has_file_upload:
            hints.append(ExecutionHint("expected_upload", target=f.form_id,
                                       value="filename_visible", confidence=0.7))

    # tables with pagination/filters/search → wait for network idle on data change
    for t in tables:
        if t.has_pagination or t.has_filters or t.has_search:
            hints.append(ExecutionHint("wait_strategy", target=t.table_id,
                                       value="networkidle", confidence=0.6))

    # dialogs → expected dialog + wait strategy
    for d in dialogs:
        if d.visible:
            hints.append(ExecutionHint("expected_dialog", target=d.dialog_id,
                                       value=f"{d.kind}:blocking={d.blocking}", confidence=0.7))
            if d.blocking:
                hints.append(ExecutionHint("wait_strategy", target=d.dialog_id,
                                           value="dialog_dismiss_required", confidence=0.6))

    # download links → expected download
    for n in root.find_all(lambda x: x.tag == "a" and (("download" in x.attrs))):
        hints.append(ExecutionHint("expected_download", target=n.id or n.text_content(30) or n.href,
                                   value="file_exists", confidence=0.7))

    # navigation links → expected navigation
    for item in navigation.primary[:10]:
        if item.href and not item.href.startswith("#"):
            hints.append(ExecutionHint("expected_navigation", target=item.label,
                                       value=f"url:{item.href}", confidence=0.5))

    return hints
