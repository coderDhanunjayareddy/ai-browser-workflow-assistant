import type { ActionVerification, BasicExecutionResult, VerifiableAction } from './action_verification'

export type RecoverySource =
  | 'same_selector'
  | 'accessibility_label'
  | 'aria_label'
  | 'associated_label'
  | 'button_text'
  | 'placeholder'
  | 'nearby_text'
  | 'stable_id'
  | 'stable_data_testid'

export interface SelectorRecoveryCandidate {
  selector: string
  source: RecoverySource
  text: string
  visible: boolean
  action_types: string[]
}

export interface SelectorRecoveryChoice {
  selector: string
  source: RecoverySource
  reason: string
}

export interface SelectorRecoveryMetadata {
  recovery_attempted?: boolean
  recovery_selector?: string | null
  recovery_source?: string | null
  recovery_verified?: boolean
  recovery_reason?: string | null
}

const SUPPORTED_RECOVERY_ACTIONS = new Set(['click', 'fill', 'select_option'])
const DESTRUCTIVE_TERMS = [
  'delete',
  'remove',
  'purchase',
  'payment',
  'pay now',
  'place order',
  'checkout',
  'submit',
  'logout',
  'log out',
  'sign out',
  'confirm',
]

const SOURCE_PRIORITY: Record<RecoverySource, number> = {
  same_selector: 1,
  accessibility_label: 2,
  aria_label: 3,
  associated_label: 4,
  button_text: 5,
  placeholder: 6,
  nearby_text: 7,
  stable_id: 8,
  stable_data_testid: 9,
}

export function shouldAttemptSelectorRecovery(
  action: VerifiableAction & { safety_level?: string; reasoning?: string },
  result: BasicExecutionResult,
  verification: ActionVerification | undefined,
  recoveryAlreadyAttempted = false,
): boolean {
  return Boolean(
    result.success &&
    verification &&
    verification.verified === false &&
    verification.reason === 'no_effect' &&
    !recoveryAlreadyAttempted &&
    SUPPORTED_RECOVERY_ACTIONS.has(action.action_type) &&
    !isDestructiveAction(action),
  )
}

export function chooseRecoveryCandidate(
  action: VerifiableAction,
  candidates: SelectorRecoveryCandidate[],
): SelectorRecoveryChoice | null {
  const compatible = candidates
    .filter((candidate) => candidate.visible)
    .filter((candidate) => candidate.action_types.includes(action.action_type))

  if (compatible.length === 0) return null

  const originalSelector = (action.target_selector || '').trim()
  const alternates = compatible.filter((candidate) => candidate.selector.trim() !== originalSelector)
  const pool = alternates.length > 0 ? alternates : compatible

  const scored = pool
    .map((candidate, index) => ({
      candidate,
      index,
      relevance: relevanceScore(action, candidate),
      priority: SOURCE_PRIORITY[candidate.source],
    }))
    .filter(({ relevance, candidate }) => relevance > 0 || candidate.source === 'same_selector')
    .sort((a, b) =>
      b.relevance - a.relevance ||
      a.priority - b.priority ||
      a.index - b.index
    )

  const selected = scored[0]?.candidate
  if (!selected) return null

  return {
    selector: selected.selector,
    source: selected.source,
    reason: `Recovered selector via ${selected.source}`,
  }
}

