"""
Phase E — Semantic DOM Analyzer + Page Structure Model (deterministic).

Classifies DOM nodes into the catalogue of SemanticType structures and builds a
deterministic semantic page tree (PageModel). Never returns raw HTML. No AI.
"""
from __future__ import annotations

from typing import Optional

from app.website_intelligence.locator_builder import build_locator
from app.website_intelligence.models import DomNode, PageModel, SemanticNode, SemanticType

_FILE_EXT = (".pdf", ".csv", ".xlsx", ".xls", ".zip", ".doc", ".docx", ".png", ".jpg", ".json", ".txt")
_DATE_TYPES = {"date", "datetime-local", "month", "week", "time"}

# Types that form the structural page tree (leaves like button/link go to the registry).
STRUCTURAL_TYPES = frozenset({
    SemanticType.header, SemanticType.footer, SemanticType.navigation, SemanticType.sidebar,
    SemanticType.toolbar, SemanticType.form, SemanticType.table, SemanticType.grid,
    SemanticType.list, SemanticType.card, SemanticType.dialog, SemanticType.menu,
    SemanticType.breadcrumb, SemanticType.tabs, SemanticType.accordion, SemanticType.tree,
    SemanticType.search_bar, SemanticType.filter, SemanticType.pagination, SemanticType.calendar,
    SemanticType.dashboard, SemanticType.section,
})


def _is_pagination_label(aria_label: str) -> bool:
    al = (aria_label or "").lower().strip()
    return "pagination" in al or "paging" in al or al.startswith("page navigation")


_DIALOG_ROLES = ("dialog", "alertdialog", "alert", "status", "tooltip")
_DIALOG_CLASSES = ("modal", "dialog", "toast", "snackbar", "drawer", "offcanvas",
                   "popover", "popup", "overlay", "backdrop", "alert")


def _is_dialogish(n: DomNode) -> bool:
    if n.tag == "dialog" or n.role in _DIALOG_ROLES:
        return True
    return bool(n.classes) and n.class_contains(*_DIALOG_CLASSES)


def classify(n: DomNode) -> tuple[Optional[SemanticType], float]:
    tag, role = n.tag, n.role
    # gate all class-substring branches: most nodes (cells, plain text) carry no class
    has_cls = bool(n.classes)
    al_low = (n.aria_label or "").lower()

    if tag == "dialog" or role in _DIALOG_ROLES or (has_cls and n.class_contains(*_DIALOG_CLASSES)):
        strong = tag == "dialog" or role in ("dialog", "alertdialog", "alert", "status")
        return SemanticType.dialog, 1.0 if strong else 0.7
    if tag == "header" or role == "banner":
        return SemanticType.header, 1.0
    if tag == "footer" or role == "contentinfo":
        return SemanticType.footer, 1.0
    if (tag in ("nav", "ol", "ul") or role == "navigation") and \
            ("breadcrumb" in al_low or (has_cls and n.class_contains("breadcrumb"))):
        return SemanticType.breadcrumb, 0.9
    if (tag in ("nav", "ul") or role == "navigation") and \
            (_is_pagination_label(n.aria_label) or (has_cls and n.class_contains("pagination", "pager"))):
        return SemanticType.pagination, 0.9
    if role == "tablist" or (has_cls and (n.class_contains("nav-tabs", "tablist") or (tag in ("ul", "div") and n.class_contains("tabs")))):
        return SemanticType.tabs, 1.0 if role == "tablist" else 0.8
    if tag == "nav" or role == "navigation":
        return SemanticType.navigation, 1.0
    if role == "toolbar" or (has_cls and n.class_contains("toolbar")):
        return SemanticType.toolbar, 1.0 if role == "toolbar" else 0.7
    if tag == "aside" or (has_cls and n.class_contains("sidebar", "sidenav", "side-nav")):
        return SemanticType.sidebar, 0.9 if tag == "aside" else 0.7
    if role == "search" or (tag == "form" and role == "search") or (tag == "input" and n.type == "search"):
        return SemanticType.search_bar, 0.9
    if tag == "form" or role == "form":
        return SemanticType.form, 1.0
    if tag == "table" or role == "table":
        return SemanticType.table, 1.0
    if role == "grid":
        return SemanticType.grid, 1.0
    if role == "tree":
        return SemanticType.tree, 1.0
    if role in ("menu", "menubar") or (has_cls and n.class_contains("menu", "dropdown-menu")):
        return SemanticType.menu, 1.0 if role in ("menu", "menubar") else 0.7
    if tag == "select" or role in ("listbox", "combobox") or (has_cls and n.class_contains("dropdown")):
        return SemanticType.dropdown, 1.0 if (tag == "select" or role in ("listbox", "combobox")) else 0.7
    if tag == "details" or (has_cls and n.class_contains("accordion")):
        return SemanticType.accordion, 0.9 if tag == "details" else 0.7
    if (tag == "input" and n.type in _DATE_TYPES) or (has_cls and n.class_contains("calendar", "datepicker")):
        return SemanticType.calendar, 0.8
    if tag == "input" and n.type == "file":
        return SemanticType.upload, 1.0
    if tag == "a" and (("download" in n.attrs) or any(n.href.lower().endswith(e) for e in _FILE_EXT)):
        return SemanticType.download, 0.9
    if (has_cls and n.class_contains("filter", "facet")) or "data-filter" in n.attrs:
        return SemanticType.filter, 0.7
    if has_cls and n.class_contains("dashboard"):
        return SemanticType.dashboard, 0.7
    if has_cls and n.class_contains("card"):
        return SemanticType.card, 0.7
    if tag == "button" or role == "button" or (tag == "input" and n.type in ("submit", "button", "image")):
        return SemanticType.button, 1.0 if (tag == "button" or role == "button") else 0.9
    if tag == "a" and n.href:
        return SemanticType.link, 0.9
    if tag in ("ul", "ol") or role == "list":
        return SemanticType.list, 0.6
    if tag in ("section", "main", "article"):
        return SemanticType.section, 0.8
    return None, 0.0


