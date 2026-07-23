from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Wave2Result:
    capability_id: str
    success: bool
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 3),
            "details": dict(self.details),
            "error": self.error,
        }


def parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {"text": raw}
        except json.JSONDecodeError:
            return {"text": raw}
    return {}


def editor_kind_from_classes(classes: str, attrs: dict[str, str] | None = None) -> str:
    attrs = attrs or {}
    haystack = f"{classes} {' '.join(attrs.values())}".lower()
    if "monaco" in haystack:
        return "monaco"
    if "cm-editor" in haystack or "codemirror" in haystack or "cm-content" in haystack:
        return "codemirror"
    return "unknown"


def execute_code_editor(page: Any, locator: Any, payload: dict[str, Any], *, capability_id: str) -> Wave2Result:
    start = time.perf_counter()
    text = str(payload.get("text") or payload.get("content") or "")
    mode = str(payload.get("mode") or "replace")
    try:
        handle = locator.element_handle()
        if handle is None:
            return _result(capability_id, False, start, {}, "editor_not_found")
        kind = str(page.evaluate(
            """(el) => {
              const root = el.closest('.monaco-editor, .cm-editor, .CodeMirror, [data-mode-id], [contenteditable="true"], textarea') || el;
              const cls = String(root.className || '').toLowerCase();
              if (cls.includes('monaco') || root.querySelector('.monaco-mouse-cursor-text, textarea.inputarea')) return 'monaco';
              if (cls.includes('cm-editor') || cls.includes('codemirror') || root.querySelector('.cm-content, textarea')) return 'codemirror';
              return 'unknown';
            }""",
            handle,
        ))
        if kind == "unknown":
            return _result(capability_id, False, start, {"editor_kind": kind}, "unsupported_editor_surface")
        expected_kind = "monaco" if capability_id.endswith(".monaco") else "codemirror" if capability_id.endswith(".codemirror") else kind
        if kind != expected_kind:
            return _result(capability_id, False, start, {"editor_kind": kind, "expected_kind": expected_kind}, "editor_kind_mismatch")
        locator.scroll_into_view_if_needed()
        locator.focus()
        applied = bool(page.evaluate(
            """([el, payload]) => {
              const root = el.closest('.monaco-editor, .cm-editor, .CodeMirror, [data-mode-id], [contenteditable="true"], textarea') || el;
              const target = root.querySelector('textarea.inputarea, textarea, .cm-content, [contenteditable="true"]') || root;
              target.focus();
              const text = String(payload.text || '');
              if (target instanceof HTMLTextAreaElement) {
                if (payload.mode === 'append') target.value += text;
                else target.value = text;
                target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                target.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
              }
              const selection = window.getSelection();
              const range = document.createRange();
              if (payload.mode === 'append') {
                range.selectNodeContents(target);
                range.collapse(false);
              } else {
                range.selectNodeContents(target);
              }
              if (selection) {
                selection.removeAllRanges();
                selection.addRange(range);
              }
              const inserted = document.execCommand('insertText', false, text);
              if (!inserted) {
                if (payload.mode !== 'append') target.textContent = '';
                target.append(document.createTextNode(text));
              }
              target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
              return true;
            }""",
            [handle, {"text": text, "mode": mode}],
        ))
        validated = bool(page.evaluate(
            """([el, expected]) => {
              const root = el.closest('.monaco-editor, .cm-editor, .CodeMirror, [data-mode-id], [contenteditable="true"], textarea') || el;
              const target = root.querySelector('textarea.inputarea, textarea, .cm-content, [contenteditable="true"]') || root;
              const actual = target instanceof HTMLTextAreaElement ? target.value : (target.textContent || '');
              return !String(expected).trim() || actual.includes(String(expected));
            }""",
            [handle, text],
        ))
        return _result(capability_id, applied and validated, start, {
            "editor_kind": kind,
            "mode": mode,
            "content_length": len(text),
            "validated": validated,
        })
    except Exception as exc:  # noqa: BLE001
        return _result(capability_id, False, start, {}, str(exc)[:200])


def execute_drag_drop(page: Any, source: Any, target: Any, payload: dict[str, Any]) -> Wave2Result:
    start = time.perf_counter()
    try:
        source.drag_to(target, timeout=int(payload.get("timeout_ms", 30_000)))
        return _result("browser.drag_drop", True, start, {"method": "playwright.drag_to"})
    except Exception as exc:  # noqa: BLE001
        return _result("browser.drag_drop", False, start, {}, str(exc)[:200])


def execute_infinite_scroll(page: Any, payload: dict[str, Any]) -> Wave2Result:
    start = time.perf_counter()
    max_steps = int(payload.get("max_steps", 12))
    target_text = str(payload.get("target_text") or "")
    signatures: set[str] = set()
    steps = 0
    found = False
    ended = False
    try:
        for steps in range(1, max_steps + 1):
            state = page.evaluate(
                """(targetText) => {
                  const bodyText = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim();
                  const signature = [bodyText.length, window.scrollY, document.body ? document.body.scrollHeight : 0].join('|');
                  const found = targetText ? bodyText.toLowerCase().includes(String(targetText).toLowerCase()) : false;
                  const atEnd = Math.ceil(window.innerHeight + window.scrollY) >= (document.body ? document.body.scrollHeight : 0);
                  window.scrollBy(0, Math.max(300, Math.floor(window.innerHeight * 0.85)));
                  return { signature, found, atEnd };
                }""",
                target_text,
            )
            sig = str(state.get("signature"))
            if state.get("found"):
                found = True
                break
            if state.get("atEnd") or sig in signatures:
                ended = True
                break
            signatures.add(sig)
            page.wait_for_timeout(int(payload.get("settle_ms", 150)))
        success = found or (not target_text and ended)
        return _result("browser.scroll.infinite", success, start, {
            "steps": steps,
            "found": found,
            "ended": ended,
            "duplicate_signatures": max(0, steps - len(signatures)),
        })
    except Exception as exc:  # noqa: BLE001
        return _result("browser.scroll.infinite", False, start, {"steps": steps}, str(exc)[:200])


