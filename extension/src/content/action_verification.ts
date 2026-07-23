export type VerificationReason = 'verified' | 'no_effect' | 'execution_failed' | 'not_applicable'

export interface VerifiableAction {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
}

export interface BasicExecutionResult {
  success: boolean
  message: string
  action_id: string
  wave2_capability?: string
  wave2_validated?: boolean
  wave3_capability?: string
  wave3_validated?: boolean
}

export interface ActionVerificationTargetState {
  exists: boolean
  selector: string | null
  tagName?: string
  inputType?: string | null
  value?: string | null
  filled?: boolean
  checked?: boolean | null
  selectedValue?: string | null
  selectedText?: string | null
  ariaExpanded?: string | null
  visible?: boolean
}

export interface ActionVerificationState {
  url: string
  title: string
  domSignature: string
  visibleTextLength: number
  interactiveCount: number
  activeElementSignature: string | null
  modalCount: number
  dialogCount: number
  expandedStates: string[]
  checkboxStates: string[]
  scrollX: number
  scrollY: number
  target?: ActionVerificationTargetState
}

export interface ActionVerification {
  verified: boolean
  reason: VerificationReason
  before_state: ActionVerificationState
  after_state: ActionVerificationState
  signals: Record<string, boolean | number | string | null>
}

export interface VerifiedExecutionResult extends BasicExecutionResult {
  verification?: ActionVerification
  execution_duration_ms?: number
  recovery_attempted?: boolean
  recovery_selector?: string | null
  recovery_source?: string | null
  recovery_verified?: boolean
  recovery_reason?: string | null
  upload_attempted?: boolean
  upload_completed?: boolean
  download_detected?: boolean
  download_completed?: boolean
  filename?: string | null
  mime_type?: string | null
  size_bytes?: number | null
  download_path_ref?: string | null
  opened_tab_id?: number | null
  previous_tab_id?: number | null
  active_tab_id?: number | null
  closed_tab_id?: number | null
  tab_switch_verified?: boolean
  wave2_capability?: string
  wave2_validated?: boolean
  wave2_details?: Record<string, string | number | boolean | null>
  wave3_capability?: string
  wave3_validated?: boolean
  wave3_details?: Record<string, string | number | boolean | null>
}

