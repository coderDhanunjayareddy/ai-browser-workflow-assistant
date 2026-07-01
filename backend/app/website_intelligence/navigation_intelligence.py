"""
Phase E — Navigation Intelligence (deterministic).

Detects primary/secondary navigation, breadcrumbs, tabs, menus, sidebars, the active
page, and the navigation hierarchy. No AI — pure DOM-driven rules.
"""
from __future__ import annotations

from typing import Optional

from app.website_intelligence.locator_builder import build_locator
from app.website_intelligence.models import DomNode, NavItem, NavigationModel


def _is_active(node: DomNode) -> bool:
    return node.attr("aria-current") == "page" or node.has_class("active", "current", "selected")


def _nav_item(link: DomNode, *, active_hint: bool = False) -> NavItem:
    label = (link.text_content(60) or link.aria_label or "").strip()
    return NavItem(
        label=label, href=link.href, active=_is_active(link) or active_hint,
        locator=build_locator(link, text=label),
    )


def _items_from_list(list_node: DomNode) -> list[NavItem]:
    items: list[NavItem] = []
    for li in [c for c in list_node.children if c.tag == "li"]:
        link = li.find_first(lambda n: n.tag == "a")
        label = ""
        href = ""
        if link is not None:
            label = (link.text_content(60) or link.aria_label or "").strip()
            href = link.href
        else:
            label = li.text_content(60)
        nested = None
        for c in li.children:
            if c.tag in ("ul", "ol"):
                nested = c
                break
        item = NavItem(
            label=label, href=href, active=_is_active(li) or (link is not None and _is_active(link)),
            children=_items_from_list(nested) if nested is not None else [],
            locator=build_locator(link if link is not None else li, text=label),
        )
        if item.label:
            items.append(item)
    return items


def _items(container: DomNode) -> list[NavItem]:
    first_list = container.find_first(lambda n: n.tag in ("ul", "ol"))
    if first_list is not None:
        items = _items_from_list(first_list)
        if items:
            return items
    links = container.find_all(lambda n: n.tag == "a" and bool(n.text_content(40)))
    return [_nav_item(a) for a in links]


def _is_breadcrumb(n: DomNode) -> bool:
    return "breadcrumb" in (n.aria_label or "").lower() or n.class_contains("breadcrumb")


def _is_tabs(n: DomNode) -> bool:
    return n.role == "tablist" or n.class_contains("nav-tabs", "tabs", "tablist")


def _is_menu(n: DomNode) -> bool:
    return n.role in ("menu", "menubar") or n.class_contains("menu", "dropdown-menu")


def _is_pag(n: DomNode) -> bool:
    al = (n.aria_label or "").lower().strip()
    return "pagination" in al or "paging" in al or al.startswith("page navigation") \
        or n.class_contains("pagination", "pager")


def analyze_navigation(root: DomNode) -> NavigationModel:
    model = NavigationModel()

    # single classification walk → bucket nav-relevant containers (was 5 find_all passes)
    breadcrumb_c: list[DomNode] = []
    tab_c: list[DomNode] = []
    menu_c: list[DomNode] = []
    sidebar_c: list[DomNode] = []
    nav_c: list[DomNode] = []
    for n in root.walk():
        is_nav = n.tag == "nav" or n.role == "navigation"
        if (is_nav or n.tag in ("ol", "ul")) and _is_breadcrumb(n):
            breadcrumb_c.append(n)
        if _is_tabs(n):
            tab_c.append(n)
        if _is_menu(n):
            menu_c.append(n)
        if n.tag == "aside" or n.class_contains("sidebar", "side-nav", "sidenav"):
            sidebar_c.append(n)
        if is_nav:
            nav_c.append(n)

    # breadcrumbs
    for bc in breadcrumb_c:
        model.breadcrumbs.extend(_items(bc))

    # tabs
    for tb in tab_c:
        if tb.role == "tablist":
            for tab in tb.find_all(lambda n: n.role == "tab" or n.tag in ("a", "button")):
                lbl = (tab.text_content(40) or tab.aria_label or "").strip()
                if lbl:
                    model.tabs.append(NavItem(label=lbl, active=_is_active(tab) or tab.attr("aria-selected") == "true",
                                              locator=build_locator(tab, text=lbl)))
        else:
            model.tabs.extend(_items(tb))

    # menus
    for mn in menu_c:
        model.menus.extend(_items(mn))

    # sidebars
    for sb in sidebar_c:
        model.sidebars.extend(_items(sb))

    # primary / secondary navigation (<nav> / role=navigation not already classified)
    plain = [n for n in nav_c if not _is_breadcrumb(n) and not _is_tabs(n) and not _is_pag(n)]
    for i, nav in enumerate(plain):
        items = _items(nav)
        if i == 0:
            model.primary.extend(items)
        else:
            model.secondary.extend(items)

    # active page
    for item in (model.primary + model.tabs + model.secondary + model.breadcrumbs):
        if item.active and item.label:
            model.active_page = item.label
            break

    return model
