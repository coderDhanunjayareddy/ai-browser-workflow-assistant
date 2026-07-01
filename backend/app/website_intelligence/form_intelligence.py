"""
Phase E — Form Intelligence (deterministic).

Turns raw <form>/inputs into semantic FormModel objects: labels, required fields,
field groups, validation hints, submit/reset buttons, password/file/date detection,
checkbox/radio groups. No AI — pure DOM-driven rules.
"""
from __future__ import annotations

import re
from typing import Optional

from app.website_intelligence.locator_builder import build_locator
from app.website_intelligence.models import DomNode, FormField, FormModel

_FIELD_TAGS = {"input", "select", "textarea"}
_SKIP_INPUT_TYPES = {"hidden", "submit", "reset", "button", "image"}
_DATE_TYPES = {"date", "datetime-local", "month", "week", "time"}
_SUBMIT_WORDS = ("submit", "save", "send", "continue", "next", "search", "apply", "ok", "sign in", "log in")


def _truthy_attr(node: DomNode, name: str) -> bool:
    """A boolean HTML attribute is true iff PRESENT (value ''/'true'/name)."""
    if name not in node.attrs:
        return False
    return node.attrs[name] in ("", "true", name)


def _label_map(form: DomNode) -> tuple[dict[str, str], dict[int, str]]:
    """Return (for_id -> label_text, id(field_node) -> wrapping_label_text)."""
    by_for: dict[str, str] = {}
    by_wrap: dict[int, str] = {}
    for lbl in form.find_by_tag("label"):
        txt = lbl.text_content(120)
        for_id = lbl.attr("for")
        if for_id:
            by_for[for_id] = txt
        # wrapping: any field descendant of this label
        for fld in lbl.find_all(lambda n: n.tag in _FIELD_TAGS):
            by_wrap[id(fld)] = txt
    return by_for, by_wrap


def _field_label(field: DomNode, by_for: dict[str, str], by_wrap: dict[int, str]) -> str:
    if field.aria_label:
        return field.aria_label
    if field.id and field.id in by_for:
        return by_for[field.id]
    if id(field) in by_wrap:
        return by_wrap[id(field)]
    if field.placeholder:
        return field.placeholder
    return field.name or ""


def _field_type(field: DomNode) -> str:
    if field.tag == "select":
        return "select"
    if field.tag == "textarea":
        return "textarea"
    return (field.type or "text").lower()


def _validation_hint(field: DomNode, ftype: str, required: bool) -> str:
    hints = []
    if required:
        hints.append("required")
    if ftype == "email":
        hints.append("email format")
    elif ftype == "url":
        hints.append("url format")
    elif ftype == "tel":
        hints.append("phone format")
    elif ftype == "number":
        if field.attr("min") or field.attr("max"):
            hints.append(f"range {field.attr('min', '?')}..{field.attr('max', '?')}")
    if field.attr("pattern"):
        hints.append("pattern")
    if field.attr("minlength") or field.attr("maxlength"):
        hints.append("length")
    return ", ".join(hints)


def _options(field: DomNode) -> list[str]:
    if field.tag == "select":
        return [o.text_content(60) for o in field.find_by_tag("option") if o.text_content(60)]
    return []


def _is_submit(node: DomNode) -> bool:
    if node.tag == "input" and node.type in ("submit", "image"):
        return True
    if node.tag == "button":
        if node.type in ("submit", ""):  # default button type in a form is submit
            txt = (node.text_content(40) or node.value or "").lower()
            return node.type == "submit" or any(w in txt for w in _SUBMIT_WORDS) or node.type == ""
    return False


def _is_reset(node: DomNode) -> bool:
    # explicit reset controls
    if node.tag == "input" and node.type == "reset":
        return True
    if node.tag == "button" and node.type == "reset":
        return True
    # JS clear/reset buttons are explicitly type=button (NOT submit — a typeless <button>
    # in a form defaults to submit, so we never steal it). Word-boundary match only.
    if node.tag == "button" and node.type == "button":
        txt = (node.text_content(40) or node.value or "").lower()
        words = set(re.split(r"[^a-z]+", txt))
        return "reset" in words or "clear" in words
    return False


def analyze_form(form: DomNode, index: int = 0) -> FormModel:
    by_for, by_wrap = _label_map(form)
    fields: list[FormField] = []
    fieldsets = form.find_by_tag("fieldset")
    # map field id -> group (fieldset legend)
    group_of: dict[int, str] = {}
    field_groups: dict[str, list[str]] = {}
    for fs in fieldsets:
        legend = fs.find_first(lambda n: n.tag == "legend")
        gname = (legend.text_content(60) if legend else "") or "group"
        members = []
        for fld in fs.find_all(lambda n: n.tag in _FIELD_TAGS):
            group_of[id(fld)] = gname
            members.append(fld.name or fld.id or "")
        if members:
            field_groups.setdefault(gname, []).extend([m for m in members if m])

    has_password = has_file = has_date = False
    radio_names: list[str] = []
    checkbox_names: list[str] = []
    required_count = 0
    validation_hints: list[str] = []

    for fld in form.find_all(lambda n: n.tag in _FIELD_TAGS):
        if fld.tag == "input" and fld.type in _SKIP_INPUT_TYPES:
            continue
        ftype = _field_type(fld)
        required = _truthy_attr(fld, "required") or fld.attr("aria-required") == "true"
        if required:
            required_count += 1
        if ftype == "password":
            has_password = True
        if ftype == "file":
            has_file = True
        if ftype in _DATE_TYPES or fld.class_contains("datepicker", "calendar"):
            has_date = True
        if ftype == "radio" and fld.name:
            radio_names.append(fld.name)
        if ftype == "checkbox" and fld.name:
            checkbox_names.append(fld.name)
        label = _field_label(fld, by_for, by_wrap)
        vhint = _validation_hint(fld, ftype, required)
        if vhint:
            validation_hints.append(f"{label or fld.name or ftype}: {vhint}")
        fields.append(FormField(
            name=fld.name or fld.id or "", label=label, field_type=ftype, required=required,
            placeholder=fld.placeholder, autocomplete=fld.attr("autocomplete"),
            options=_options(fld), group=group_of.get(id(fld), ""), validation_hint=vhint,
            locator=build_locator(fld, label=label),
        ))

    # submit / reset
    submit_label = None
    reset_label = None
    for btn in form.find_all(lambda n: n.tag in ("button", "input")):
        if reset_label is None and _is_reset(btn):
            reset_label = (btn.text_content(40) or btn.value or "Reset").strip()
            continue
        if submit_label is None and _is_submit(btn):
            submit_label = (btn.text_content(40) or btn.value or "Submit").strip()

    label = form.aria_label or form.attr("name") or form.id or f"form-{index}"
    return FormModel(
        form_id=form.id or form.testid or f"form-{index}",
        label=label, fields=fields, field_groups=field_groups,
        submit_label=submit_label, reset_label=reset_label,
        has_password=has_password, has_file_upload=has_file, has_date_picker=has_date,
        checkbox_groups=sorted(set(checkbox_names)), radio_groups=sorted(set(radio_names)),
        required_count=required_count, validation_hints=validation_hints,
        locator=build_locator(form, label=label),
    )


def analyze_forms(root: DomNode) -> list[FormModel]:
    forms = root.find_all(lambda n: n.tag == "form" or n.role == "form")
    if root.tag == "form" or root.role == "form":
        forms = [root] + forms
    return [analyze_form(f, i) for i, f in enumerate(forms)]