def execute_virtual_list(page: Any, locator: Any, payload: dict[str, Any]) -> Wave2Result:
    start = time.perf_counter()
    target_text = str(payload.get("target_text") or payload.get("text") or "")
    max_steps = int(payload.get("max_steps", 20))
    settle_ms = int(payload.get("settle_ms", 80))
    try:
        handle = locator.element_handle() if locator is not None else None
        state = page.evaluate(
            """async ([container, targetText, maxSteps, settleMs]) => {
              const root = container || document.scrollingElement || document.documentElement;
              const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
              const seen = new Set();
              let found = false;
              let ended = false;
              let steps = 0;
              for (steps = 1; steps <= maxSteps; steps++) {
                const text = (root.textContent || '').replace(/\\s+/g, ' ').trim();
                found = targetText ? text.toLowerCase().includes(String(targetText).toLowerCase()) : false;
                const signature = [text.length, root.scrollTop || window.scrollY, root.scrollHeight || document.body.scrollHeight].join('|');
                if (found || seen.has(signature)) break;
                seen.add(signature);
                const before = root.scrollTop || window.scrollY;
                if (root === document.scrollingElement || root === document.documentElement || root === document.body) {
                  window.scrollBy(0, Math.max(160, Math.floor(window.innerHeight * 0.8)));
                } else {
                  root.scrollTop += Math.max(120, Math.floor(root.clientHeight * 0.8));
                }
                await sleep(settleMs);
                const after = root.scrollTop || window.scrollY;
                ended = after === before || after + (root.clientHeight || window.innerHeight) >= (root.scrollHeight || document.body.scrollHeight);
                if (ended) break;
              }
              return { found, ended, steps };
            }""",
            [handle, target_text, max(1, min(max_steps, 80)), max(0, min(settle_ms, 1000))],
        )
        success = bool(state.get("found"))
        return _result("browser.lists.virtual", success, start, dict(state))
    except Exception as exc:  # noqa: BLE001
        return _result("browser.lists.virtual", False, start, {}, str(exc)[:200])


def execute_shadow_dom(page: Any, payload: dict[str, Any]) -> Wave2Result:
    start = time.perf_counter()
    path = str(payload.get("shadow_path") or "")
    action = str(payload.get("shadow_action") or payload.get("operation") or "click")
    text = str(payload.get("text") or payload.get("value") or "")
    try:
        state = page.evaluate(
            """([path, action, text]) => {
              const parts = String(path).split('>>').map((part) => part.trim()).filter(Boolean);
              let root = document;
              let target = null;
              for (const part of parts) {
                target = root.querySelector(part);
                if (!target) return { success: false, error: `missing:${part}`, depth: parts.length };
                root = target.shadowRoot || target;
              }
              if (!(target instanceof HTMLElement)) return { success: false, error: 'not_actionable', depth: parts.length };
              target.focus?.();
              if (action === 'fill') {
                if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) target.value = text;
                else target.textContent = text;
                target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                target.dispatchEvent(new Event('change', { bubbles: true }));
              } else {
                target.click();
              }
              return { success: true, depth: parts.length, action };
            }""",
            [path, action, text],
        )
        success = bool(state.get("success"))
        return _result("browser.shadow_dom.open", success, start, dict(state), None if success else str(state.get("error") or "shadow_dom_failed"))
    except Exception as exc:  # noqa: BLE001
        return _result("browser.shadow_dom.open", False, start, {}, str(exc)[:200])


def execute_keyboard(page: Any, payload: dict[str, Any]) -> Wave2Result:
    start = time.perf_counter()
    sequence = payload.get("sequence") or payload.get("keys") or []
    if isinstance(sequence, str):
        sequence = [sequence]
    try:
        for key in sequence:
            page.keyboard.press(str(key))
        return _result("browser.advanced_keyboard", True, start, {"sequence": list(map(str, sequence)), "count": len(sequence)})
    except Exception as exc:  # noqa: BLE001
        return _result("browser.advanced_keyboard", False, start, {"sequence": list(map(str, sequence))}, str(exc)[:200])


def execute_clipboard(page: Any, payload: dict[str, Any]) -> Wave2Result:
    start = time.perf_counter()
    operation = str(payload.get("operation") or "paste")
    text = str(payload.get("text") or "")
    try:
        if operation in {"paste", "write"}:
            page.evaluate("text => navigator.clipboard && navigator.clipboard.writeText ? navigator.clipboard.writeText(text) : Promise.resolve()", text)
            if operation == "paste":
                page.keyboard.press("Control+V")
        elif operation in {"copy", "cut"}:
            page.keyboard.press("Control+C" if operation == "copy" else "Control+X")
        else:
            return _result("browser.clipboard", False, start, {"operation": operation}, "unsupported_clipboard_operation")
        return _result("browser.clipboard", True, start, {"operation": operation, "text_length": len(text)})
    except Exception as exc:  # noqa: BLE001
        return _result("browser.clipboard", False, start, {"operation": operation}, str(exc)[:200])


def _result(capability_id: str, success: bool, start: float, details: dict[str, Any], error: str | None = None) -> Wave2Result:
    return Wave2Result(
        capability_id=capability_id,
        success=success,
        duration_ms=(time.perf_counter() - start) * 1000,
        details=details,
        error=error,
    )
