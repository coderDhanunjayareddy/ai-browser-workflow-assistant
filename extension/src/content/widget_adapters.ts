export interface WidgetAction {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
}

export interface WidgetAdapterResult {
  success: boolean
  message: string
  action_id: string
  widget_adapter?: string
}

export interface WidgetDescriptor {
  kind: 'date_picker' | 'combobox' | 'autocomplete' | 'cookie_banner' | 'modal_dialog'
  role?: string | null
  tagName?: string | null
  text?: string | null
  ariaExpanded?: string | null
  ariaControls?: string | null
  autocomplete?: string | null
  hasListbox?: boolean
  hasDialog?: boolean
  visible?: boolean
}

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

export function isSafeWidgetAction(action: WidgetAction): boolean {
  if (action.safety_level === 'danger') return false
  const haystack = `${action.description || ''} ${action.reasoning || ''} ${action.value || ''}`.toLowerCase()
  return !DESTRUCTIVE_TERMS.some((term) => haystack.includes(term))
}

export function chooseWidgetAdapter(
  action: WidgetAction,
  descriptors: WidgetDescriptor[],
): WidgetDescriptor['kind'] | null {
  if (!isSafeWidgetAction(action)) return null
  const visible = descriptors.filter((descriptor) => descriptor.visible !== false)
  if (visible.some((descriptor) => descriptor.kind === 'cookie_banner')) return 'cookie_banner'
  if (visible.some((descriptor) => descriptor.kind === 'modal_dialog')) return 'modal_dialog'
  if (
    action.action_type === 'choose_date' ||
    visible.some((descriptor) => descriptor.kind === 'date_picker')
  ) return 'date_picker'
  if (
    action.action_type === 'select_option' &&
    visible.some((descriptor) => descriptor.kind === 'combobox')
  ) return 'combobox'
  if (
    action.action_type === 'fill' &&
    visible.some((descriptor) => descriptor.kind === 'autocomplete')
  ) return 'autocomplete'
  return null
}

