export type RichTextEditorKind =
  | 'contenteditable'
  | 'quill'
  | 'prosemirror'
  | 'tinymce'
  | 'ckeditor'
  | 'draftjs'
  | 'slate'
  | 'lexical'
  | 'unknown'

export interface RichTextAction {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
}

export interface RichTextPayload {
  text: string
  html?: string | null
  mode: 'replace' | 'append' | 'insert'
  preserve_formatting: boolean
  shortcuts: string[]
}

export interface RichTextExecutionResult {
  success: boolean
  message: string
  action_id: string
  rich_text_editor?: RichTextEditorKind
  rich_text_mode?: RichTextPayload['mode']
  rich_text_validated?: boolean
  inserted_length?: number
  shortcuts_applied?: string[]
}

const RICH_TEXT_ACTIONS = new Set(['rich_text', 'insert_rich_text', 'edit_rich_text'])

export function parseRichTextPayload(value: string | null): RichTextPayload {
  const fallback = {
    text: value || '',
    html: null,
    mode: 'replace' as const,
    preserve_formatting: true,
    shortcuts: [],
  }
  if (!value) return fallback
  try {
    const parsed = JSON.parse(value) as Partial<RichTextPayload>
    return {
      text: String(parsed.text ?? parsed.html ?? ''),
      html: typeof parsed.html === 'string' ? parsed.html : null,
      mode: parsed.mode === 'append' || parsed.mode === 'insert' || parsed.mode === 'replace'
        ? parsed.mode
        : 'replace',
      preserve_formatting: parsed.preserve_formatting !== false,
      shortcuts: Array.isArray(parsed.shortcuts) ? parsed.shortcuts.map(String).slice(0, 8) : [],
    }
  } catch {
    return fallback
  }
}

export function detectRichTextKind(element: Element | null): RichTextEditorKind {
  if (!element) return 'unknown'
  const root = element.closest([
    '.ql-editor',
    '.ProseMirror',
    '.tox-edit-area, .mce-content-body',
    '.ck-editor, .ck-content',
    '[data-contents="true"]',
    '[data-slate-editor="true"]',
    '[data-lexical-editor="true"]',
    '[contenteditable="true"]',
    '[role="textbox"]',
  ].join(', '))
  const candidate = root || element
  const className = String((candidate as HTMLElement).className || '').toLowerCase()
  if (candidate.matches?.('.ql-editor') || className.includes('ql-editor')) return 'quill'
  if (candidate.matches?.('.ProseMirror') || className.includes('prosemirror')) return 'prosemirror'
  if (candidate.matches?.('.mce-content-body, .tox-edit-area') || className.includes('mce-content-body')) return 'tinymce'
  if (candidate.matches?.('.ck-content, .ck-editor') || className.includes('ck-content')) return 'ckeditor'
  if (candidate.matches?.('[data-contents="true"]')) return 'draftjs'
  if (candidate.matches?.('[data-slate-editor="true"]')) return 'slate'
  if (candidate.matches?.('[data-lexical-editor="true"]')) return 'lexical'
  if ((candidate as HTMLElement).isContentEditable || candidate.getAttribute('contenteditable') === 'true') return 'contenteditable'
  if (candidate.getAttribute('role') === 'textbox') return 'contenteditable'
  return 'unknown'
}

export function shouldHandleRichTextAction(action: RichTextAction, target: Element | null): boolean {
  if (action.safety_level === 'danger') return false
  return RICH_TEXT_ACTIONS.has(action.action_type) && detectRichTextKind(target) !== 'unknown'
}

