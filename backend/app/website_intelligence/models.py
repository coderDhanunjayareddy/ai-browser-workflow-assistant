"""
Phase E — Website Intelligence — Domain Models.

DomNode             : a serializable DOM node (the single input to every analyzer)
SemanticType        : the catalogue of semantic UI structures
ElementCategory     : coarse interactive category
Priority            : interaction priority
LocatorMetadata     : deterministic locator params (reuses the resolver strategy names)
SemanticNode        : a node in the semantic page tree
PageModel           : the deterministic semantic page-structure model
FormField/FormModel : form intelligence
TableColumn/TableModel : table intelligence
NavItem/NavigationModel : navigation intelligence
DialogModel         : dialog intelligence
InteractiveElement  : interactive registry entry
ExecutionHint       : advisory execution hint
WebsiteIntelligenceResult : the aggregate result
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ── DOM snapshot node ─────────────────────────────────────────────────────────

@dataclass
class DomNode:
    tag:         str
    attrs:       dict[str, str]   = field(default_factory=dict)
    text:        str              = ""
    children:    list["DomNode"]  = field(default_factory=list)
    # convenience-extracted attributes (mirror the capture JS)
    role:        str              = ""
    id:          str              = ""
    classes:     str              = ""
    name:        str              = ""
    type:        str              = ""
    placeholder: str              = ""
    aria_label:  str              = ""
    testid:      str              = ""
    href:        str              = ""
    value:       str              = ""
    visible:     bool             = True
    disabled:    bool             = False

    # ── traversal ──────────────────────────────────────────────────────────────

    @property
    def class_list(self) -> list[str]:
        cl = self.__dict__.get("_class_list")
        if cl is None:
            cl = [c for c in (self.classes or "").split() if c]
            self.__dict__["_class_list"] = cl
        return cl

    @property
    def _classes_low(self) -> str:
        low = self.__dict__.get("_cl_low")
        if low is None:
            low = (self.classes or "").lower()
            self.__dict__["_cl_low"] = low
        return low

    def attr(self, name: str, default: str = "") -> str:
        return self.attrs.get(name, default)

    def has_class(self, *names: str) -> bool:
        cl = set(self.class_list)
        return any(n in cl for n in names)

    def class_contains(self, *fragments: str) -> bool:
        low = self._classes_low
        return any(fr in low for fr in fragments)

    def walk(self):
        """Yield self then every descendant (pre-order)."""
        yield self
        for c in self.children:
            yield from c.walk()

    def descendants(self):
        for c in self.children:
            yield from c.walk()

    def find_all(self, pred) -> list["DomNode"]:
        return [n for n in self.descendants() if pred(n)]

    def find_first(self, pred) -> Optional["DomNode"]:
        for n in self.descendants():
            if pred(n):
                return n
        return None

    def find_by_tag(self, *tags: str) -> list["DomNode"]:
        s = {t.lower() for t in tags}
        return [n for n in self.descendants() if n.tag in s]

    def text_content(self, limit: int = 200) -> str:
        """Aggregate visible text of self + descendants, trimmed. Short-circuits at limit."""
        parts: list[str] = []
        total = 0
        for n in self.walk():
            if n.text:
                t = n.text.strip()
                if t:
                    parts.append(t)
                    total += len(t) + 1
                    if total >= limit:
                        break
        return " ".join(parts)[:limit].strip()

    def node_count(self) -> int:
        return sum(1 for _ in self.walk())

    def to_dict(self, include_children: bool = True, depth: int = 0, max_depth: int = 60) -> dict[str, Any]:
        d = {
            "tag": self.tag, "role": self.role, "id": self.id, "classes": self.classes,
            "name": self.name, "type": self.type, "placeholder": self.placeholder,
            "aria_label": self.aria_label, "testid": self.testid, "href": self.href,
            "text": self.text, "visible": self.visible, "disabled": self.disabled,
            "attrs": self.attrs,
        }
        if include_children and depth < max_depth:
            d["children"] = [c.to_dict(True, depth + 1, max_depth) for c in self.children]
        return d


# ── Enums ─────────────────────────────────────────────────────────────────────

class SemanticType(str, Enum):
    page          = "PAGE"
    header        = "HEADER"
    footer        = "FOOTER"
    navigation    = "NAVIGATION"
    form          = "FORM"
    table         = "TABLE"
    grid          = "GRID"
    list          = "LIST"
    card          = "CARD"
    dialog        = "DIALOG"
    menu          = "MENU"
    dropdown      = "DROPDOWN"
    breadcrumb    = "BREADCRUMB"
    tabs          = "TABS"
    accordion     = "ACCORDION"
    tree          = "TREE"
    search_bar    = "SEARCH_BAR"
    filter        = "FILTER"
    upload        = "UPLOAD"
    download      = "DOWNLOAD"
    button        = "BUTTON"
    link          = "LINK"
    toolbar       = "TOOLBAR"
    sidebar       = "SIDEBAR"
    pagination    = "PAGINATION"
    calendar      = "CALENDAR"
    dashboard     = "DASHBOARD"
    section       = "SECTION"
    container     = "CONTAINER"


class ElementCategory(str, Enum):
    form_control = "FORM_CONTROL"
    button       = "BUTTON"
    link         = "LINK"
    navigation   = "NAVIGATION"
    upload       = "UPLOAD"
    download     = "DOWNLOAD"
    toggle       = "TOGGLE"
    selection    = "SELECTION"
    other        = "OTHER"


class Priority(str, Enum):
    primary   = "PRIMARY"
    secondary = "SECONDARY"
    tertiary  = "TERTIARY"


# ── Locator metadata (reuses resolver strategy names) ─────────────────────────

@dataclass
class LocatorMetadata:
    primary_strategy: str               # one of the resolver strategies
    params:           dict[str, str]    # resolver-consumable params (priority-ordered)
    candidates:       list[str]         = field(default_factory=list)   # strategies present, in priority order
    css:              str               = ""
    xpath:            str               = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_strategy": self.primary_strategy,
            "params":           self.params,
            "candidates":       self.candidates,
            "css":              self.css,
            "xpath":            self.xpath,
        }


# ── Semantic node / page model ────────────────────────────────────────────────

@dataclass
class SemanticNode:
    type:        SemanticType
    label:       str
    interactive: bool
    confidence:  float
    locator:     Optional[LocatorMetadata] = None
    children:    list["SemanticNode"]      = field(default_factory=list)
    tag:         str                       = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type":        self.type.value,
            "label":       self.label,
            "interactive": self.interactive,
            "confidence":  self.confidence,
            "tag":         self.tag,
            "locator":     self.locator.to_dict() if self.locator else None,
            "children":    [c.to_dict() for c in self.children],
        }

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class PageModel:
    url:        str
    title:      str
    root:       SemanticNode
    sections:   list[str]              = field(default_factory=list)
    type_counts: dict[str, int]        = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url":        self.url,
            "title":      self.title,
            "sections":   self.sections,
            "type_counts": self.type_counts,
            "root":       self.root.to_dict(),
        }


# ── Form intelligence ─────────────────────────────────────────────────────────

@dataclass
class FormField:
    name:         str
    label:        str
    field_type:   str                     # text|password|email|checkbox|radio|file|date|select|textarea|...
    required:     bool                     = False
    placeholder:  str                      = ""
    autocomplete: str                      = ""
    options:      list[str]                = field(default_factory=list)
    group:        str                      = ""
    validation_hint: str                   = ""
    locator:      Optional[LocatorMetadata] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "label": self.label, "field_type": self.field_type,
            "required": self.required, "placeholder": self.placeholder,
            "autocomplete": self.autocomplete, "options": self.options, "group": self.group,
            "validation_hint": self.validation_hint,
            "locator": self.locator.to_dict() if self.locator else None,
        }


@dataclass
class FormModel:
    form_id:           str
    label:             str
    fields:            list[FormField]       = field(default_factory=list)
    field_groups:      dict[str, list[str]]  = field(default_factory=dict)
    submit_label:      Optional[str]         = None
    reset_label:       Optional[str]         = None
    has_password:      bool                  = False
    has_file_upload:   bool                  = False
    has_date_picker:   bool                  = False
    checkbox_groups:   list[str]             = field(default_factory=list)
    radio_groups:      list[str]             = field(default_factory=list)
    required_count:    int                   = 0
    validation_hints:  list[str]             = field(default_factory=list)
    locator:           Optional[LocatorMetadata] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "form_id": self.form_id, "label": self.label,
            "fields": [f.to_dict() for f in self.fields],
            "field_groups": self.field_groups, "submit_label": self.submit_label,
            "reset_label": self.reset_label, "has_password": self.has_password,
            "has_file_upload": self.has_file_upload, "has_date_picker": self.has_date_picker,
            "checkbox_groups": self.checkbox_groups, "radio_groups": self.radio_groups,
            "required_count": self.required_count, "validation_hints": self.validation_hints,
            "field_count": len(self.fields),
            "locator": self.locator.to_dict() if self.locator else None,
        }


# ── Table intelligence ────────────────────────────────────────────────────────

@dataclass
class TableColumn:
    index:    int
    header:   str
    sortable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "header": self.header, "sortable": self.sortable}


@dataclass
class TableModel:
    table_id:          str
    label:             str
    headers:           list[str]            = field(default_factory=list)
    columns:           list[TableColumn]    = field(default_factory=list)
    row_count:         int                  = 0
    sortable_columns:  list[str]            = field(default_factory=list)
    has_pagination:    bool                 = False
    has_selection:     bool                 = False
    has_search:        bool                 = False
    has_filters:       bool                 = False
    action_buttons:    list[str]            = field(default_factory=list)
    export_buttons:    list[str]            = field(default_factory=list)
    locator:           Optional[LocatorMetadata] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id, "label": self.label, "headers": self.headers,
            "columns": [c.to_dict() for c in self.columns], "row_count": self.row_count,
            "column_count": len(self.headers), "sortable_columns": self.sortable_columns,
            "has_pagination": self.has_pagination, "has_selection": self.has_selection,
            "has_search": self.has_search, "has_filters": self.has_filters,
            "action_buttons": self.action_buttons, "export_buttons": self.export_buttons,
            "locator": self.locator.to_dict() if self.locator else None,
        }


# ── Navigation intelligence ───────────────────────────────────────────────────

@dataclass
class NavItem:
    label:    str
    href:     str                       = ""
    active:   bool                      = False
    children: list["NavItem"]           = field(default_factory=list)
    locator:  Optional[LocatorMetadata] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label, "href": self.href, "active": self.active,
            "children": [c.to_dict() for c in self.children],
            "locator": self.locator.to_dict() if self.locator else None,
        }


@dataclass
class NavigationModel:
    primary:      list[NavItem]   = field(default_factory=list)
    secondary:    list[NavItem]   = field(default_factory=list)
    breadcrumbs:  list[NavItem]   = field(default_factory=list)
    tabs:         list[NavItem]   = field(default_factory=list)
    menus:        list[NavItem]   = field(default_factory=list)
    sidebars:     list[NavItem]   = field(default_factory=list)
    active_page:  Optional[str]   = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary":     [n.to_dict() for n in self.primary],
            "secondary":   [n.to_dict() for n in self.secondary],
            "breadcrumbs": [n.to_dict() for n in self.breadcrumbs],
            "tabs":        [n.to_dict() for n in self.tabs],
            "menus":       [n.to_dict() for n in self.menus],
            "sidebars":    [n.to_dict() for n in self.sidebars],
            "active_page": self.active_page,
        }


# ── Dialog intelligence ───────────────────────────────────────────────────────

@dataclass
class DialogModel:
    dialog_id:   str
    kind:        str                       # modal|confirmation|alert|toast|drawer|popup|overlay
    label:       str                       = ""
    visible:     bool                      = True
    blocking:    bool                      = False
    dismissible: bool                      = True
    buttons:     list[str]                 = field(default_factory=list)
    locator:     Optional[LocatorMetadata] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialog_id": self.dialog_id, "kind": self.kind, "label": self.label,
            "visible": self.visible, "blocking": self.blocking, "dismissible": self.dismissible,
            "buttons": self.buttons,
            "locator": self.locator.to_dict() if self.locator else None,
        }


# ── Interactive registry ──────────────────────────────────────────────────────

@dataclass
class InteractiveElement:
    semantic_id:        str
    role:               str
    category:           ElementCategory
    priority:           Priority
    label:              str
    visible:            bool                  = True
    enabled:            bool                  = True
    validation_strategy: str                  = "DOM_PRESENCE"
    locator:            Optional[LocatorMetadata] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_id": self.semantic_id, "role": self.role,
            "category": self.category.value, "priority": self.priority.value,
            "label": self.label, "visible": self.visible, "enabled": self.enabled,
            "validation_strategy": self.validation_strategy,
            "locator": self.locator.to_dict() if self.locator else None,
        }


# ── Execution hints (advisory only) ───────────────────────────────────────────

@dataclass
class ExecutionHint:
    hint_type:  str                    # preferred_validation|wait_strategy|loading_indicator|expected_*
    target:     str                    # semantic_id or label this hint refers to
    value:      str
    confidence: float                  = 0.5
    advisory:   bool                   = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "hint_type": self.hint_type, "target": self.target, "value": self.value,
            "confidence": self.confidence, "advisory": self.advisory,
        }


# ── Aggregate result ──────────────────────────────────────────────────────────

@dataclass
class WebsiteIntelligenceResult:
    url:          str
    title:        str
    page:         PageModel
    forms:        list[FormModel]
    tables:       list[TableModel]
    navigation:   NavigationModel
    dialogs:      list[DialogModel]
    registry:     list[InteractiveElement]
    hints:        list[ExecutionHint]
    stats:        dict[str, Any]            = field(default_factory=dict)
    latency_ms:   float                     = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url, "title": self.title,
            "page": self.page.to_dict(),
            "forms": [f.to_dict() for f in self.forms],
            "tables": [t.to_dict() for t in self.tables],
            "navigation": self.navigation.to_dict(),
            "dialogs": [d.to_dict() for d in self.dialogs],
            "registry": [e.to_dict() for e in self.registry],
            "hints": [h.to_dict() for h in self.hints],
            "stats": self.stats,
            "latency_ms": self.latency_ms,
        }
