from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal


RichTextMode = Literal["replace", "append", "insert"]


@dataclass(frozen=True)
class RichTextPayload:
    text: str
    html: str | None = None
    mode: RichTextMode = "replace"
    preserve_formatting: bool = True
    shortcuts: tuple[str, ...] = ()


@dataclass(frozen=True)
class RichTextResult:
    success: bool
    editor_kind: str
    mode: RichTextMode
    inserted_length: int
    duration_ms: float
    validated: bool
    shortcuts_applied: tuple[str, ...] = field(default_factory=tuple)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "editor_kind": self.editor_kind,
            "mode": self.mode,
            "inserted_length": self.inserted_length,
            "duration_ms": round(self.duration_ms, 3),
            "validated": self.validated,
            "shortcuts_applied": list(self.shortcuts_applied),
            "error": self.error,
        }


def parse_payload(raw: Any) -> RichTextPayload:
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"text": raw}
    else:
        data = {"text": ""}

    mode = data.get("mode", "replace")
    if mode not in {"replace", "append", "insert"}:
        mode = "replace"
    shortcuts = data.get("shortcuts", ())
    if not isinstance(shortcuts, (list, tuple)):
        shortcuts = ()
    return RichTextPayload(
        text=str(data.get("text") or data.get("html") or ""),
        html=str(data["html"]) if isinstance(data.get("html"), str) else None,
        mode=mode,  # type: ignore[arg-type]
        preserve_formatting=data.get("preserve_formatting", True) is not False,
        shortcuts=tuple(str(shortcut) for shortcut in shortcuts[:8]),
    )


def execute(page: Any, locator: Any, payload: RichTextPayload) -> RichTextResult:
    start = time.perf_counter()
    try:
        handle = locator.element_handle()
        if handle is None:
            return _result(False, "unknown", payload, start, False, "editor_not_found")
        editor_kind = detect_editor_kind(page, handle)
        if editor_kind == "unknown":
            return _result(False, editor_kind, payload, start, False, "unsupported_editor_surface")
        locator.scroll_into_view_if_needed()
        locator.focus()
        applied = apply_editor_script(page, handle, payload)
        validated = validate_editor_text(page, handle, payload.text)
        return _result(applied and validated, editor_kind, payload, start, validated, None)
    except Exception as exc:  # noqa: BLE001
        return _result(False, "unknown", payload, start, False, str(exc)[:200])


def detect_editor_kind(page: Any, handle: Any) -> str:
    try:
        return str(page.evaluate(
            """(el) => {
              const root = el.closest('.ql-editor, .ProseMirror, .mce-content-body, .ck-content, [data-contents="true"], [data-slate-editor="true"], [data-lexical-editor="true"], [contenteditable="true"], [role="textbox"]') || el;
              const cls = String(root.className || '').toLowerCase();
              if (root.matches('.ql-editor') || cls.includes('ql-editor')) return 'quill';
              if (root.matches('.ProseMirror') || cls.includes('prosemirror')) return 'prosemirror';
              if (root.matches('.mce-content-body')) return 'tinymce';
              if (root.matches('.ck-content')) return 'ckeditor';
              if (root.matches('[data-contents="true"]')) return 'draftjs';
              if (root.matches('[data-slate-editor="true"]')) return 'slate';
              if (root.matches('[data-lexical-editor="true"]')) return 'lexical';
              if (root.isContentEditable || root.getAttribute('contenteditable') === 'true') return 'contenteditable';
              if (root.getAttribute('role') === 'textbox') return 'contenteditable';
              return 'unknown';
            }""",
            handle,
        ))
    except Exception:
        return "unknown"


def apply_editor_script(page: Any, handle: Any, payload: RichTextPayload) -> bool:
    return bool(page.evaluate(
        """([el, payload]) => {
          const root = el.closest('.ql-editor, .ProseMirror, .mce-content-body, .ck-content, [data-contents="true"], [data-slate-editor="true"], [data-lexical-editor="true"], [contenteditable="true"], [role="textbox"]') || el;
          root.focus();
          const selection = window.getSelection();
          if (!selection) return false;
          const range = document.createRange();
          if (payload.mode === 'append') {
            range.selectNodeContents(root);
            range.collapse(false);
          } else if (payload.mode !== 'insert') {
            range.selectNodeContents(root);
          }
          if (payload.mode !== 'insert') {
            selection.removeAllRanges();
            selection.addRange(range);
          }
          for (const shortcut of payload.shortcuts || []) {
            const parts = String(shortcut).toLowerCase().split('+').map((part) => part.trim());
            const key = parts[parts.length - 1] || '';
            const init = {
              key,
              code: key.length === 1 ? `Key${key.toUpperCase()}` : key,
              bubbles: true,
              cancelable: true,
              ctrlKey: parts.includes('ctrl') || parts.includes('control'),
              metaKey: parts.includes('cmd') || parts.includes('meta'),
              altKey: parts.includes('alt'),
              shiftKey: parts.includes('shift')
            };
            root.dispatchEvent(new KeyboardEvent('keydown', init));
            root.dispatchEvent(new KeyboardEvent('keyup', init));
          }
          const inserted = payload.html && payload.preserve_formatting
            ? document.execCommand('insertHTML', false, payload.html)
            : document.execCommand('insertText', false, payload.text);
          if (!inserted) {
            if (payload.mode === 'replace') root.textContent = '';
            root.append(document.createTextNode(payload.text));
          }
          root.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
          root.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }""",
        [handle, {
            "text": payload.text,
            "html": payload.html,
            "mode": payload.mode,
            "preserve_formatting": payload.preserve_formatting,
            "shortcuts": list(payload.shortcuts),
        }],
    ))


def validate_editor_text(page: Any, handle: Any, expected: str) -> bool:
    try:
        actual = str(page.evaluate(
            """(el) => {
              const root = el.closest('.ql-editor, .ProseMirror, .mce-content-body, .ck-content, [data-contents="true"], [data-slate-editor="true"], [data-lexical-editor="true"], [contenteditable="true"], [role="textbox"]') || el;
              return (root.textContent || '').replace(/\\s+/g, ' ').trim();
            }""",
            handle,
        ))
        return not expected.strip() or expected.strip() in actual
    except Exception:
        return False


def _result(success: bool, editor_kind: str, payload: RichTextPayload, start: float, validated: bool, error: str | None) -> RichTextResult:
    return RichTextResult(
        success=success,
        editor_kind=editor_kind,
        mode=payload.mode,
        inserted_length=len(payload.text),
        duration_ms=(time.perf_counter() - start) * 1000,
        validated=validated,
        shortcuts_applied=payload.shortcuts,
        error=error,
    )