export function findRecoverySelector(action: VerifiableAction): SelectorRecoveryChoice | null {
  const sourcePriority: Record<RecoverySource, number> = {
    same_selector: 1,
    accessibility_label: 2,
    aria_label: 3,
    associated_label: 4,
    button_text: 5,
    placeholder: 6,
    nearby_text: 7,
    stable_id: 8,
    stable_data_testid: 9,
  }

  function normalize(text: string | null | undefined): string {
    return (text || '').replace(/\s+/g, ' ').trim()
  }

  function visible(candidate: Element | null): candidate is HTMLElement {
    if (!(candidate instanceof HTMLElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
  }

  function css(value: string): string {
    return CSS.escape(value)
  }

  function quote(value: string): string {
    return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
  }

  function stableSelector(element: HTMLElement): string | null {
    const testId = element.getAttribute('data-testid') || element.getAttribute('data-test-id')
    if (testId) return `[data-testid=${quote(testId)}], [data-test-id=${quote(testId)}]`
    const id = element.getAttribute('id')
    if (id && !/^[\d\s]|[:]/.test(id)) return `#${css(id)}`
    const aria = element.getAttribute('aria-label')
    if (aria) return `${element.tagName.toLowerCase()}[aria-label=${quote(aria)}]`
    const placeholder = element.getAttribute('placeholder')
    if (placeholder) return `${element.tagName.toLowerCase()}[placeholder=${quote(placeholder)}]`
    const name = element.getAttribute('name')
    if (name) return `${element.tagName.toLowerCase()}[name=${quote(name)}]`
    return nthSelector(element)
  }

  function nthSelector(element: HTMLElement): string {
    const parts: string[] = []
    let current: HTMLElement | null = element
    while (current && current !== document.body && parts.length < 4) {
      const tag = current.tagName.toLowerCase()
      const siblings = Array.from(current.parentElement?.children || []).filter((sibling) => sibling.tagName === current?.tagName)
      const index = siblings.indexOf(current) + 1
      parts.unshift(siblings.length > 1 ? `${tag}:nth-of-type(${index})` : tag)
      current = current.parentElement
    }
    return parts.join(' > ')
  }

  function labelText(element: HTMLElement): string {
    const id = element.getAttribute('id')
    if (id) {
      const explicit = document.querySelector(`label[for=${quote(id)}]`)
      if (explicit) return normalize(explicit.textContent)
    }
    const wrapping = element.closest('label')
    if (wrapping) return normalize(wrapping.textContent)
    return ''
  }

  function nearbyText(element: HTMLElement): string {
    const parent = element.parentElement
    if (!parent) return ''
    return normalize(parent.textContent).slice(0, 160)
  }

  function addCandidate(
    candidates: SelectorRecoveryCandidate[],
    element: HTMLElement,
    source: RecoverySource,
    text: string,
    actionTypes: string[],
  ) {
    if (!visible(element)) return
    const selector = stableSelector(element)
    if (!selector) return
    candidates.push({
      selector,
      source,
      text: normalize(text),
      visible: true,
      action_types: actionTypes,
    })
  }

  function localRelevanceScore(candidate: SelectorRecoveryCandidate): number {
    const goal = `${action.description || ''} ${action.value || ''} ${action.target_selector || ''}`.toLowerCase()
    const text = candidate.text.toLowerCase()
    if (!text) return candidate.source === 'same_selector' ? 1 : 0
    const tokens = text.split(/[^a-z0-9]+/).filter((token) => token.length >= 2)
    if (tokens.length === 0) return 0
    const matches = tokens.filter((token) => goal.includes(token)).length
    if (matches === 0) return 0
    return matches / tokens.length
  }

  function localChoose(candidatesToChoose: SelectorRecoveryCandidate[]): SelectorRecoveryChoice | null {
    const compatible = candidatesToChoose
      .filter((candidate) => candidate.visible)
      .filter((candidate) => candidate.action_types.includes(action.action_type))
    if (compatible.length === 0) return null

    const originalSelector = (action.target_selector || '').trim()
    const alternates = compatible.filter((candidate) => candidate.selector.trim() !== originalSelector)
    const pool = alternates.length > 0 ? alternates : compatible
    const scored = pool
      .map((candidate, index) => ({
        candidate,
        index,
        relevance: localRelevanceScore(candidate),
        priority: sourcePriority[candidate.source],
      }))
      .filter(({ relevance, candidate }) => relevance > 0 || candidate.source === 'same_selector')
      .sort((a, b) =>
        b.relevance - a.relevance ||
        a.priority - b.priority ||
        a.index - b.index
      )

    const selected = scored[0]?.candidate
    if (!selected) return null
    return {
      selector: selected.selector,
      source: selected.source,
      reason: `Recovered selector via ${selected.source}`,
    }
  }

  const candidates: SelectorRecoveryCandidate[] = []
  let original: Element | null = null
  try {
    original = action.target_selector ? document.querySelector(action.target_selector) : null
  } catch {
    original = null
  }
  if (visible(original)) {
    candidates.push({
      selector: action.target_selector || '',
      source: 'same_selector',
      text: normalize(original.textContent || original.getAttribute('aria-label') || original.getAttribute('placeholder')),
      visible: true,
      action_types: [action.action_type],
    })
  }

  if (action.action_type === 'click') {
    const elements = Array.from(document.querySelectorAll(
      'button, a[href], [role="button"], input[type="button"], input[type="submit"], [aria-label], [data-testid], [data-test-id]',
    )).filter(visible)
    for (const element of elements) {
      const aria = element.getAttribute('aria-label')
      const accessible = aria || element.getAttribute('title')
      const text = normalize(element instanceof HTMLInputElement ? element.value : element.textContent)
      const testId = element.getAttribute('data-testid') || element.getAttribute('data-test-id')
      const id = element.getAttribute('id')
      if (accessible) addCandidate(candidates, element, accessible === aria ? 'aria_label' : 'accessibility_label', accessible, ['click'])
      if (text) addCandidate(candidates, element, 'button_text', text, ['click'])
      if (testId) addCandidate(candidates, element, 'stable_data_testid', testId, ['click'])
      if (id) addCandidate(candidates, element, 'stable_id', id, ['click'])
      const nearby = nearbyText(element)
      if (nearby) addCandidate(candidates, element, 'nearby_text', nearby, ['click'])
    }
  }

  if (action.action_type === 'fill') {
    const elements = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]')).filter(visible)
    for (const element of elements) {
      const placeholder = element.getAttribute('placeholder')
      const aria = element.getAttribute('aria-label')
      const label = labelText(element)
      const testId = element.getAttribute('data-testid') || element.getAttribute('data-test-id')
      const id = element.getAttribute('id')
      if (aria) addCandidate(candidates, element, 'aria_label', aria, ['fill'])
      if (label) addCandidate(candidates, element, 'associated_label', label, ['fill'])
      if (placeholder) addCandidate(candidates, element, 'placeholder', placeholder, ['fill'])
      if (testId) addCandidate(candidates, element, 'stable_data_testid', testId, ['fill'])
      if (id) addCandidate(candidates, element, 'stable_id', id, ['fill'])
      const nearby = nearbyText(element)
      if (nearby) addCandidate(candidates, element, 'nearby_text', nearby, ['fill'])
    }
  }

  if (action.action_type === 'select_option') {
    const elements = Array.from(document.querySelectorAll('select, [role="combobox"], [aria-haspopup="listbox"]')).filter(visible)
    for (const element of elements) {
      const aria = element.getAttribute('aria-label')
      const label = labelText(element)
      const testId = element.getAttribute('data-testid') || element.getAttribute('data-test-id')
      const id = element.getAttribute('id')
      if (aria) addCandidate(candidates, element, 'aria_label', aria, ['select_option'])
      if (label) addCandidate(candidates, element, 'associated_label', label, ['select_option'])
      if (testId) addCandidate(candidates, element, 'stable_data_testid', testId, ['select_option'])
      if (id) addCandidate(candidates, element, 'stable_id', id, ['select_option'])
      const nearby = nearbyText(element)
      if (nearby) addCandidate(candidates, element, 'nearby_text', nearby, ['select_option'])
    }
  }

  return localChoose(candidates)
}

function isDestructiveAction(action: VerifiableAction & { safety_level?: string; reasoning?: string }): boolean {
  if (action.safety_level === 'danger') return true
  const haystack = `${action.description || ''} ${action.reasoning || ''} ${action.value || ''}`.toLowerCase()
  return DESTRUCTIVE_TERMS.some((term) => haystack.includes(term))
}

function relevanceScore(action: VerifiableAction, candidate: SelectorRecoveryCandidate): number {
  const goal = `${action.description || ''} ${action.value || ''} ${action.target_selector || ''}`.toLowerCase()
  const text = candidate.text.toLowerCase()
  if (!text) return candidate.source === 'same_selector' ? 1 : 0
  const tokens = text.split(/[^a-z0-9]+/).filter((token) => token.length >= 2)
  if (tokens.length === 0) return 0
  const matches = tokens.filter((token) => goal.includes(token)).length
  if (matches === 0) return 0
  return matches / tokens.length
}
