export async function executeActionV2(action: {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
}): Promise<{ success: boolean; message: string; action_id: string }> {
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
          return { success: true, message: `Filled field: ${selector}`, action_id }
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
