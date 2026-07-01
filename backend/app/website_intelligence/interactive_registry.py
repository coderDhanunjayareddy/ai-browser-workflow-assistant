"""
Phase E — Interactive Element Registry (deterministic).

Every interactive component gets a semantic_id, role, category, priority, visibility,
enabled state, locator metadata, and a validation strategy. The Playwright adapter can
consume these (the locator params are resolver-ready) WITHOUT any public-API change —
consumption is opt-in; the registry never executes anything.
"""
from __future__ import annotations

from app.website_intelligence.locator_builder import build_locator
from app.website_intelligence.models import DomNode, ElementCategory, InteractiveElement, Priority

_FILE_EXT = (".pdf", ".csv", ".xlsx", ".xls", ".zip", ".doc", ".docx", ".png", ".jpg", ".json", ".txt")
_INTERACTIVE_ROLES = {"button", "link", "checkbox", "radio", "menuitem", "tab", "option",
                      "switch", "textbox", "combobox", "listbox", "slider", "searchbox"}
_PRIMARY_WORDS = ("submit", "save", "continue", "sign in", "log in", "buy", "checkout", "confirm", "search")


def _is_interactive(n: DomNode) -> bool:
    if n.tag in ("button", "select", "textarea"):
        return True
    if n.tag == "a" and n.href:
        return True
    if n.tag == "input" and n.type not in ("hidden",):
        return True
    if n.role in _INTERACTIVE_ROLES:
        return True
    if "onclick" in n.attrs or n.attr("tabindex") not in ("", "-1"):
        return n.tag in ("div", "span", "li") and bool(n.text_content(20))
    return False


def _category(n: DomNode) -> ElementCategory:
    if n.tag == "input" and n.type == "file":
        return ElementCategory.upload
    if n.tag == "a" and (("download" in n.attrs) or any(n.href.lower().endswith(e) for e in _FILE_EXT)):
        return ElementCategory.download
    if n.tag == "a" or n.role == "link":
        return ElementCategory.link
    if n.tag == "button" or n.role == "button" or (n.tag == "input" and n.type in ("submit", "button", "image")):
        return ElementCategory.button
    if (n.tag == "input" and n.type in ("checkbox", "radio")) or n.role in ("checkbox", "radio", "switch"):
        return ElementCategory.toggle
    if n.tag == "select" or n.role in ("listbox", "combobox"):
        return ElementCategory.selection
    if n.tag in ("input", "textarea") or n.role in ("textbox", "searchbox"):
        return ElementCategory.form_control
    return ElementCategory.other


def _role(n: DomNode, cat: ElementCategory) -> str:
    if n.role:
        return n.role
    return {
        ElementCategory.button: "button", ElementCategory.link: "link",
        ElementCategory.upload: "button", ElementCategory.download: "link",
        ElementCategory.toggle: "checkbox", ElementCategory.selection: "combobox",
        ElementCategory.form_control: "textbox", ElementCategory.other: "generic",
    }[cat]


def _label(n: DomNode) -> str:
    return (n.aria_label or n.text_content(40) or n.value or n.placeholder or n.name or n.id or "").strip()


def _priority(n: DomNode, cat: ElementCategory, label: str) -> Priority:
    low = label.lower()
    if cat == ElementCategory.button:
        if n.type == "submit" or n.class_contains("primary", "btn-primary", "cta") or any(w in low for w in _PRIMARY_WORDS):
            return Priority.primary
        return Priority.secondary
    if cat in (ElementCategory.upload, ElementCategory.download, ElementCategory.selection):
        return Priority.secondary
    if cat == ElementCategory.link:
        return Priority.secondary
    if cat == ElementCategory.form_control:
        return Priority.secondary
    return Priority.tertiary


def _validation_strategy(n: DomNode, cat: ElementCategory) -> str:
    if cat == ElementCategory.link and n.href and not n.href.startswith("#"):
        return "URL_MATCH"
    if cat == ElementCategory.form_control:
        return "VALUE_EQUALS"
    if cat == ElementCategory.download:
        return "FILE_EXISTS"
    return "DOM_PRESENCE"


def build_registry(root: DomNode) -> list[InteractiveElement]:
    out: list[InteractiveElement] = []
    used: set[str] = set()
    idx = 0
    for n in root.walk():
        if not _is_interactive(n):
            continue
        cat = _category(n)
        label = _label(n)
        role = _role(n, cat)
        base = n.testid or n.id or n.name or f"{cat.value.lower()}-{idx}"
        sid = base
        suffix = 0
        while sid in used:
            suffix += 1
            sid = f"{base}-{suffix}"
        used.add(sid)
        idx += 1
        out.append(InteractiveElement(
            semantic_id=sid, role=role, category=cat,
            priority=_priority(n, cat, label), label=label,
            visible=n.visible, enabled=not n.disabled,
            validation_strategy=_validation_strategy(n, cat),
            locator=build_locator(n, text=label if cat in (ElementCategory.button, ElementCategory.link, ElementCategory.download) else None),
        ))
    return out
