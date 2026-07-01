"""
Phase E — Semantic Locator Builder.

Produces deterministic LocatorMetadata for a DomNode by extracting the strongest
stable identifiers and ordering them by the EXISTING adaptive-resolver priority
(EXTENDED_RESOLUTION_PRIORITY). It does NOT resolve or duplicate locator logic — it
emits a params dict that the existing ElementResolver / AdaptiveResolver consumes
unchanged. A deterministic CSS + XPath fallback is always provided.
"""
from __future__ import annotations

import re
from typing import Optional

from app.execution_gateway.browser.capabilities import EXTENDED_RESOLUTION_PRIORITY
from app.website_intelligence.models import DomNode, LocatorMetadata

# A CSS-safe identifier: starts with a letter/_/- and contains only [A-Za-z0-9_-].
_SIMPLE_IDENT = re.compile(r"[A-Za-z_-][A-Za-z0-9_-]*$")


def _css_escape(value: str) -> str:
    return value.replace('"', '\\"')


def _xpath_lit(s: str) -> str:
    """Quote a string as an XPath 1.0 literal, handling embedded quotes safely."""
    if '"' not in s:
        return f'"{s}"'
    if "'" not in s:
        return f"'{s}'"
    parts = s.split('"')
    return "concat(" + ", '\"', ".join(f'"{p}"' for p in parts) + ")"


def _build_css(node: DomNode) -> str:
    tag = node.tag or "*"
    if node.id:
        # ids that aren't simple CSS identifiers (digit-leading, special chars) use [id=]
        return f'{tag}#{node.id}' if _SIMPLE_IDENT.fullmatch(node.id) and not node.id[0].isdigit() \
            else f'{tag}[id="{_css_escape(node.id)}"]'
    if node.testid:
        return f'{tag}[data-testid="{_css_escape(node.testid)}"]'
    if node.name:
        return f'{tag}[name="{_css_escape(node.name)}"]'
    # only a class that is a valid CSS identifier (skips Tailwind-style w-1/2, hover:bg, top-[3px])
    simple = [c for c in node.class_list if _SIMPLE_IDENT.fullmatch(c)]
    if simple:
        return f'{tag}.{simple[0]}'
    return tag


def _build_xpath(node: DomNode, text: str) -> str:
    if node.id:
        return f'//*[@id={_xpath_lit(node.id)}]'
    if node.testid:
        return f'//*[@data-testid={_xpath_lit(node.testid)}]'
    if text:
        return f'//{node.tag or "*"}[normalize-space()={_xpath_lit(text)}]'
    if node.name:
        return f'//{node.tag or "*"}[@name={_xpath_lit(node.name)}]'
    return f'//{node.tag or "*"}'


def build_locator(node: DomNode, *, label: Optional[str] = None, text: Optional[str] = None) -> LocatorMetadata:
    """Build resolver-consumable locator metadata in adaptive-resolver priority order."""
    eff_text = (text if text is not None else node.text) or ""
    eff_text = eff_text.strip()

    derived: dict[str, str] = {}
    if node.testid:
        derived["testid"] = node.testid
    if node.aria_label:
        derived["aria_label"] = node.aria_label
    if node.role:
        derived["role"] = node.role
        rn = node.aria_label or label or eff_text
        if rn:
            derived["role_name"] = rn.strip()
    if label:
        derived["label"] = label.strip()
    if node.placeholder:
        derived["placeholder"] = node.placeholder
    if eff_text and node.tag in ("button", "a", "summary", "label", "option"):
        derived["text"] = eff_text
    if node.id:
        derived["id"] = node.id
    if node.name:
        derived["name"] = node.name

    css = _build_css(node)
    xpath = _build_xpath(node, eff_text)
    derived["css"] = css
    derived["xpath"] = xpath

    # candidates = strategies present, in resolver priority order (excluding role_name helper)
    candidates = [s for s in EXTENDED_RESOLUTION_PRIORITY if s in derived]
    primary = candidates[0] if candidates else "css"

    # params keeps every derived strategy (role_name retained for the role builder)
    return LocatorMetadata(
        primary_strategy=primary,
        params=derived,
        candidates=candidates,
        css=css,
        xpath=xpath,
    )
