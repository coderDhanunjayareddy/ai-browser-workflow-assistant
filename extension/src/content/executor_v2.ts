export async function executeActionV2(action: {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
}): Promise<{ success: boolean; message: string; action_id: string; [key: string]: unknown }> {
  const { action_id, action_type, value } = action
  let selector = action.target_selector

  // Helper: query element safely
  function safeQuery(sel: string): Element | null {
    try {
      return document.querySelector(sel)
    } catch {
      return null
    }
  }

  // Helper: wait for element
  function waitForElement(sel: string, timeoutMs = 5000): Promise<Element | null> {
    return new Promise((resolve) => {
      const immediate = safeQuery(sel)
      if (immediate) { resolve(immediate); return }

      const deadline = Date.now() + timeoutMs
      const interval = setInterval(() => {
        const el = safeQuery(sel)
        if (el) {
          clearInterval(interval)
          resolve(el)
        } else if (Date.now() >= deadline) {
          clearInterval(interval)
          resolve(null)
        }
      }, 100)
    })
  }

  function isVisibleElement(candidate: Element | null): candidate is HTMLElement {
    if (!(candidate instanceof HTMLElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
  }

  function findVisibleByText(selectors: string[], text: string | null): HTMLElement | null {
    const needle = (text || '').replace(/\s+/g, ' ').trim().toLowerCase()
    if (!needle) return null
    const candidates = Array.from(document.querySelectorAll(selectors.join(', '))).filter(isVisibleElement)
    return candidates.find((candidate) =>
      (candidate.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase().includes(needle)
    ) ?? null
  }

  function normalizeSafeHttpUrl(raw: string | null): string | null {
    if (!raw) return null
    try {
      const url = new URL(raw, window.location.href)
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
      return url.toString()
    } catch {
      return null
    }
  }

  function sameUrlIgnoringHash(left: string, right: string): boolean {
    try {
      const a = new URL(left)
      const b = new URL(right)
      a.hash = ''
      b.hash = ''
      return a.toString() === b.toString()
    } catch {
      return left === right
    }
  }

  function isDisabledElement(candidate: HTMLElement): boolean {
    const ariaDisabled = (candidate.getAttribute('aria-disabled') || '').toLowerCase() === 'true'
    const disabledClass = /\b(disabled|inactive|unavailable)\b/i.test(candidate.className || '')
    const nativeDisabled = candidate instanceof HTMLButtonElement || candidate instanceof HTMLInputElement
      ? candidate.disabled
      : false
    return ariaDisabled || disabledClass || nativeDisabled
  }

  function candidateLabel(candidate: HTMLElement): string {
    return [
      candidate.getAttribute('aria-label') || '',
      candidate.getAttribute('title') || '',
      candidate.textContent || '',
    ].join(' ').replace(/\s+/g, ' ').trim()
  }

  function fieldLabel(field: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement): string {
    const byAria = field.getAttribute('aria-label') || field.getAttribute('placeholder') || field.getAttribute('name') || ''
    if (byAria) return byAria.trim()
    const id = field.id
    if (id) {
      const label = document.querySelector(`label[for="${CSS.escape(id)}"]`)
      if (label?.textContent) return label.textContent.replace(/\s+/g, ' ').trim()
    }
    const wrapped = field.closest('label')
    return (wrapped?.textContent || '').replace(/\s+/g, ' ').trim()
  }

  function formEvidence(field: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement): Record<string, string | number | boolean | null> {
    const form = field.form
    const fields = form
      ? Array.from(form.querySelectorAll('input, textarea, select'))
      : Array.from(document.querySelectorAll('input, textarea, select'))
    const fillable = fields.filter((candidate): candidate is HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement => {
      if (!(candidate instanceof HTMLInputElement || candidate instanceof HTMLTextAreaElement || candidate instanceof HTMLSelectElement)) return false
      if (candidate instanceof HTMLInputElement && ['hidden', 'submit', 'button', 'reset', 'file', 'image'].includes(candidate.type)) return false
      return isVisibleElement(candidate)
    })
    const invalid = fillable.filter((candidate) => typeof candidate.checkValidity === 'function' && !candidate.checkValidity())
    const filled = fillable.filter((candidate) => {
      if (candidate instanceof HTMLInputElement && ['checkbox', 'radio'].includes(candidate.type)) return candidate.checked
      return Boolean(candidate.value)
    })
    const submitControl = form?.querySelector('button[type="submit"], input[type="submit"], button:not([type])') || null
    return {
      form_field_name: field.name || field.id || null,
      form_field_label: fieldLabel(field) || null,
      form_field_type: field instanceof HTMLInputElement ? field.type : field.tagName.toLowerCase(),
      form_id: form?.id || form?.getAttribute('name') || null,
      field_valid: typeof field.checkValidity === 'function' ? field.checkValidity() : true,
      validation_message: 'validationMessage' in field ? field.validationMessage || null : null,
      form_valid: form && typeof form.checkValidity === 'function' ? form.checkValidity() : invalid.length === 0,
      invalid_field_count: invalid.length,
      filled_field_count: filled.length,
      submit_control_detected: Boolean(submitControl),
    }
  }

  function findNextPageControl(): HTMLElement | null {
    const directSelectors = [
      'a[rel="next"]',
      'area[rel="next"]',
      'a.next',
      '.next a',
      'a[aria-label*="next" i]',
      'button[aria-label*="next" i]',
      '[role="link"][aria-label*="next" i]',
      '[role="button"][aria-label*="next" i]',
      'a[title*="next" i]',
      'button[title*="next" i]',
      '[data-testid*="next" i]',
      '[class*="next" i]',
    ]
    const direct = Array.from(document.querySelectorAll(directSelectors.join(', ')))
      .filter(isVisibleElement)
      .filter((candidate) => !isDisabledElement(candidate))
    if (direct.length > 0) return direct[0]

    const controls = Array.from(document.querySelectorAll('a, button, [role="link"], [role="button"]'))
      .filter(isVisibleElement)
      .filter((candidate) => !isDisabledElement(candidate))
    return controls.find((candidate) => {
      const label = candidateLabel(candidate).toLowerCase()
      return /^(next|next page|load more|show more|more|>|\u203a|\u00bb)$/.test(label) ||
        /\b(next|next page|load more|show more)\b/.test(label)
    }) ?? null
  }

  function hrefForControl(candidate: HTMLElement): string | null {
    const link = candidate instanceof HTMLAnchorElement || candidate instanceof HTMLAreaElement
      ? candidate
      : candidate.closest('a') || candidate.querySelector('a[href]')
    return normalizeSafeHttpUrl(link?.getAttribute('href') || null)
  }

  // Resolve element by selector
  let targetEl: Element | null = null
  if (selector) {
    targetEl = await waitForElement(selector)
  }

  try {
    switch (action_type) {
      case 'click': {
        if (!targetEl) return { success: false, message: `Click target not found: ${selector}`, action_id }
        if (targetEl instanceof HTMLElement) {
          targetEl.scrollIntoView({ block: 'center', inline: 'center' })
          targetEl.click()
          return { success: true, message: `Clicked: ${selector}`, action_id }
        }
        return { success: false, message: `Target not clickable html element: ${selector}`, action_id }
      }

      case 'fill': {
        if (!targetEl) return { success: false, message: `Fill target not found: ${selector}`, action_id }
        if (targetEl instanceof HTMLInputElement || targetEl instanceof HTMLTextAreaElement) {
          targetEl.focus()
          targetEl.value = value || ''
          targetEl.dispatchEvent(new Event('input', { bubbles: true }))
          targetEl.dispatchEvent(new Event('change', { bubbles: true }))
          if (targetEl.value !== (value || '')) {
            return { success: false, message: `Field value was not retained after fill: ${selector}`, action_id }
          }
          return { success: true, message: `Filled field: ${selector}`, action_id, ...formEvidence(targetEl) }
        }
        return { success: false, message: `Target is not a fillable input: ${selector}`, action_id }
      }

      case 'select_option': {
        if (!targetEl) return { success: false, message: `Select target not found: ${selector}`, action_id }
        if (targetEl instanceof HTMLSelectElement) {
          targetEl.value = value || ''
          targetEl.dispatchEvent(new Event('change', { bubbles: true }))
          return { success: true, message: `Selected option: ${value} on select: ${selector}`, action_id }
        }
        if (targetEl instanceof HTMLElement) {
          targetEl.scrollIntoView({ block: 'center', inline: 'center' })
          targetEl.click()
          await new Promise((resolve) => setTimeout(resolve, 500))
          const option = findVisibleByText(
            ['[role="option"]', '[role="listitem"]', 'li', 'button', '[data-testid]', 'div', 'span'],
            value,
          )
          if (option) {
            option.scrollIntoView({ block: 'center', inline: 'center' })
            option.click()
            return { success: true, message: `Selected visible option: ${value}`, action_id }
          }
        }
        return { success: false, message: `No visible option found for: ${value}`, action_id }
      }

      case 'choose_date': {
        if (!targetEl) {
          targetEl = findVisibleByText(
            ['[role="gridcell"]', '[role="button"]', 'button', 'td', 'div', 'span'],
            value,
          )
        }
        if (!targetEl) return { success: false, message: `Date picker target not found: ${selector || value}`, action_id }
        // Clicks the calendar target day cell
        if (targetEl instanceof HTMLElement) {
          targetEl.scrollIntoView({ block: 'center', inline: 'center' })
          targetEl.click()
          return { success: true, message: `Chose date: ${value} via: ${selector}`, action_id }
        }
        return { success: false, message: `Target not html element for date picker`, action_id }
      }

      case 'hover': {
        if (!targetEl) return { success: false, message: `Hover target not found: ${selector}`, action_id }
        if (targetEl instanceof HTMLElement) {
          targetEl.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))
          targetEl.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
          return { success: true, message: `Hovered over: ${selector}`, action_id }
        }
        return { success: false, message: `Target not hoverable html element`, action_id }
      }

      case 'keyboard_shortcut': {
        const active = document.activeElement
        if (active instanceof HTMLElement && value) {
          const keyEvent = new KeyboardEvent('keydown', { key: value, code: value, bubbles: true })
          active.dispatchEvent(keyEvent)
          return { success: true, message: `Dispatched keyboard shortcut ${value} to active element.`, action_id }
        }
        return { success: false, message: 'No active element or key specified.', action_id }
      }

      case 'scroll': {
        const direction = (value ?? 'down').toLowerCase()
        const delta = direction === 'up' ? -400 : 400
        if (!selector || selector === 'window') {
          window.scrollBy({ top: delta, behavior: 'smooth' })
          return { success: true, message: `Scrolled ${direction} window.`, action_id }
        }
        if (targetEl) {
          targetEl.scrollBy({ top: delta, behavior: 'smooth' })
          return { success: true, message: `Scrolled ${direction} on: ${selector}`, action_id }
        }
        return { success: false, message: `Scroll target not found: ${selector}`, action_id }
      }

      case 'navigate': {
        if (!value) return { success: false, message: 'No URL provided.', action_id }
        window.location.href = value
        return { success: true, message: `Navigating to: ${value}`, action_id }
      }

      case 'navigate_next_page': {
        const requestedUrl = normalizeSafeHttpUrl(value)
        if (requestedUrl && !sameUrlIgnoringHash(requestedUrl, window.location.href)) {
          window.location.href = requestedUrl
          return { success: true, message: `Navigating to next page: ${requestedUrl}`, action_id, next_page_url: requestedUrl, pagination_mode: 'next_link', pagination_control_label: 'requested_url', pagination_used_fallback_click: false }
        }

        const headNext = normalizeSafeHttpUrl(document.querySelector<HTMLLinkElement>('link[rel="next"]')?.href || null)
        if (headNext && !sameUrlIgnoringHash(headNext, window.location.href)) {
          window.location.href = headNext
          return { success: true, message: `Navigating to next page: ${headNext}`, action_id, next_page_url: headNext, pagination_mode: 'next_link', pagination_control_label: 'link[rel=next]', pagination_used_fallback_click: false }
        }

        const control = findNextPageControl()
        if (!control) return { success: false, message: 'No enabled next-page control found.', action_id }

        const href = hrefForControl(control)
        const controlLabel = candidateLabel(control) || control.tagName.toLowerCase()
        if (href && !sameUrlIgnoringHash(href, window.location.href)) {
          window.location.href = href
          return { success: true, message: `Navigating to next page: ${href}`, action_id, next_page_url: href, pagination_mode: 'next_link', pagination_control_label: controlLabel, pagination_used_fallback_click: false }
        }

        control.scrollIntoView({ block: 'center', inline: 'center' })
        control.click()
        return { success: true, message: `Clicked next page control: ${controlLabel}`, action_id, next_page_url: window.location.href, pagination_mode: 'next_link', pagination_control_label: controlLabel, pagination_used_fallback_click: true }
      }

      case 'wait': {
        const waitMs = Number(value ?? 2000)
        await new Promise((resolve) => setTimeout(resolve, waitMs))
        return { success: true, message: `Waited ${waitMs}ms`, action_id }
      }

      default:
        return { success: false, message: `Action type not supported in V2: ${action_type}`, action_id }
    }
  } catch (err) {
    return { success: false, message: `Runtime execution error: ${String(err)}`, action_id }
  }
}
