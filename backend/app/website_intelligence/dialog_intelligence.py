"""
Phase E — Dialog Intelligence (deterministic).

Recognizes modal dialogs, confirmation dialogs, alerts, toast messages, drawers,
popups, and blocking overlays — and reports their state (visible, blocking,
dismissible, buttons). No AI — pure DOM-driven rules.
"""
from __future__ import annotations

from app.website_intelligence.locator_builder import build_locator
from app.website_intelligence.models import DomNode, DialogModel

_CONFIRM_WORDS = ("confirm", "cancel", "yes", "no", "ok", "delete", "discard", "accept", "decline")
# substring-safe close words (distinct enough not to false-match)
_CLOSE_SUBSTR = ("close", "dismiss", "×")
# exact-match-only close labels (the bare letter "x" must never match "Next"/"Exit")
_CLOSE_EXACT = ("x", "close", "dismiss")


def _kind(n: DomNode) -> str:
    role = n.role
    if role == "alert":
        return "alert"
    if role == "alertdialog":
        return "confirmation"
    if role == "status":
        return "toast"
    if role == "dialog" or n.tag == "dialog":
        return "modal"
    if role == "tooltip":
        return "popup"
    if n.class_contains("toast", "snackbar"):
        return "toast"
    if n.class_contains("drawer", "offcanvas"):
        return "drawer"
    if n.class_contains("popover", "popup"):
        return "popup"
    if n.class_contains("overlay", "backdrop"):
        return "overlay"
    if n.class_contains("alert"):
        return "alert"
    if n.class_contains("modal", "dialog"):
        return "modal"
    return "modal"


def _buttons(n: DomNode) -> list[str]:
    out: list[str] = []
    for b in n.find_all(lambda x: x.tag == "button" or x.role == "button"
                        or (x.tag == "input" and x.type in ("button", "submit"))):
        lbl = (b.text_content(30) or b.value or b.aria_label or "").strip()
        if lbl and lbl not in out:
            out.append(lbl)
    return out


def _has_close(n: DomNode) -> bool:
    for b in n.find_all(lambda x: x.tag in ("button", "a") or x.role == "button"):
        txt = (b.text_content(20) or b.aria_label or "").lower().strip()
        if b.class_contains("close", "dismiss"):
            return True
        if txt in _CLOSE_EXACT:                                  # exact match (incl. bare "x")
            return True
        if any(w in txt for w in _CLOSE_SUBSTR):                 # substring (close/dismiss/×)
            return True
    return False


def _is_dialog_node(n: DomNode) -> bool:
    if n.tag == "dialog":
        return True
    if n.role in ("dialog", "alertdialog", "alert", "status", "tooltip"):
        return True
    return n.class_contains("modal", "dialog", "toast", "snackbar", "drawer", "offcanvas",
                            "popover", "popup", "overlay", "backdrop", "alert")


def analyze_dialogs(root: DomNode) -> list[DialogModel]:
    nodes = root.find_all(_is_dialog_node)
    if _is_dialog_node(root):
        nodes = [root] + nodes
    # de-duplicate nested overlay+modal (keep the outermost unique by identity)
    seen: set[int] = set()
    out: list[DialogModel] = []
    for i, n in enumerate(nodes):
        if id(n) in seen:
            continue
        seen.add(id(n))
        kind = _kind(n)
        buttons = _buttons(n)
        has_close = _has_close(n)
        is_confirm = kind == "confirmation" or any(
            any(w in b.lower() for w in _CONFIRM_WORDS) for b in buttons)
        if is_confirm and kind == "modal":
            kind = "confirmation"
        blocking = kind in ("modal", "confirmation", "overlay") or n.attr("aria-modal") == "true"
        dismissible = has_close or kind in ("toast", "popup", "alert", "drawer") or \
            any("cancel" in b.lower() or "close" in b.lower() for b in buttons)
        # aria-labelledby holds element ID references (not visible text) — never use it
        # as the human-readable label; prefer aria-label, then a heading, then text.
        label = (n.aria_label or "").strip()
        if not label:
            heading = n.find_first(lambda x: x.tag in ("h1", "h2", "h3", "h4"))
            label = heading.text_content(60) if heading else (n.text_content(60))
        out.append(DialogModel(
            dialog_id=n.id or n.testid or f"dialog-{i}",
            kind=kind, label=label, visible=n.visible, blocking=blocking,
            dismissible=dismissible, buttons=buttons,
            locator=build_locator(n, label=n.aria_label or label),
        ))
    return out