export async function executeRichTextAction(action: RichTextAction): Promise<RichTextExecutionResult | null> {
  const richTextActions = new Set(['rich_text', 'insert_rich_text', 'edit_rich_text'])

  function parsePayload(value: string | null): RichTextPayload {
    const fallback = {
      text: value || '',
      html: null,
      mode: 'replace' as const,
      preserve_formatting: true,
      shortcuts: [],
    }
    if (!value) return fallback
    try {
      const parsed = JSON.parse(value) as Partial<RichTextPayload>
      return {
        text: String(parsed.text ?? parsed.html ?? ''),
        html: typeof parsed.html === 'string' ? parsed.html : null,
        mode: parsed.mode === 'append' || parsed.mode === 'insert' || parsed.mode === 'replace'
          ? parsed.mode
          : 'replace',
        preserve_formatting: parsed.preserve_formatting !== false,
        shortcuts: Array.isArray(parsed.shortcuts) ? parsed.shortcuts.map(String).slice(0, 8) : [],
      }
    } catch {
      return fallback
    }
  }

  function detectKind(element: Element | null): RichTextEditorKind {
    if (!element) return 'unknown'
    const root = element.closest([
      '.ql-editor',
      '.ProseMirror',
      '.tox-edit-area, .mce-content-body',
      '.ck-editor, .ck-content',
      '[data-contents="true"]',
      '[data-slate-editor="true"]',
      '[data-lexical-editor="true"]',
      '[contenteditable="true"]',
      '[role="textbox"]',
    ].join(', '))
    const candidate = root || element
    const className = String((candidate as HTMLElement).className || '').toLowerCase()
    if (candidate.matches?.('.ql-editor') || className.includes('ql-editor')) return 'quill'
    if (candidate.matches?.('.ProseMirror') || className.includes('prosemirror')) return 'prosemirror'
    if (candidate.matches?.('.mce-content-body, .tox-edit-area') || className.includes('mce-content-body')) return 'tinymce'
    if (candidate.matches?.('.ck-content, .ck-editor') || className.includes('ck-content')) return 'ckeditor'
    if (candidate.matches?.('[data-contents="true"]')) return 'draftjs'
    if (candidate.matches?.('[data-slate-editor="true"]')) return 'slate'
    if (candidate.matches?.('[data-lexical-editor="true"]')) return 'lexical'
    if ((candidate as HTMLElement).isContentEditable || candidate.getAttribute('contenteditable') === 'true') return 'contenteditable'
    if (candidate.getAttribute('role') === 'textbox') return 'contenteditable'
    return 'unknown'
  }

  function shouldHandle(target: Element | null): boolean {
    if (action.safety_level === 'danger') return false
    return richTextActions.has(action.action_type) && detectKind(target) !== 'unknown'
  }

  function query(selector: string | null): Element | null {
    if (!selector) return null
    try {
      return document.querySelector(selector)
    } catch {
      return null
    }
  }

  function visible(candidate: Element | null): candidate is HTMLElement {
    if (!(candidate instanceof HTMLElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
  }

  function editorRoot(candidate: Element | null): HTMLElement | null {
    if (!candidate) return null
    const root = candidate.closest([
      '.ql-editor',
      '.ProseMirror',
      '.mce-content-body',
      '.ck-content',
      '[data-contents="true"]',
      '[data-slate-editor="true"]',
      '[data-lexical-editor="true"]',
      '[contenteditable="true"]',
      '[role="textbox"]',
    ].join(', '))
    if (visible(root)) return root
    return visible(candidate) ? candidate : null
  }

  function selectContents(target: HTMLElement, mode: RichTextPayload['mode']) {
    target.focus()
    const selection = window.getSelection()
    if (!selection) return false
    const range = document.createRange()
    if (mode === 'append') {
      range.selectNodeContents(target)
      range.collapse(false)
    } else if (mode === 'insert') {
      return true
    } else {
      range.selectNodeContents(target)
    }
    selection.removeAllRanges()
    selection.addRange(range)
    return true
  }

  function dispatchEditorEvents(target: HTMLElement) {
    target.dispatchEvent(new InputEvent('beforeinput', { bubbles: true, cancelable: true, inputType: 'insertText' }))
    target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }))
    target.dispatchEvent(new Event('change', { bubbles: true }))
  }

  function applyShortcut(target: HTMLElement, shortcut: string) {
    const parts = shortcut.toLowerCase().split('+').map((part) => part.trim())
    const key = parts[parts.length - 1] || ''
    const eventInit = {
      key,
      code: key.length === 1 ? `Key${key.toUpperCase()}` : key,
      bubbles: true,
      cancelable: true,
      ctrlKey: parts.includes('ctrl') || parts.includes('control'),
      metaKey: parts.includes('cmd') || parts.includes('meta'),
      altKey: parts.includes('alt'),
      shiftKey: parts.includes('shift'),
    }
    target.dispatchEvent(new KeyboardEvent('keydown', eventInit))
    target.dispatchEvent(new KeyboardEvent('keyup', eventInit))
  }

  function containsExpectedText(target: HTMLElement, expected: string): boolean {
    const actual = (target.textContent || '').replace(/\s+/g, ' ').trim()
    const normalized = expected.replace(/\s+/g, ' ').trim()
    return normalized.length === 0 || actual.includes(normalized)
  }

  const direct = query(action.target_selector)
  const target = editorRoot(direct) ||
    Array.from(document.querySelectorAll('[contenteditable="true"], [role="textbox"], .ql-editor, .ProseMirror, .ck-content, .mce-content-body, [data-slate-editor="true"], [data-lexical-editor="true"]'))
      .map(editorRoot)
      .find((candidate): candidate is HTMLElement => Boolean(candidate)) ||
    null

  if (!shouldHandle(target)) return null
  if (!target) return { success: false, message: 'Rich text editor not found.', action_id: action.action_id }

  const payload = parsePayload(action.value)
  const editorKind = detectKind(target)
  const started = performance.now()
  const selected = selectContents(target, payload.mode)
  if (!selected) {
    return {
      success: false,
      message: 'Rich text selection could not be prepared.',
      action_id: action.action_id,
      rich_text_editor: editorKind,
      rich_text_mode: payload.mode,
      rich_text_validated: false,
    }
  }

  for (const shortcut of payload.shortcuts) applyShortcut(target, shortcut)

  const inserted = payload.html && payload.preserve_formatting
    ? document.execCommand('insertHTML', false, payload.html)
    : document.execCommand('insertText', false, payload.text)

  if (!inserted) {
    if (payload.mode === 'replace') target.textContent = ''
    target.append(document.createTextNode(payload.text))
  }

  dispatchEditorEvents(target)
  const validated = containsExpectedText(target, payload.text)
  const duration = Math.round(performance.now() - started)
  return {
    success: validated,
    message: validated
      ? `Rich text inserted with ${editorKind} editor (${duration}ms).`
      : `Rich text insertion validation failed for ${editorKind} editor.`,
    action_id: action.action_id,
    rich_text_editor: editorKind,
    rich_text_mode: payload.mode,
    rich_text_validated: validated,
    inserted_length: payload.text.length,
    shortcuts_applied: payload.shortcuts,
  }
}