export async function executeWidgetAdapter(action: WidgetAction): Promise<WidgetAdapterResult | null> {
  function normalize(text: string | null | undefined): string {
    return (text || '').replace(/\s+/g, ' ').trim()
  }

  function lower(text: string | null | undefined): string {
    return normalize(text).toLowerCase()
  }

  function safeQuery(selector: string | null): Element | null {
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

  function isSafe(): boolean {
    if (action.safety_level === 'danger') return false
    const haystack = `${action.description || ''} ${action.reasoning || ''} ${action.value || ''}`.toLowerCase()
    return ![
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
    ].some((term) => haystack.includes(term))
  }

  function wait(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  function fireInput(element: HTMLInputElement | HTMLTextAreaElement, value: string) {
    element.focus()
    element.value = value
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }

  function clickElement(element: HTMLElement) {
    element.scrollIntoView({ block: 'center', inline: 'center' })
    element.click()
  }

  function textOf(element: Element | null): string {
    if (!element) return ''
    return normalize(
      element.getAttribute('aria-label') ||
      element.getAttribute('title') ||
      (element instanceof HTMLInputElement ? element.value : '') ||
      element.textContent ||
      '',
    )
  }

  function findVisibleByText(selectors: string[], text: string | null, root: ParentNode = document): HTMLElement | null {
    const needle = lower(text)
    if (!needle) return null
    const candidates = Array.from(root.querySelectorAll(selectors.join(', '))).filter(visible)
    return candidates.find((candidate) => lower(textOf(candidate)).includes(needle)) ?? null
  }

  function activeDialog(): HTMLElement | null {
    return Array.from(document.querySelectorAll('[role="dialog"], [aria-modal="true"], dialog, .modal'))
      .find(visible) ?? null
  }

  function findCookieBanner(): HTMLElement | null {
    return Array.from(document.querySelectorAll(
      '[aria-label*="cookie" i], [id*="cookie" i], [class*="cookie" i], [id*="consent" i], [class*="consent" i], [data-testid*="cookie" i], [data-testid*="consent" i]',
    )).find(visible) ?? null
  }

  function targetElement(): HTMLElement | null {
    const direct = safeQuery(action.target_selector)
    return visible(direct) ? direct : null
  }

  async function cookieBannerAdapter(): Promise<WidgetAdapterResult | null> {
    const banner = findCookieBanner()
    if (!banner) return null
    const policyText = lower(`${action.description || ''} ${action.value || ''}`)
    const wantsReject = /\b(reject|decline|deny|necessary only)\b/.test(policyText)
    const wantsAccept = /\b(accept|agree|allow|consent|continue)\b/.test(policyText)
    if (!wantsAccept && !wantsReject) return null
    const labels = wantsReject
      ? ['Reject', 'Decline', 'Deny', 'Necessary only']
      : ['Accept all', 'Accept', 'Agree', 'Allow all', 'Got it', 'OK']
    for (const label of labels) {
      const button = findVisibleByText(['button', '[role="button"], input[type="button"]', 'a'], label, banner)
      if (button) {
        clickElement(button)
        return { success: true, message: `Widget adapter handled cookie banner: ${label}`, action_id: action.action_id, widget_adapter: 'cookie_banner' }
      }
    }
    return null
  }

  async function modalAdapter(): Promise<WidgetAdapterResult | null> {
    const dialog = activeDialog()
    if (!dialog) return null
    const requested = lower(`${action.description || ''} ${action.value || ''}`)
    if (/\b(close|dismiss|cancel)\b/.test(requested)) {
      const close = findVisibleByText(['button', '[role="button"]', 'a'], 'Close', dialog) ||
        dialog.querySelector('[aria-label*="close" i], [data-testid*="close" i], .close') as HTMLElement | null
      if (visible(close)) {
        clickElement(close)
        return { success: true, message: 'Widget adapter closed modal dialog.', action_id: action.action_id, widget_adapter: 'modal_dialog' }
      }
    }

    const target = targetElement()
    if (target && dialog.contains(target)) {
      if (action.action_type === 'click') {
        clickElement(target)
        return { success: true, message: 'Widget adapter clicked inside modal dialog.', action_id: action.action_id, widget_adapter: 'modal_dialog' }
      }
      if (action.action_type === 'fill' && (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) {
        fireInput(target, action.value || '')
        return { success: true, message: 'Widget adapter filled modal field.', action_id: action.action_id, widget_adapter: 'modal_dialog' }
      }
    }
    return null
  }

  async function datePickerAdapter(): Promise<WidgetAdapterResult | null> {
    if (action.action_type !== 'choose_date' && !/\b(date|calendar|check-in|checkout|check out)\b/i.test(`${action.description || ''} ${action.value || ''}`)) return null
    const target = targetElement()
    if (target) {
      clickElement(target)
      await wait(250)
    }

    const value = action.value || action.description || ''
    const dateText = normalize(value)
    const day = dateText.match(/\b([0-3]?\d)\b/)?.[1] || dateText
    const root = activeDialog() || document
    const selectors = [
      '[role="gridcell"]',
      '[role="button"]',
      'button',
      'td',
      '[aria-label]',
      '[data-testid*="day" i]',
      '[class*="day" i]',
    ]
    const exact = Array.from(root.querySelectorAll(selectors.join(', ')))
      .filter(visible)
      .find((candidate) => {
        const label = lower(textOf(candidate))
        return label === lower(day) || label.includes(lower(dateText))
      }) as HTMLElement | undefined
    if (exact) {
      clickElement(exact)
      await wait(150)
      return { success: true, message: `Widget adapter selected date: ${dateText}`, action_id: action.action_id, widget_adapter: 'date_picker' }
    }
    return null
  }

  async function comboboxAdapter(): Promise<WidgetAdapterResult | null> {
    if (action.action_type !== 'select_option') return null
    const target = targetElement() ||
      Array.from(document.querySelectorAll('[role="combobox"], [aria-haspopup="listbox"], [aria-expanded][aria-controls]')).find(visible)
    if (!target) return null
    clickElement(target)
    await wait(250)

    if (target instanceof HTMLInputElement && action.value) {
      fireInput(target, action.value)
      await wait(300)
    } else {
      const search = Array.from(document.querySelectorAll('[role="listbox"] input, [role="dialog"] input, input[role="combobox"], input[type="search"]')).find(visible)
      if (search instanceof HTMLInputElement && action.value) {
        fireInput(search, action.value)
        await wait(300)
      }
    }

    const option = findVisibleByText(['[role="option"]', '[role="listitem"]', 'li', 'button', '[data-testid]', 'div', 'span'], action.value)
    if (option) {
      clickElement(option)
      return { success: true, message: `Widget adapter selected option: ${action.value}`, action_id: action.action_id, widget_adapter: 'combobox' }
    }
    return null
  }

  async function autocompleteAdapter(): Promise<WidgetAdapterResult | null> {
    if (action.action_type !== 'fill') return null
    const target = targetElement()
    if (!(target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) return null
    const autoAttr = `${target.getAttribute('autocomplete') || ''} ${target.getAttribute('aria-autocomplete') || ''} ${target.getAttribute('role') || ''}`.toLowerCase()
    if (!autoAttr.includes('list') && !autoAttr.includes('combobox') && !target.getAttribute('aria-controls')) return null
    fireInput(target, action.value || '')
    await wait(350)
    const suggestion = findVisibleByText(['[role="option"]', '[role="listitem"]', 'li', 'button', '[data-testid]', 'div', 'span'], action.value)
    if (suggestion) {
      clickElement(suggestion)
      return { success: true, message: `Widget adapter selected autocomplete suggestion: ${action.value}`, action_id: action.action_id, widget_adapter: 'autocomplete' }
    }
    return { success: true, message: 'Widget adapter filled autocomplete input without selectable suggestion.', action_id: action.action_id, widget_adapter: 'autocomplete' }
  }

  if (!isSafe()) return null
  return await cookieBannerAdapter() ||
    await modalAdapter() ||
    await datePickerAdapter() ||
    await comboboxAdapter() ||
    await autocompleteAdapter()
}
