export interface Wave2Action {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
}

export interface Wave2Result {
  success: boolean
  message: string
  action_id: string
  wave2_capability?: string
  wave2_validated?: boolean
  wave2_details?: Record<string, string | number | boolean | null>
}

const WAVE2_ACTIONS = new Set([
  'monaco_edit',
  'codemirror_edit',
  'drag_drop',
  'virtual_list_find',
  'shadow_click',
  'shadow_fill',
  'infinite_scroll',
  'advanced_keyboard',
  'clipboard',
])

export function parseWave2Payload(value: string | null): Record<string, unknown> {
  if (!value) return {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : { text: value }
  } catch {
    return { text: value }
  }
}

export function isWave2CoreAction(actionType: string): boolean {
  return WAVE2_ACTIONS.has(actionType)
}

export async function executeWave2CoreAction(action: Wave2Action): Promise<Wave2Result | null> {
  const wave2Actions = new Set([
    'monaco_edit',
    'codemirror_edit',
    'drag_drop',
    'virtual_list_find',
    'shadow_click',
    'shadow_fill',
    'infinite_scroll',
    'advanced_keyboard',
    'clipboard',
  ])
  if (!wave2Actions.has(action.action_type)) return null
  if (action.safety_level === 'danger') {
    return { success: false, message: 'Wave 2 action refused because it is marked dangerous.', action_id: action.action_id }
  }

  const payload = (() => {
    if (!action.value) return {}
    try {
      const parsed = JSON.parse(action.value)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : { text: action.value }
    } catch {
      return { text: action.value }
    }
  })()

  function q(selector: string | null): Element | null {
    if (!selector) return null
    try { return document.querySelector(selector) } catch { return null }
  }

  function visible(candidate: Element | null): candidate is HTMLElement {
    if (!(candidate instanceof HTMLElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
  }

  function editorRoot(el: Element | null): HTMLElement | null {
    if (!el) return null
    const root = el.closest('.monaco-editor, .cm-editor, .CodeMirror, .cm-content, textarea, [contenteditable="true"]') || el
    return visible(root) ? root : null
  }

  function editorKind(el: Element | null): string {
    if (!el) return 'unknown'
    const root = editorRoot(el) || el
    const className = String((root as HTMLElement).className || '').toLowerCase()
    if (className.includes('monaco') || root.querySelector?.('.monaco-mouse-cursor-text, textarea.inputarea')) return 'monaco'
    if (className.includes('cm-editor') || className.includes('codemirror') || className.includes('cm-content')) return 'codemirror'
    return 'unknown'
  }

  function setEditorContent(kind: 'monaco' | 'codemirror'): Wave2Result {
    const target = editorRoot(q(action.target_selector))
    const capability = kind === 'monaco' ? 'browser.editors.monaco' : 'browser.editors.codemirror'
    if (!target || editorKind(target) !== kind) {
      return { success: false, message: `${kind} editor not found.`, action_id: action.action_id, wave2_capability: capability, wave2_validated: false }
    }
    const text = String(payload.text ?? payload.content ?? '')
    const mode = String(payload.mode ?? 'replace')
    const input = target.querySelector('textarea.inputarea, textarea, .cm-content, [contenteditable="true"]') as HTMLElement | null || target
    input.focus()
    if (input instanceof HTMLTextAreaElement) {
      input.value = mode === 'append' ? `${input.value}${text}` : text
      input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
    } else {
      const selection = window.getSelection()
      const range = document.createRange()
      if (mode === 'append') { range.selectNodeContents(input); range.collapse(false) } else { range.selectNodeContents(input) }
      selection?.removeAllRanges(); selection?.addRange(range)
      const inserted = document.execCommand('insertText', false, text)
      if (!inserted) {
        if (mode !== 'append') input.textContent = ''
        input.append(document.createTextNode(text))
      }
      input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }))
    }
    const actual = input instanceof HTMLTextAreaElement ? input.value : input.textContent || ''
    const validated = !text.trim() || actual.includes(text)
    return {
      success: validated,
      message: validated ? `${kind} content updated.` : `${kind} validation failed.`,
      action_id: action.action_id,
      wave2_capability: capability,
      wave2_validated: validated,
      wave2_details: { editor_kind: kind, content_length: text.length, mode },
    }
  }

  function dispatchKeyboard(): Wave2Result {
    const raw = payload.sequence ?? payload.keys ?? []
    const keys = Array.isArray(raw) ? raw.map(String) : [String(raw)]
    const target = q(action.target_selector) as HTMLElement | null || document.activeElement as HTMLElement | null
    target?.focus?.()
    for (const combo of keys) {
      const parts = combo.toLowerCase().split('+').map((part) => part.trim())
      const key = parts[parts.length - 1] || combo
      const init = {
        key,
        code: key.length === 1 ? `Key${key.toUpperCase()}` : key,
        bubbles: true,
        cancelable: true,
        ctrlKey: parts.includes('ctrl') || parts.includes('control'),
        metaKey: parts.includes('cmd') || parts.includes('meta'),
        altKey: parts.includes('alt'),
        shiftKey: parts.includes('shift'),
      }
      ;(target || document.body).dispatchEvent(new KeyboardEvent('keydown', init))
      ;(target || document.body).dispatchEvent(new KeyboardEvent('keyup', init))
    }
    return { success: true, message: `Dispatched ${keys.length} keyboard event(s).`, action_id: action.action_id, wave2_capability: 'browser.advanced_keyboard', wave2_validated: true, wave2_details: { count: keys.length } }
  }

  async function clipboard(): Promise<Wave2Result> {
    const operation = String(payload.operation ?? 'paste')
    const text = String(payload.text ?? '')
    const target = q(action.target_selector) as HTMLElement | null || document.activeElement as HTMLElement | null
    target?.focus?.()
    try {
      if ((operation === 'paste' || operation === 'write') && navigator.clipboard?.writeText) await navigator.clipboard.writeText(text)
      if (operation === 'paste') document.execCommand('insertText', false, text)
      if (operation === 'copy') document.execCommand('copy')
      if (operation === 'cut') document.execCommand('cut')
      return { success: true, message: `Clipboard ${operation} completed.`, action_id: action.action_id, wave2_capability: 'browser.clipboard', wave2_validated: true, wave2_details: { operation, text_length: text.length } }
    } catch (err) {
      return { success: false, message: `Clipboard ${operation} failed: ${String(err)}`, action_id: action.action_id, wave2_capability: 'browser.clipboard', wave2_validated: false }
    }
  }

  function dragDrop(): Wave2Result {
    const source = q(action.target_selector)
    const target = q(String(payload.drop_selector ?? payload.target_selector ?? ''))
    if (!visible(source) || !visible(target)) return { success: false, message: 'Drag source or drop target not found.', action_id: action.action_id, wave2_capability: 'browser.drag_drop', wave2_validated: false }
    const data = new DataTransfer()
    for (const type of ['dragstart', 'dragenter', 'dragover', 'drop', 'dragend']) {
      const el = type === 'dragstart' || type === 'dragend' ? source : target
      el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: data }))
    }
    return { success: true, message: 'Drag and drop completed.', action_id: action.action_id, wave2_capability: 'browser.drag_drop', wave2_validated: true }
  }

  function shadowAction(): Wave2Result {
    const path = String(payload.shadow_path ?? '')
    const parts = path.split('>>').map((part) => part.trim()).filter(Boolean)
    let root: Document | ShadowRoot | Element = document
    let target: Element | null = null
    for (const part of parts) {
      target = (root as ParentNode).querySelector(part)
      if (!target) return { success: false, message: `Shadow target not found: ${part}`, action_id: action.action_id, wave2_capability: 'browser.shadow_dom.open', wave2_validated: false }
      root = target.shadowRoot || target
    }
    if (!(target instanceof HTMLElement)) return { success: false, message: 'Final shadow target is not actionable.', action_id: action.action_id, wave2_capability: 'browser.shadow_dom.open', wave2_validated: false }
    if (action.action_type === 'shadow_fill') {
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) target.value = String(payload.text ?? '')
      else target.textContent = String(payload.text ?? '')
      target.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }))
    } else {
      target.click()
    }
    return { success: true, message: 'Open shadow DOM action completed.', action_id: action.action_id, wave2_capability: 'browser.shadow_dom.open', wave2_validated: true, wave2_details: { depth: parts.length } }
  }

  async function infiniteScroll(): Promise<Wave2Result> {
    const targetText = String(payload.target_text ?? '')
    const maxSteps = Math.max(1, Math.min(Number(payload.max_steps ?? 12), 50))
    const signatures = new Set<string>()
    let found = false
    let ended = false
    let steps = 0
    for (steps = 1; steps <= maxSteps; steps++) {
      const bodyText = (document.body?.innerText || '').replace(/\s+/g, ' ').trim()
      found = targetText ? bodyText.toLowerCase().includes(targetText.toLowerCase()) : false
      const signature = `${bodyText.length}|${window.scrollY}|${document.body?.scrollHeight || 0}`
      ended = Math.ceil(window.innerHeight + window.scrollY) >= (document.body?.scrollHeight || 0)
      if (found || ended || signatures.has(signature)) break
      signatures.add(signature)
      window.scrollBy(0, Math.max(300, Math.floor(window.innerHeight * 0.85)))
      await new Promise((resolve) => setTimeout(resolve, Number(payload.settle_ms ?? 150)))
    }
    return { success: found || (!targetText && ended), message: found ? 'Infinite scroll target found.' : ended ? 'Infinite scroll reached end.' : 'Infinite scroll budget exhausted.', action_id: action.action_id, wave2_capability: 'browser.scroll.infinite', wave2_validated: found || ended, wave2_details: { steps, found, ended } }
  }

  async function virtualListFind(): Promise<Wave2Result> {
    const targetText = String(payload.target_text ?? payload.text ?? '')
    const container = q(action.target_selector) as HTMLElement | null || document.scrollingElement as HTMLElement | null
    if (!container || !targetText) return { success: false, message: 'Virtual list container or target text missing.', action_id: action.action_id, wave2_capability: 'browser.lists.virtual', wave2_validated: false }
    const maxSteps = Math.max(1, Math.min(Number(payload.max_steps ?? 20), 80))
    let found = false
    let steps = 0
    for (steps = 1; steps <= maxSteps; steps++) {
      found = (container.textContent || '').toLowerCase().includes(targetText.toLowerCase())
      if (found) break
      container.scrollTop += Math.max(120, Math.floor(container.clientHeight * 0.8))
      await new Promise((resolve) => setTimeout(resolve, Number(payload.settle_ms ?? 80)))
    }
    return { success: found, message: found ? 'Virtual list target found.' : 'Virtual list target not found within budget.', action_id: action.action_id, wave2_capability: 'browser.lists.virtual', wave2_validated: found, wave2_details: { steps, found } }
  }

  if (action.action_type === 'monaco_edit') return setEditorContent('monaco')
  if (action.action_type === 'codemirror_edit') return setEditorContent('codemirror')
  if (action.action_type === 'drag_drop') return dragDrop()
  if (action.action_type === 'shadow_click' || action.action_type === 'shadow_fill') return shadowAction()
  if (action.action_type === 'advanced_keyboard') return dispatchKeyboard()
  if (action.action_type === 'clipboard') return await clipboard()
  if (action.action_type === 'infinite_scroll') return await infiniteScroll()
  if (action.action_type === 'virtual_list_find') return await virtualListFind()
  return null
}