def _label(n: DomNode, stype: SemanticType) -> str:
    if n.aria_label:
        return n.aria_label
    if stype in (SemanticType.header, SemanticType.footer, SemanticType.section,
                 SemanticType.card, SemanticType.dialog, SemanticType.dashboard):
        h = n.find_first(lambda x: x.tag in ("h1", "h2", "h3", "h4", "h5", "h6"))
        if h is not None and h.text_content(60):
            return h.text_content(60)
    if stype == SemanticType.table:
        cap = n.find_first(lambda x: x.tag == "caption")
        if cap is not None and cap.text_content(60):
            return cap.text_content(60)
        if n.attr("summary"):
            return n.attr("summary")
    if stype in (SemanticType.button, SemanticType.link, SemanticType.download):
        t = n.text_content(40)
        if t:
            return t
    if stype == SemanticType.form:
        return n.attr("name") or n.id or "Form"
    if n.id:
        return n.id
    txt = n.text_content(40)
    return txt or stype.value.replace("_", " ").title()


_INTERACTIVE_TYPES = frozenset({
    SemanticType.button, SemanticType.link, SemanticType.upload, SemanticType.download,
    SemanticType.dropdown, SemanticType.search_bar, SemanticType.calendar,
})


def _build_tree(node: DomNode, counts: dict[str, int]) -> list[SemanticNode]:
    """
    Build structural semantic nodes from node's children (skipping generic containers),
    counting every classified node along the way (single pass — no separate census walk).
    """
    out: list[SemanticNode] = []
    for child in node.children:
        stype, conf = classify(child)
        if stype is not None:
            counts[stype.value] = counts.get(stype.value, 0) + 1
        if stype in STRUCTURAL_TYPES:
            label = _label(child, stype)
            sn = SemanticNode(
                type=stype, label=label,
                interactive=stype in _INTERACTIVE_TYPES, confidence=conf, tag=child.tag,
                locator=build_locator(child, label=child.aria_label or label),
            )
            sn.children = _build_tree(child, counts)
            out.append(sn)
        else:
            # generic/leaf container — splice in any significant descendants
            out.extend(_build_tree(child, counts))
    return out


def analyze_page(root: DomNode, *, url: str = "", title: str = "") -> PageModel:
    page_root = SemanticNode(type=SemanticType.page, label=title or "Page",
                             interactive=False, confidence=1.0, tag="body")
    counts: dict[str, int] = {}
    page_root.children = _build_tree(root, counts)
    sections = [c.label for c in page_root.children]
    return PageModel(url=url, title=title, root=page_root, sections=sections, type_counts=counts)
