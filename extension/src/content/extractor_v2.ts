import type { PageContext } from '../types'

export function extractPageContextV2(): PageContext {
  const INTERACTIVE_SELECTOR = [
    'button',
    'a[href]',
    'input:not([type="hidden"])',
    'select',
    'textarea',
    '[contenteditable="true"]',
    '[role="textbox"]',
    '[role="searchbox"]',
    '[role="button"]:not(button)',
    '[role="listitem"]',
    '[role="option"]',
    '[role="menuitem"]',
    '[role="row"]',
    '[role="tab"]',
    'span[title]:not([title=""])',
  ].join(', ')

  const MAX_ELEMENTS = 150
  const MAX_TEXT_LENGTH = 1000
  const MAX_VALUE_LENGTH = 200

  function sanitizeText(text: string): string {
    return text
      .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[redacted-ssn]')
      .replace(/\b(?:\d{4}[\s-]?){3}\d{4}\b/g, '[redacted-card]')
  }

  function isVisible(el: Element): boolean {
    if (!(el instanceof HTMLElement)) return false
    const style = window.getComputedStyle(el)
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false
    const rect = el.getBoundingClientRect()
    return rect.width > 0 && rect.height > 0
  }

  function buildSelector(el: Element): string {
    if (el.id) return `#${CSS.escape(el.id)}`
    const testId = el.getAttribute('data-testid')
    if (testId) return `[data-testid="${testId}"]`
    
    const ariaLabel = el.getAttribute('aria-label')
    if (ariaLabel) return `${el.tagName.toLowerCase()}[aria-label="${ariaLabel}"]`

    const title = el.getAttribute('title')
    if (title) return `${el.tagName.toLowerCase()}[title="${title}"]`

    const placeholder = el.getAttribute('placeholder')
    if (placeholder) return `${el.tagName.toLowerCase()}[placeholder="${placeholder}"]`

    const parts: string[] = []
    let current: Element | null = el
    let depth = 0
    while (current && current.tagName !== 'BODY' && depth < 5) {
      let part = current.tagName.toLowerCase()
      const role = current.getAttribute('role')
      if (role) part += `[role="${CSS.escape(role)}"]`

      const parent = current.parentElement
      if (parent) {
        const siblings = Array.from(parent.children).filter((child) => child.tagName === current!.tagName)
        if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(current) + 1})`
      }
      parts.unshift(part)
      current = current.parentElement
      depth++
    }
    return parts.join(' > ') || el.tagName.toLowerCase()
  }

  function getAccessibilityRole(el: Element): string {
    const roleAttr = el.getAttribute('role')
    if (roleAttr) return roleAttr

    const tag = el.tagName.toLowerCase()
    if (tag === 'button') return 'button'
    if (tag === 'a') return 'link'
    if (tag === 'input') {
      const type = (el as HTMLInputElement).type
      if (type === 'checkbox') return 'checkbox'
      if (type === 'radio') return 'radio'
      return 'textbox'
    }
    if (tag === 'select') return 'combobox'
    if (tag === 'textarea') return 'textbox'
    return 'generic'
  }

  function getAccessibilityName(el: Element): string {
    const ariaLabel = el.getAttribute('aria-label')
    if (ariaLabel) return ariaLabel

    const title = el.getAttribute('title')
    if (title) return title

    const placeholder = el.getAttribute('placeholder')
    if (placeholder) return placeholder

    return (el.textContent || '').trim()
  }

  function getAccessibilityState(el: Element): Record<string, string | boolean> {
    const state: Record<string, string | boolean> = {}
    if (el.getAttribute('aria-expanded')) {
      state['expanded'] = el.getAttribute('aria-expanded') === 'true'
    }
    if (el.getAttribute('aria-checked')) {
      state['checked'] = el.getAttribute('aria-checked') === 'true'
    }
    // M1.2: native <details> open/closed state (evidence-backed, no ARIA attribute needed).
    if (el.tagName === 'DETAILS') {
      state['expanded'] = (el as HTMLDetailsElement).open
    }

    if (el instanceof HTMLInputElement) {
      if (el.disabled) state['disabled'] = true
      if (el.readOnly) state['readonly'] = true

      // M1.2: current value/checked so the planner can tell "already filled" from "empty".
      // Native .checked is ground truth for real checkbox/radio inputs (overrides any
      // aria-checked read above, which exists for ARIA-widget checkboxes, e.g. <div role=checkbox>).
      if (el.type === 'checkbox' || el.type === 'radio') {
        state['checked'] = el.checked
      } else if (
        el.type !== 'password' && el.type !== 'file' && el.type !== 'hidden' &&
        el.type !== 'submit' && el.type !== 'button' && el.type !== 'reset' && el.type !== 'image'
      ) {
        // Password fields are explicitly excluded from value capture — never even redacted.
        if (el.value) state['value'] = sanitizeText(el.value).slice(0, MAX_VALUE_LENGTH)
      }
    } else if (el instanceof HTMLTextAreaElement) {
      if (el.value) state['value'] = sanitizeText(el.value).slice(0, MAX_VALUE_LENGTH)
    } else if (el instanceof HTMLSelectElement) {
      if (el.value) state['value'] = el.value
      const selectedOption = el.options[el.selectedIndex]
      if (selectedOption && selectedOption.text) {
        state['selected_text'] = sanitizeText(selectedOption.text).slice(0, MAX_VALUE_LENGTH)
      }
    } else if (el.getAttribute('contenteditable') === 'true') {
      const text = (el as HTMLElement).innerText || el.textContent || ''
      if (text) state['value'] = sanitizeText(text).slice(0, MAX_VALUE_LENGTH)
    }

    return state
  }

  function collectContentBlocks(): { text: string; selector: string }[] {
    const candidates = Array.from(document.querySelectorAll([
      'article',
      'li',
      '[role="listitem"]',
      '[role="row"]',
      '[data-testid]',
      'section',
      'a[href]',
      'div',
    ].join(', ')))

    const seen = new Set<string>()
    return candidates
      .filter(isVisible)
      .map((el) => ({
        el,
        text: sanitizeText((el.textContent || '').replace(/\s+/g, ' ').trim()).slice(0, 500),
      }))
      .filter(({ text }) => text.length >= 40)
      .filter(({ text }) => {
        const key = text.slice(0, 120)
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
      .slice(0, 36)
      .map(({ el, text }) => ({
        text,
        selector: buildSelector(el),
      }))
  }

  function collectImages(): string[] {
    const seen = new Set<string>()
    return Array.from(document.querySelectorAll('img'))
      .map((img) => img.currentSrc || img.src || img.getAttribute('data-src') || '')
      .filter((src) => src && !src.toLowerCase().includes('.svg'))
      .map((src) => {
        try {
          return new URL(src, window.location.href).href
        } catch {
          return ''
        }
      })
      .filter((src) => {
        if (!src || seen.has(src)) return false
        seen.add(src)
        return true
      })
      .slice(0, 25)
  }

  function collectMetadata(): Record<string, string> {
    const metadata: Record<string, string> = {}
    const metaSelectors: Record<string, string> = {
      canonical_url: 'link[rel="canonical"]',
      og_url: 'meta[property="og:url"]',
      og_title: 'meta[property="og:title"]',
      site_name: 'meta[property="og:site_name"]',
      description: 'meta[name="description"]',
    }
    for (const [key, selector] of Object.entries(metaSelectors)) {
      const el = document.querySelector(selector)
      const value = el instanceof HTMLMetaElement
        ? el.content
        : el instanceof HTMLLinkElement
          ? el.href
          : ''
      if (value) metadata[key] = sanitizeText(value).slice(0, 300)
    }
    return metadata
  }

  const elements = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR))
    .filter(isVisible)
    .slice(0, MAX_ELEMENTS)
    .map((el, index) => {
      const rect = el.getBoundingClientRect()
      const groundedId = `el_${String(index).padStart(3, '0')}`
      
      const item: any = {
        element_id: groundedId,
        type: el.tagName.toLowerCase(),
        text: sanitizeText((el.textContent || '').trim().slice(0, 100)),
        selector: buildSelector(el),
        visible: true,
        role: getAccessibilityRole(el),
        aria_label: el.getAttribute('aria-label') || undefined,
        accessibility_name: getAccessibilityName(el),
        state: getAccessibilityState(el),
        bounding_box: {
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        }
      }

      if (el instanceof HTMLInputElement) {
        item.input_type = el.type
        item.placeholder = el.placeholder || undefined
      }

      return item
    })

  const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
    .slice(0, 5)
    .map((h) => sanitizeText((h.textContent || '').trim()))
    .filter((text) => text.length > 0)

  return {
    url: window.location.href,
    title: document.title,
    metadata: collectMetadata(),
    interactive_elements: elements,
    content_blocks: collectContentBlocks(),
    headings,
    selected_text: '',
    visible_text: sanitizeText((document.body.innerText || '').slice(0, MAX_TEXT_LENGTH)),
    images: collectImages(),
  }
}
