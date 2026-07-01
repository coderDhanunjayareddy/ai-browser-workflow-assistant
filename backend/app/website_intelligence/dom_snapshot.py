"""
Phase E — DOM Snapshot capture (read-only).

The SINGLE point of contact with a real browser: one read-only `page.evaluate` that
serializes the DOM into a DomNode tree. No clicks, no navigation, no mutation.

`from_html` builds the SAME DomNode tree from an HTML string using the Python stdlib
html.parser, so every analyzer is fully testable without a browser and the validation
suite is deterministic.
"""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any, Optional

from app.website_intelligence.models import DomNode

# Void elements (no closing tag).
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}

# One read-only DOM serialization. Returns a nested dict tree rooted at <body>.
CAPTURE_JS = r"""
() => {
  function vis(el){
    try {
      const s = getComputedStyle(el);
      if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false;
      if (el.hasAttribute('hidden')) return false;
      const r = el.getBoundingClientRect();
      return (r.width > 0 || r.height > 0);
    } catch(e){ return true; }
  }
  function attrs(el){ const o={}; for (const a of el.attributes){ o[a.name]=a.value; } return o; }
  function directText(el){
    let t = '';
    for (const c of el.childNodes){ if (c.nodeType === 3) t += c.textContent; }
    return t.replace(/\s+/g,' ').trim().slice(0,200);
  }
  function node(el, depth){
    if (depth > 60) return null;
    const a = attrs(el);
    const children = [];
    for (const c of el.children){ const n = node(c, depth+1); if (n) children.push(n); }
    return {
      tag: el.tagName.toLowerCase(),
      attrs: a,
      role: a['role'] || '',
      id: el.id || '',
      classes: (el.getAttribute('class') || ''),
      name: a['name'] || '',
      type: a['type'] || '',
      placeholder: a['placeholder'] || '',
      aria_label: a['aria-label'] || '',
      testid: a['data-testid'] || '',
      href: a['href'] || '',
      value: (el.value !== undefined ? String(el.value || '') : (a['value'] || '')),
      text: directText(el),
      visible: vis(el),
      disabled: (el.disabled === true) || a['aria-disabled'] === 'true' || ('disabled' in a),
      children: children,
    };
  }
  return node(document.body, 0);
}
"""


def capture(page: Any) -> DomNode:
    """Capture the live page DOM (read-only). One evaluate, then pure-Python analysis."""
    raw = page.evaluate(CAPTURE_JS)
    return from_dict(raw)


def from_dict(d: dict) -> DomNode:
    if not d:
        return DomNode(tag="body")
    node = DomNode(
        tag=d.get("tag", "div"),
        attrs=dict(d.get("attrs", {}) or {}),
        text=d.get("text", "") or "",
        role=d.get("role", "") or "",
        id=d.get("id", "") or "",
        classes=d.get("classes", "") or "",
        name=d.get("name", "") or "",
        type=d.get("type", "") or "",
        placeholder=d.get("placeholder", "") or "",
        aria_label=d.get("aria_label", "") or "",
        testid=d.get("testid", "") or "",
        href=d.get("href", "") or "",
        value=d.get("value", "") or "",
        visible=bool(d.get("visible", True)),
        disabled=bool(d.get("disabled", False)),
    )
    node.children = [from_dict(c) for c in (d.get("children", []) or []) if c]
    return node


# ── Browser-free path: build a DomNode from an HTML string ────────────────────

class _SnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = DomNode(tag="body")
        self._stack: list[DomNode] = [self.root]

    def _make(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> DomNode:
        a = {k: (v if v is not None else "") for k, v in attrs}
        style = (a.get("style", "") or "").replace(" ", "").lower()
        hidden = ("display:none" in style or "visibility:hidden" in style
                  or "hidden" in a or a.get("type", "") == "hidden")
        disabled = ("disabled" in a) or (a.get("aria-disabled", "") == "true")
        return DomNode(
            tag=tag.lower(), attrs=a,
            role=a.get("role", ""), id=a.get("id", ""), classes=a.get("class", ""),
            name=a.get("name", ""), type=a.get("type", ""), placeholder=a.get("placeholder", ""),
            aria_label=a.get("aria-label", ""), testid=a.get("data-testid", ""),
            href=a.get("href", ""), value=a.get("value", ""),
            visible=not hidden, disabled=disabled,
        )

    def handle_starttag(self, tag, attrs):
        node = self._make(tag, attrs)
        self._stack[-1].children.append(node)
        if tag.lower() not in _VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = self._make(tag, attrs)
        self._stack[-1].children.append(node)

    def handle_endtag(self, tag):
        t = tag.lower()
        # pop to the matching open tag, if any
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == t:
                del self._stack[i:]
                break

    def handle_data(self, data):
        text = (data or "").strip()
        if text and len(self._stack) > 0:
            cur = self._stack[-1]
            cur.text = (cur.text + " " + text).strip()[:200] if cur.text else text[:200]


def from_html(html: str, *, url: str = "", title: str = "") -> DomNode:
    """Deterministically parse an HTML string into a DomNode tree (no browser)."""
    parser = _SnapshotParser()
    parser.feed(html or "")
    parser.close()
    root = parser.root
    # If the document has a single <html>/<body>, prefer the <body> subtree as root.
    body = root.find_first(lambda n: n.tag == "body")
    if body is not None:
        return body
    return root
