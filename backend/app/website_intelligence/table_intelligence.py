"""
Phase E — Table Intelligence (deterministic).

Turns raw <table>/grids into a structured TableModel: headers, columns, sortable
columns, row count, pagination, selection checkboxes, search box, filters, action and
export buttons. No AI — pure DOM-driven rules.
"""
from __future__ import annotations

import re
from typing import Optional

from app.website_intelligence.locator_builder import build_locator
from app.website_intelligence.models import DomNode, TableColumn, TableModel

_PAGINATION_HINTS = ("pagination", "pager", "page-nav")
# grid-container class signals: whole-token match OR a hyphen/underscore sub-token match
_GRID_WHOLE = {"table", "grid", "datatable", "data-grid", "data-table", "list"}
_GRID_TOKEN = {"table", "grid", "datatable", "list"}
_MAX_CONTAINER_DEPTH = 4
_EXPORT_WORDS = ("export", "csv", "excel", "pdf", "download")
_FILTER_WORDS = ("filter", "facet")


def _parent_map(root: DomNode) -> dict[int, DomNode]:
    pmap: dict[int, DomNode] = {}
    stack = [root]
    while stack:
        n = stack.pop()
        for c in n.children:
            pmap[id(c)] = n
            stack.append(c)
    return pmap


def _ancestors(node: DomNode, pmap: dict[int, DomNode]):
    cur = pmap.get(id(node))
    while cur is not None:
        yield cur
        cur = pmap.get(id(cur))


def _pag_label(aria_label: str) -> bool:
    al = (aria_label or "").lower().strip()
    return "pagination" in al or "paging" in al or al.startswith("page navigation")


def _is_pagination(n: DomNode) -> bool:
    if n.tag in ("nav", "ul") and _pag_label(n.aria_label):
        return True
    if n.class_contains(*_PAGINATION_HINTS):
        return True
    if n.role == "navigation" and _pag_label(n.aria_label):
        return True
    return False


def _grid_container_class(node: DomNode) -> bool:
    """True if a class token names a data-grid container (token-aware, not raw substring)."""
    for tok in node.class_list:
        if tok in _GRID_WHOLE:
            return True
        if any(p in _GRID_TOKEN for p in re.split(r"[-_]", tok)):
            return True
    return False


def _widget_container(table: DomNode, pmap: dict[int, DomNode]) -> DomNode:
    """
    Nearest ancestor (within a small bound) whose CLASS names a data-grid container,
    so table controls (pagination/search/filters/export) are scoped to THIS table's
    widget — not ballooned to <main>/<section> or a sibling grid.
    """
    depth = 0
    for anc in _ancestors(table, pmap):
        if anc.tag in ("body", "html") or depth >= _MAX_CONTAINER_DEPTH:
            break
        depth += 1
        if _grid_container_class(anc):
            return anc
    return table


def _headers(table: DomNode) -> list[DomNode]:
    ths = table.find_all(lambda n: n.tag == "th" or n.role == "columnheader")
    if ths:
        return ths
    # fall back to the first row's cells
    first_row = table.find_first(lambda n: n.tag == "tr" or n.role == "row")
    if first_row:
        return [c for c in first_row.children if c.tag in ("td", "th") or c.role in ("cell", "columnheader")]
    return []


def _is_sortable(th: DomNode) -> bool:
    if "aria-sort" in th.attrs:
        return True
    if th.class_contains("sort"):
        return True
    # a sort control: an element with a sort-related class, or a button whose
    # class/label clearly indicates sorting (a plain header button does NOT count)
    sort_ctrl = th.find_first(lambda n: n.class_contains("sort")
                              or (n.tag == "button" and "sort" in (n.aria_label or n.text_content(20) or "").lower()))
    return sort_ctrl is not None


def _row_count(table: DomNode) -> int:
    tbodies = table.find_all(lambda n: n.tag == "tbody")
    if tbodies:
        return sum(len(tb.find_all(lambda n: n.tag == "tr")) for tb in tbodies)
    rows = table.find_all(lambda n: n.tag == "tr")
    if rows:
        # a header row = a <tr> with header cells and no data cells
        header_rows = [r for r in rows
                       if r.find_first(lambda n: n.tag == "td") is None
                       and r.find_first(lambda n: n.tag == "th") is not None]
        return max(0, len(rows) - len(header_rows))
    role_rows = table.find_all(lambda n: n.role == "row")
    return max(0, len(role_rows) - 1) if role_rows else 0


def analyze_table(table: DomNode, container: DomNode, index: int = 0) -> TableModel:
    header_nodes = _headers(table)
    headers = [h.text_content(60) for h in header_nodes]
    columns = [TableColumn(index=i, header=headers[i], sortable=_is_sortable(header_nodes[i]))
               for i in range(len(header_nodes))]
    sortable = [c.header for c in columns if c.sortable]

    # single pass over the widget container for pagination / search / filters / export
    has_pagination = has_search = has_filters = False
    export_buttons: list[str] = []
    for n in container.walk():
        if not has_pagination and _is_pagination(n):
            has_pagination = True
        if not has_search and ((n.tag == "input" and n.type == "search") or n.role == "search"
                               or (n.tag == "input" and "search" in (n.placeholder or n.name or "").lower())):
            has_search = True
        is_ctrl = n.tag in ("button", "a")
        if not has_filters and (n.class_contains(*_FILTER_WORDS) or "data-filter" in n.attrs
                                or (is_ctrl and any(w in (n.text_content(30) or "").lower() for w in _FILTER_WORDS))):
            has_filters = True
        if is_ctrl:
            lbl = (n.text_content(30) or n.aria_label or "").strip()
            if lbl and lbl not in export_buttons and any(w in lbl.lower() for w in _EXPORT_WORDS):
                export_buttons.append(lbl)

    # selection checkboxes inside the table
    has_selection = table.find_first(lambda n: n.tag == "input" and n.type == "checkbox") is not None

    # row action buttons (inside table rows): buttons, or links that carry text
    action_buttons = []
    for btn in table.find_all(lambda n: n.tag == "button" or (n.tag == "a" and bool(n.text_content(20)))):
        lbl = (btn.text_content(30) or btn.aria_label or "").strip()
        if lbl and lbl not in action_buttons:
            action_buttons.append(lbl)

    caption = table.find_first(lambda n: n.tag == "caption")
    label = (table.aria_label or (caption.text_content(60) if caption else "")
             or table.attr("summary") or table.id or f"table-{index}")
    return TableModel(
        table_id=table.id or table.testid or f"table-{index}",
        label=label, headers=headers, columns=columns, row_count=_row_count(table),
        sortable_columns=sortable, has_pagination=has_pagination, has_selection=has_selection,
        has_search=has_search, has_filters=has_filters,
        action_buttons=action_buttons[:20], export_buttons=export_buttons[:10],
        locator=build_locator(table, label=label),
    )


def analyze_tables(root: DomNode) -> list[TableModel]:
    pmap = _parent_map(root)
    tables = root.find_all(lambda n: n.tag == "table" or n.role in ("table", "grid"))
    if root.tag == "table" or root.role in ("table", "grid"):
        tables = [root] + tables
    out = []
    for i, t in enumerate(tables):
        out.append(analyze_table(t, _widget_container(t, pmap), i))
    return out
