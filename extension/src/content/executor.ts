/**
 * executeAction — runs inside the live page via chrome.scripting.executeScript.
 *
 * CRITICAL: This function must be entirely self-contained.
 * executeScript serialises it with .toString() and runs it in the page context,
 * so NO module-level imports, constants, or helpers are available here.
 * Every helper must be defined inside this function body.
 *
 * The function is ASYNC so it can poll for elements that appear after animations
 * or network transitions (e.g. WhatsApp opening a chat after clicking a contact).
 */
export async function executeAction(action: {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
}): Promise<{ success: boolean; message: string; action_id: string }> {
  const { action_id, action_type, value, description } = action

  // Guard: AI sometimes pastes the entire formatted element line instead of just
  // the CSS selector (e.g. "input[text] | label=... | selector=input[title='...']").
  // Extract the real selector from "selector=<css>" if present, otherwise use as-is.
  let target_selector = action.target_selector
  if (target_selector && target_selector.includes('selector=')) {
    const m = target_selector.match(/selector=([^\s|]+)/)
    if (m) target_selector = m[1]
  }
  // Also strip anything after " | " if the AI included metadata in the selector field.
  if (target_selector && target_selector.includes(' | ')) {
    target_selector = target_selector.split(' | ')[0].trim()
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  function safeQuery(selector: string): Element | null {
    try {
      return document.querySelector(selector)
    } catch {
      return null // Invalid selector syntax — treat as not found.
    }
  }

  /**
   * Poll for a CSS selector until it appears in the DOM or the timeout expires.
   * Resolves with the element as soon as it is found, or null on timeout.
   * Default timeout: 10s — generous enough for slow networks and animations.
   */
  function waitForElement(selector: string, timeoutMs = 10_000): Promise<Element | null> {
    return new Promise((resolve) => {
      // Already present — fast path.
      const immediate = safeQuery(selector)
      if (immediate) { resolve(immediate); return }

      const deadline = Date.now() + timeoutMs
      const interval = setInterval(() => {
        const el = safeQuery(selector)
        if (el) {
          clearInterval(interval)
          resolve(el)
          return
        }
        if (Date.now() >= deadline) {
          clearInterval(interval)
          resolve(null)
        }
      }, 150)
    })
  }

  /**
   * Poll until any one of several selectors appears.
   * Returns the first match found, or null on timeout.
   */
  function waitForAny(selectors: string[], timeoutMs = 10_000): Promise<{ selector: string; el: Element } | null> {
    return new Promise((resolve) => {
      // Fast path.
      for (const sel of selectors) {
        const el = safeQuery(sel)
        if (el) { resolve({ selector: sel, el }); return }
      }

      const deadline = Date.now() + timeoutMs
      const interval = setInterval(() => {
        for (const sel of selectors) {
          const el = safeQuery(sel)
          if (el) { clearInterval(interval); resolve({ selector: sel, el }); return }
        }
        if (Date.now() >= deadline) { clearInterval(interval); resolve(null) }
      }, 150)
    })
  }

  // ── Action handlers ───────────────────────────────────────────────────────

  try {
    switch (action_type) {
      // ── click ─────────────────────────────────────────────────────────────
      case 'click': {
        if (!target_selector)
          return { success: false, message: 'No selector provided for click.', action_id }

        // Helper: simulate a real mouse click at the element's center coordinates.
        //
        // WHY coordinates matter: React attaches ONE delegated listener to the root.
        // When a click fires, React walks the fiber tree from event.target upward,
        // triggering synthetic onClick handlers. Dispatching with clientX/clientY=0
        // (the default) confuses some apps — with real coordinates it behaves like
        // an actual user click, triggering WhatsApp's chat-open handler correctly.
        //
        // We also use document.elementFromPoint() to find the topmost visible element
        // at the click position — that's the element React's delegation system starts
        // its fiber-tree walk from, giving the correct handler chain.
        function tryClick(
          candidate: Element,
          resolvedSelector: string,
        ): { success: boolean; message: string; action_id: string } | null {
          if (!(candidate instanceof HTMLElement)) return null

          candidate.scrollIntoView({ block: 'center', inline: 'center' })
          const r = candidate.getBoundingClientRect()
          if (r.width === 0 && r.height === 0) return null // not visible

          // Center of the element in viewport coordinates.
          const cx = Math.round(r.left + r.width  / 2)
          const cy = Math.round(r.top  + r.height / 2)

          // The topmost element at those coordinates is what a real mouse-click would hit.
          // elementFromPoint can return SVG/non-HTML nodes — fall back to candidate if so.
          const pointed = document.elementFromPoint(cx, cy)
          const topEl: HTMLElement = (pointed instanceof HTMLElement ? pointed : null) ?? candidate

          const opts: MouseEventInit & PointerEventInit = {
            bubbles: true, cancelable: true, view: window,
            clientX: cx, clientY: cy, screenX: cx, screenY: cy,
          }

          // Full sequence: pointer → mouse → click.
          topEl.dispatchEvent(new PointerEvent('pointerover',  opts))
          topEl.dispatchEvent(new PointerEvent('pointerdown',  opts))
          topEl.dispatchEvent(new MouseEvent('mousedown',      opts))
          topEl.dispatchEvent(new PointerEvent('pointerup',    opts))
          topEl.dispatchEvent(new MouseEvent('mouseup',        opts))
          topEl.dispatchEvent(new MouseEvent('click',          opts))
          topEl.click() // belt-and-suspenders for non-React handlers
          if (topEl !== candidate) {
            candidate.dispatchEvent(new MouseEvent('click', opts))
            candidate.click()
          }

          return { success: true, message: `Clicked at (${cx},${cy}): ${resolvedSelector}`, action_id }
        }

        // Detect CSS class-only selectors (e.g. ._2nY6U, .abc123).
        // These are app-internal hashes that change with every deploy — skip
        // the 10s wait and go straight to semantic fallback.
        const isClassOnlySelector = /^\.[a-zA-Z_-][\w-]*$/.test(target_selector.trim())

        // Primary: wait up to 3s for the exact selector (fast-fail so fallbacks kick in quickly).
        const el = isClassOnlySelector ? null : await waitForElement(target_selector, 3_000)
        const primary = el ? tryClick(el, target_selector) : null
        if (primary) return primary

        // Attribute-swap fallback: WhatsApp and similar apps sometimes use aria-label where
        // the AI guessed title= (or vice versa). Try swapping the attribute name.
        const attrSwap = target_selector
          .replace(/\[title=(["'][^"']+["'])\]/, '[aria-label=$1]')
          .replace(/\[aria-label=(["'][^"']+["'])\]/, '[title=$1]')
        if (attrSwap !== target_selector) {
          const swappedEl = await waitForElement(attrSwap, 2_000)
          const swappedResult = swappedEl ? tryClick(swappedEl, attrSwap) : null
          if (swappedResult) return swappedResult
        }

        // Semantic fallback: extract the human-readable value from the selector
        // (e.g. div[title='Search or start new chat'] → "Search or start new chat")
        // then search for any visible element whose aria-label / title / placeholder
        // contains the first keyword — handles renamed selectors across app updates.
        const attrValueMatch = target_selector.match(
          /\[(?:title|aria-label|placeholder|data-testid)=["']([^"']+)["']\]/
        )
        if (attrValueMatch) {
          const keyword = attrValueMatch[1].split(/\s+/)[0] // first word
          const semanticSelectors = [
            `[contenteditable="true"][aria-label*="${keyword}" i]`,
            `[contenteditable="true"][title*="${keyword}" i]`,
            `[role="searchbox"][aria-label*="${keyword}" i]`,
            `[aria-label*="${keyword}" i]`,
            `[title*="${keyword}" i]`,
            `[placeholder*="${keyword}" i]`,
            `[data-testid*="${keyword}" i]`,
          ]
          const match = await waitForAny(semanticSelectors, 5_000)
          if (match) {
            const result = tryClick(match.el, `${match.el.tagName.toLowerCase()}[semantic~="${keyword}"]`)
            if (result) return result
          }
        }

        // Text-content fallback: scan visible elements for one whose text/title
        // matches a keyword extracted from the action description.
        // Covers WhatsApp contacts, Gmail threads — any item not captured by selectors.
        if (description) {
          // Extract capitalised words (likely proper nouns: "Rahul", "Inbox", etc.)
          const nameTokens = description.match(/\b[A-Z][a-z]{1,30}\b/g) ?? []
          for (const token of nameTokens) {
            // Try title attribute match first (most precise — WhatsApp span[title="Rahul"])
            const byTitle = Array.from(document.querySelectorAll(`[title*="${token}" i]`))
            for (const candidate of byTitle) {
              const r = candidate.getBoundingClientRect()
              if (r.width > 0 && r.height > 0 && candidate instanceof HTMLElement) {
                const res = tryClick(candidate, `[title*="${token}" i]`)
                if (res) return res
              }
            }
            // Then try visible text content match (innerText contains the token)
            // Use numeric 1 for NodeFilter.SHOW_ELEMENT — safer in serialized executeScript context.
            const walker = document.createTreeWalker(document.body, 1 /* SHOW_ELEMENT */)
            let node = walker.nextNode()
            while (node) {
              const el = node as Element
              const rect = el.getBoundingClientRect()
              if (
                rect.width > 0 && rect.height > 0 &&
                el instanceof HTMLElement &&
                el.children.length <= 5 && // leaf-ish elements only
                (el.textContent || '').trim() === token
              ) {
                el.click()
                return { success: true, message: `Clicked by text content match "${token}": ${el.tagName}`, action_id }
              }
              node = walker.nextNode()
            }
          }
        }

        // Submit fallback: if there is a focused input/contenteditable, press Enter.
        // ONLY for real submit contexts — skip search boxes (Enter there doesn't open contacts/results).
        const active = document.activeElement
        const isTypeable = (e: Element | null): e is HTMLElement =>
          e instanceof HTMLInputElement ||
          e instanceof HTMLTextAreaElement ||
          (e instanceof HTMLElement && e.getAttribute('contenteditable') === 'true')

        const isSearchBox = (e: Element | null): boolean => {
          if (!e) return false
          if (e instanceof HTMLInputElement && e.type === 'search') return true
          const role = e.getAttribute('role')
          if (role === 'searchbox' || role === 'combobox') return true
          const label = e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('placeholder') || ''
          if (/search/i.test(label)) return true
          return false
        }

        // Do NOT press Enter on search boxes — it won't open a contact or navigate to a result.
        if (isTypeable(active) && !isSearchBox(active)) {
          const enterDown = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })
          const enterUp   = new KeyboardEvent('keyup',   { key: 'Enter', code: 'Enter', bubbles: true })
          active.dispatchEvent(enterDown)
          active.dispatchEvent(enterUp)
          const form = active.closest('form')
          if (form) form.requestSubmit()
          return {
            success: true,
            message: `Pressed Enter on focused element (${target_selector} not found — used keyboard submit)`,
            action_id,
          }
        }

        return { success: false, message: `Element not found: ${target_selector}`, action_id }
      }

      // ── fill ──────────────────────────────────────────────────────────────
      case 'fill': {
        if (!target_selector)
          return { success: false, message: 'No selector provided for fill.', action_id }

        // Helper: fill a resolved input element.
        function fillInput(
          inputEl: HTMLInputElement | HTMLTextAreaElement,
          fillValue: string,
          resolvedSelector: string,
        ): { success: boolean; message: string; action_id: string } {
          inputEl.focus()
          const proto = inputEl instanceof HTMLInputElement
            ? HTMLInputElement.prototype
            : HTMLTextAreaElement.prototype
          const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set
          if (nativeSetter) {
            nativeSetter.call(inputEl, fillValue)
          } else {
            inputEl.value = fillValue
          }
          inputEl.dispatchEvent(new Event('input', { bubbles: true }))
          inputEl.dispatchEvent(new Event('change', { bubbles: true }))
          return { success: true, message: `Filled "${fillValue}" into: ${resolvedSelector}`, action_id }
        }

        // Helper: fill a contenteditable element (WhatsApp, Gmail, Notion, etc.)
        function fillContentEditable(
          ceEl: HTMLElement,
          text: string,
          resolvedSelector: string,
        ): { success: boolean; message: string; action_id: string } {
          ceEl.focus()
          ceEl.textContent = ''
          // execCommand triggers framework listeners (React, Vue, Svelte).
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ;(document as any).execCommand('selectAll', false)
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          ;(document as any).execCommand('insertText', false, text)
          // Belt-and-suspenders: also fire input event.
          ceEl.dispatchEvent(new Event('input', { bubbles: true }))
          return { success: true, message: `Filled "${text}" into: ${resolvedSelector}`, action_id }
        }

        const fillValue = value ?? ''

        // Detect CSS class-only selectors — skip wait, go straight to semantic fallback.
        const isClassOnlySelector = /^\.[a-zA-Z_-][\w-]*$/.test(target_selector.trim())

        // Wait up to 3s for the exact selector (fast-fail so fallbacks kick in quickly).
        let el = isClassOnlySelector ? null : await waitForElement(target_selector, 3_000)

        // Attribute-swap fallback: try aria-label ↔ title swap before going semantic.
        if (!el) {
          const attrSwap = target_selector
            .replace(/\[title=(["'][^"']+["'])\]/, '[aria-label=$1]')
            .replace(/\[aria-label=(["'][^"']+["'])\]/, '[title=$1]')
          if (attrSwap !== target_selector) el = await waitForElement(attrSwap, 2_000)
        }

        // Primary path: regular input or textarea.
        if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
          return fillInput(el, fillValue, target_selector)
        }

        // Primary path: contenteditable div (WhatsApp, Gmail, etc.)
        if (el instanceof HTMLElement && el.getAttribute('contenteditable') === 'true') {
          return fillContentEditable(el, fillValue, target_selector)
        }

        // Semantic fallback: selector has an attribute value → search by keyword.
        const attrMatch = target_selector.match(
          /\[(?:title|aria-label|placeholder|data-testid)=["']([^"']+)["']\]/
        )
        if (attrMatch) {
          const keyword = attrMatch[1].split(/\s+/)[0]
          const match = await waitForAny([
            `[aria-label*="${keyword}" i]`,
            `[title*="${keyword}" i]`,
            `[placeholder*="${keyword}" i]`,
          ], 5_000)
          if (match) {
            if (match.el instanceof HTMLInputElement || match.el instanceof HTMLTextAreaElement)
              return fillInput(match.el, fillValue, `${target_selector} → semantic[${keyword}]`)
            if (match.el instanceof HTMLElement && match.el.getAttribute('contenteditable') === 'true')
              return fillContentEditable(match.el, fillValue, `${target_selector} → semantic[${keyword}]`)
          }
        }

        // Focused-element fallback: selector might point to a container that focused an input.
        const active = document.activeElement
        if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement) {
          return fillInput(active, fillValue, `${target_selector} → focused input`)
        }
        if (active instanceof HTMLElement && active.getAttribute('contenteditable') === 'true') {
          return fillContentEditable(active, fillValue, `${target_selector} → focused contenteditable`)
        }

        // No "first visible input" fallback — that causes dangerous wrong fills.
        return { success: false, message: `No fillable input found for: ${target_selector}`, action_id }
      }

      // ── scroll ────────────────────────────────────────────────────────────
      case 'scroll': {
        const direction = (value ?? 'down').toLowerCase()
        const delta = direction === 'up' ? -400 : 400

        if (!target_selector || target_selector === 'window') {
          window.scrollBy({ top: delta, behavior: 'smooth' })
          return { success: true, message: `Scrolled ${direction}.`, action_id }
        }

        const el = await waitForElement(target_selector, 5_000)
        if (!el)
          return { success: false, message: `Scroll target not found: ${target_selector}`, action_id }

        el.scrollBy({ top: delta, behavior: 'smooth' })
        return { success: true, message: `Scrolled ${direction} on: ${target_selector}`, action_id }
      }

      // ── navigate ──────────────────────────────────────────────────────────
      case 'navigate': {
        if (!value)
          return { success: false, message: 'No URL provided for navigate.', action_id }
        if (!value.startsWith('https://') && !value.startsWith('http://'))
          return { success: false, message: `Unsafe URL rejected (must be http/https): ${value}`, action_id }

        window.location.href = value
        // Navigation is async — we return success optimistically.
        return { success: true, message: `Navigating to: ${value}`, action_id }
      }

      // ── wait ───────────────────────────────────────────────────────────────
      case 'wait': {
        const parsed = Number(value ?? 2000)
        const waitMs = Number.isFinite(parsed)
          ? Math.max(500, Math.min(parsed, 10_000))
          : 2000
        await new Promise((resolve) => setTimeout(resolve, waitMs))
        return { success: true, message: `Waited ${waitMs}ms.`, action_id }
      }

      default:
        return { success: false, message: `Unknown action type: "${action_type}"`, action_id }
    }
  } catch (err) {
    return { success: false, message: `Runtime error: ${String(err)}`, action_id }
  }
}