export function captureVerificationState(action: VerifiableAction): ActionVerificationState {
  function safeQuery(selector: string | null): Element | null {
    if (!selector) return null
    try {
      return document.querySelector(selector)
    } catch {
      return null
    }
  }

  function normalize(text: string | null | undefined): string {
    return (text || '').replace(/\s+/g, ' ').trim()
  }

  function isVisible(candidate: Element | null): boolean {
    if (!(candidate instanceof HTMLElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
  }

  function elementSignature(candidate: Element | null): string | null {
    if (!candidate) return null
    const tag = candidate.tagName.toLowerCase()
    const id = candidate.getAttribute('id')
    const name = candidate.getAttribute('name')
    const role = candidate.getAttribute('role')
    const aria = candidate.getAttribute('aria-label')
    const title = candidate.getAttribute('title')
    const text = normalize(candidate.textContent).slice(0, 80)
    return [tag, id, name, role, aria, title, text].filter(Boolean).join('|') || tag
  }

  function countVisible(selector: string): number {
    return Array.from(document.querySelectorAll(selector)).filter(isVisible).length
  }

  function compactStates(selector: string, attr: string): string[] {
    return Array.from(document.querySelectorAll(selector))
      .slice(0, 60)
      .map((candidate, index) => {
        const signature = elementSignature(candidate) || `${candidate.tagName.toLowerCase()}#${index}`
        return `${signature}=${candidate.getAttribute(attr) ?? ''}`
      })
  }

  function checkboxStates(): string[] {
    return Array.from(document.querySelectorAll('input[type="checkbox"], input[type="radio"]'))
      .slice(0, 80)
      .map((candidate, index) => {
        const input = candidate as HTMLInputElement
        const signature = elementSignature(input) || `input#${index}`
        return `${signature}=${input.checked ? 'checked' : 'unchecked'}`
      })
  }

  function targetState(target: Element | null): ActionVerificationTargetState | undefined {
    if (!action.target_selector) return undefined
    if (!target) return { exists: false, selector: action.target_selector }

    const base: ActionVerificationTargetState = {
      exists: true,
      selector: action.target_selector,
      tagName: target.tagName.toLowerCase(),
      ariaExpanded: target.getAttribute('aria-expanded'),
      visible: isVisible(target),
    }

    if (target instanceof HTMLInputElement) {
      const inputType = (target.getAttribute('type') || 'text').toLowerCase()
      base.inputType = inputType
      base.checked = inputType === 'checkbox' || inputType === 'radio' ? target.checked : null
      base.filled = target.value.length > 0
      if (inputType !== 'password') base.value = target.value
      return base
    }

    if (target instanceof HTMLTextAreaElement) {
      base.inputType = 'textarea'
      base.value = target.value
      base.filled = target.value.length > 0
      return base
    }

    if (target instanceof HTMLSelectElement) {
      base.selectedValue = target.value
      base.selectedText = target.selectedOptions[0]?.textContent ? normalize(target.selectedOptions[0].textContent) : null
      return base
    }

    if (target instanceof HTMLElement && target.isContentEditable) {
      base.inputType = 'contenteditable'
      base.value = normalize(target.textContent)
      base.filled = normalize(target.textContent).length > 0
    }

    return base
  }

  const target = safeQuery(action.target_selector)
  const visibleTextLength = normalize(document.body?.innerText).length
  const interactiveCount = document.querySelectorAll(
    'a[href], button, input, textarea, select, [role="button"], [role="link"], [contenteditable="true"]',
  ).length
  const modalCount = countVisible('[aria-modal="true"], .modal, [role="dialog"]')
  const dialogCount = countVisible('dialog, [role="dialog"]')
  const expandedStates = compactStates('[aria-expanded]', 'aria-expanded')
  const checks = checkboxStates()
  const targetDetails = targetState(target)

  const domSignature = [
    location.href,
    document.title,
    visibleTextLength,
    interactiveCount,
    modalCount,
    dialogCount,
    expandedStates.join(';'),
    checks.join(';'),
    targetDetails ? JSON.stringify(targetDetails) : '',
  ].join('|')

  return {
    url: location.href,
    title: document.title,
    domSignature,
    visibleTextLength,
    interactiveCount,
    activeElementSignature: elementSignature(document.activeElement),
    modalCount,
    dialogCount,
    expandedStates,
    checkboxStates: checks,
    scrollX: window.scrollX,
    scrollY: window.scrollY,
    target: targetDetails,
  }
}

export function createFallbackVerificationState(
  url: string | null | undefined,
  title: string | null | undefined,
  action?: VerifiableAction,
): ActionVerificationState {
  const safeUrl = url || ''
  const safeTitle = title || ''
  return {
    url: safeUrl,
    title: safeTitle,
    domSignature: `${safeUrl}|${safeTitle}`,
    visibleTextLength: 0,
    interactiveCount: 0,
    activeElementSignature: null,
    modalCount: 0,
    dialogCount: 0,
    expandedStates: [],
    checkboxStates: [],
    scrollX: 0,
    scrollY: 0,
    target: action?.target_selector ? { exists: false, selector: action.target_selector } : undefined,
  }
}

export function verifyActionEffect(
  action: VerifiableAction,
  executionResult: BasicExecutionResult,
  before: ActionVerificationState,
  after: ActionVerificationState,
  executionDurationMs = 0,
): ActionVerification {
  const signals: Record<string, boolean | number | string | null> = {
    action_type: action.action_type,
    execution_success: executionResult.success,
    execution_duration_ms: Math.max(0, Math.round(executionDurationMs)),
    url_changed: before.url !== after.url,
    dom_changed: before.domSignature !== after.domSignature,
    focus_changed: before.activeElementSignature !== after.activeElementSignature,
    visible_text_length_changed: before.visibleTextLength !== after.visibleTextLength,
    interactive_count_changed: before.interactiveCount !== after.interactiveCount,
    modal_count_changed: before.modalCount !== after.modalCount,
    dialog_count_changed: before.dialogCount !== after.dialogCount,
    expanded_state_changed: before.expandedStates.join('|') !== after.expandedStates.join('|'),
    checkbox_state_changed: before.checkboxStates.join('|') !== after.checkboxStates.join('|'),
    scroll_position_changed: before.scrollX !== after.scrollX || before.scrollY !== after.scrollY,
    target_exists_after: after.target?.exists ?? null,
    target_value_changed: valueForComparison(before.target) !== valueForComparison(after.target),
    target_filled_after: after.target?.filled ?? null,
    target_checked_changed: before.target?.checked !== after.target?.checked,
    target_selected_changed: before.target?.selectedValue !== after.target?.selectedValue ||
      before.target?.selectedText !== after.target?.selectedText,
    target_expanded_changed: before.target?.ariaExpanded !== after.target?.ariaExpanded,
    wave2_capability: executionResult.wave2_capability ?? null,
    wave2_validated: executionResult.wave2_validated ?? null,
    wave3_capability: executionResult.wave3_capability ?? null,
    wave3_validated: executionResult.wave3_validated ?? null,
  }

  if (!executionResult.success) {
    return { verified: false, reason: 'execution_failed', before_state: before, after_state: after, signals }
  }

  let verified = false
  let reason: VerificationReason = 'no_effect'

  switch (action.action_type) {
    case 'click':
      verified = Boolean(
        signals.url_changed ||
        signals.dom_changed ||
        signals.focus_changed ||
        signals.modal_count_changed ||
        signals.dialog_count_changed ||
        signals.expanded_state_changed ||
        signals.checkbox_state_changed ||
        signals.target_checked_changed ||
        signals.target_expanded_changed ||
        signals.visible_text_length_changed ||
        signals.interactive_count_changed,
      )
      break

    case 'fill':
    case 'rich_text':
    case 'insert_rich_text':
    case 'edit_rich_text':
    case 'monaco_edit':
    case 'codemirror_edit':
    case 'shadow_fill':
    case 'clipboard':
      verified = verifyFill(action, before, after)
      if (!verified && executionResult.wave2_validated === true) verified = true
      signals.fill_verified_without_password_value = verified
      break

    case 'drag_drop':
    case 'virtual_list_find':
    case 'shadow_click':
    case 'infinite_scroll':
    case 'advanced_keyboard':
      verified = executionResult.wave2_validated === true || executionResult.success === true
      signals.wave2_result_verified = verified
      break

    case 'canvas_action':
    case 'svg_action':
    case 'pdf_viewer':
    case 'chart_action':
    case 'map_action':
    case 'media_control':
    case 'file_preview':
    case 'visual_region':
      verified = executionResult.wave3_validated === true || executionResult.success === true
      signals.wave3_result_verified = verified
      break

    case 'select_option':
      verified = Boolean(signals.target_selected_changed || targetMatchesActionValue(after, action.value))
      break

    case 'navigate':
      verified = before.url !== after.url
      break

    case 'scroll':
      verified = Boolean(signals.scroll_position_changed)
      break

    case 'wait':
      verified = true
      signals.wait_completed = true
      break

    default:
      reason = 'not_applicable'
      verified = false
  }

  if (verified) reason = 'verified'
  return { verified, reason, before_state: before, after_state: after, signals }
}

function valueForComparison(target?: ActionVerificationTargetState): string | boolean | null | undefined {
  if (!target) return undefined
  if (target.inputType === 'password') return target.filled
  if (typeof target.value === 'string') return target.value
  if (typeof target.selectedValue === 'string') return target.selectedValue
  if (typeof target.checked === 'boolean') return target.checked
  return target.filled
}

function verifyFill(
  action: VerifiableAction,
  before: ActionVerificationState,
  after: ActionVerificationState,
): boolean {
  const afterTarget = after.target
  if (!afterTarget?.exists) return false
  if (afterTarget.inputType === 'password') return afterTarget.filled === true
  const changed = valueForComparison(before.target) !== valueForComparison(afterTarget)
  if (changed) return true
  return typeof action.value === 'string' && afterTarget.value === action.value
}

function targetMatchesActionValue(after: ActionVerificationState, value: string | null): boolean {
  if (!value || !after.target) return false
  return after.target.selectedValue === value || after.target.selectedText === value
}
