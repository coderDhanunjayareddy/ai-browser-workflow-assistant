import type { PageContext, InteractiveElement, ContentBlock } from '../types'

/**
 * Extracts a structured, size-limited snapshot of the current page.
 *
 * IMPORTANT: This function is passed to chrome.scripting.executeScript()
 * which serializes it via .toString() and runs it inside the active tab.
 * All constants and helpers MUST be defined inside this function —
 * module-level variables are not available in the serialized execution context.
 */
export function extractPageContext(): PageContext {
  // ── Constants ─────────────────────────────────────────────────────────────
  const INTERACTIVE_SELECTOR = [
    'button',
    'a[href]',
    'input:not([type="hidden"]):not([type="password"])',
    'select',
    'textarea',
    '[contenteditable="true"]',        // WhatsApp, Gmail, Notion, etc.
    '[role="textbox"]',                // ARIA text inputs
    '[role="searchbox"]',              // ARIA search inputs
    '[role="button"]:not(button)',     // Non-button elements acting as buttons
    '[role="listitem"]',               // WhatsApp contacts, chat rows in search results
    '[role="option"]',                 // Dropdown / combobox options
    '[role="menuitem"]',               // Context / action menu items
    '[role="row"]',                    // Gmail threads, table-based list rows
    '[role="tab"]',                    // Tab panels
    'span[title]:not([title=""])',     // WhatsApp contact name spans (title="Rahul")
  ].join(', ')
  const MAX_ELEMENTS = 120             // Keep prompt size manageable for Gemini
  const MAX_CONTENT_BLOCKS = 36
  const MAX_HEADINGS = 5
  const MAX_TEXT_LENGTH = 1000        // Visible text is rarely needed beyond a snippet

  // ── Helpers ───────────────────────────────────────────────────────────────

  function sanitizeText(text: string): string {
    return text
      .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[redacted-ssn]')
      .replace(/\b(?:\d{4}[\s-]?){3}\d{4}\b/g, '[redacted-card]')
  }

  function isSensitiveElement(el: Element): boolean {
    if (el instanceof HTMLInputElement && el.type === 'password') return true
    const autocomplete = (el.getAttribute('autocomplete') || '').toLowerCase()
    return ['cc-number', 'cc-csc', 'cc-cvv', 'cc-exp', 'cc-exp-month', 'cc-exp-year'].includes(autocomplete)
  }

  function buildSelector(el: Element): string {
    if (el.id) return `#${CSS.escape(el.id)}`

    const testId = el.getAttribute('data-testid')
    if (testId) return `[data-testid="${testId}"]`

    if (el.tagName.toLowerCase() === 'a') {
      const href = el.getAttribute('href')
      if (href && !href.startsWith('javascript:')) {
        const amznMatch = href.match(/(?:\/dp\/|\/gp\/product\/)([A-Z0-9]{10})/i)
        if (amznMatch) {
          return `a[href*="${amznMatch[1]}"]`
        }
        const fkMatch = href.match(/[?&]pid=([A-Z0-9]{16})/i)
        if (fkMatch) {
          return `a[href*="${fkMatch[1]}"]`
        }
        if (href.length < 120) {
          return `a[href="${href}"]`
        }
      }
    }

    const ariaLabel = el.getAttribute('aria-label')
    if (ariaLabel) return `${el.tagName.toLowerCase()}[aria-label="${ariaLabel}"]`

    const title = el.getAttribute('title')
    if (title) return `${el.tagName.toLowerCase()}[title="${title}"]`

    const placeholder = el.getAttribute('placeholder')
    if (placeholder) return `${el.tagName.toLowerCase()}[placeholder="${placeholder}"]`

    const name = el.getAttribute('name')
    if (name) return `${el.tagName.toLowerCase()}[name="${name}"]`

    const parts: string[] = []
    let current: Element | null = el
    let depth = 0

    while (current && current.tagName !== 'BODY' && depth < 5) {
      if (current.id) {
        parts.unshift(`#${CSS.escape(current.id)}`)
        break
      }

      const testId = current.getAttribute('data-testid')
      if (testId) {
        parts.unshift(`[data-testid="${testId}"]`)
        break
      }

      const ariaLabel = current.getAttribute('aria-label')
      if (ariaLabel) {
        parts.unshift(`${current.tagName.toLowerCase()}[aria-label="${ariaLabel}"]`)
        break
      }

      let part = current.tagName.toLowerCase()
      const role = current.getAttribute('role')
      if (role) {
        part += `[role="${role}"]`
      }
      if (current.getAttribute('contenteditable') === 'true') {
        part += '[contenteditable="true"]'
      }

      const parent = current.parentElement
      if (parent) {
        const siblings = Array.from(parent.children).filter(
          (c) => c.tagName === current!.tagName
        )
        if (siblings.length > 1) {
          part += `:nth-of-type(${siblings.indexOf(current) + 1})`
        }
      }
      parts.unshift(part)
      current = current.parentElement
      depth++
    }

    return parts.join(' > ')
  }

  function isVisible(el: Element): boolean {
    const rect = el.getBoundingClientRect()
    const style = window.getComputedStyle(el)
    return (
      rect.width > 0 &&
      rect.height > 0 &&
      style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      style.opacity !== '0'
    )
  }

  function getElementText(el: Element): string {
    if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) {
      return el.placeholder || el.getAttribute('aria-label') || el.getAttribute('name') || ''
    }
    // Prefer explicit label attributes (most reliable for AI selector generation)
    const label = el.getAttribute('aria-label') || el.getAttribute('title') ||
                  el.getAttribute('placeholder') || el.getAttribute('data-placeholder')
    if (label) return sanitizeText(label)
    // For listitem/row/option roles: use inner text (contact name, thread subject, etc.)
    return sanitizeText((el.textContent || '').trim()).slice(0, 80)
  }

  function getMetaContent(selector: string): string {
    const el = document.querySelector(selector)
    if (el instanceof HTMLMetaElement) return sanitizeText(el.content || '').trim()
    if (el instanceof HTMLLinkElement) return sanitizeText(el.href || '').trim()
    return ''
  }

  function firstText(selectors: string[]): string {
    for (const selector of selectors) {
      const el = document.querySelector(selector)
      const text = sanitizeText((el?.textContent || '').trim())
      if (text) return text
    }
    return ''
  }

  function collectMetadata(): Record<string, string> {
    const metadata: Record<string, string> = {}

    const canonicalUrl = getMetaContent('link[rel="canonical"]')
    const ogUrl = getMetaContent('meta[property="og:url"]')
    const ogTitle = getMetaContent('meta[property="og:title"]')
    const ogSiteName = getMetaContent('meta[property="og:site_name"]')
    const author = getMetaContent('meta[name="author"]')
    const articleAuthor = getMetaContent('meta[property="article:author"]')

    if (canonicalUrl) metadata.canonical_url = canonicalUrl
    if (ogUrl) metadata.og_url = ogUrl
    if (ogTitle) metadata.og_title = ogTitle
    if (ogSiteName) metadata.site_name = ogSiteName
    if (author) metadata.author = author
    if (articleAuthor) metadata.article_author = articleAuthor

    if (location.hostname.includes('youtube.com') && location.pathname === '/watch') {
      const videoTitle = firstText([
        'h1 yt-formatted-string',
        'h1.title',
        'h1',
      ]) || ogTitle || document.title.replace(/\s+-\s+YouTube$/, '')

      const channelName = firstText([
        'ytd-video-owner-renderer #channel-name a',
        '#owner #channel-name a',
        '#upload-info #channel-name a',
        'ytd-channel-name a',
      ])

      if (videoTitle) metadata.video_title = videoTitle
      if (channelName) metadata.channel_name = channelName
      metadata.video_url = canonicalUrl || ogUrl || location.href
    }

    return metadata
  }

  function scoreElement(el: Element): number {
    let score = 0
    const tag = el.tagName.toLowerCase()
    const role = el.getAttribute('role') || ''
    const text = getElementText(el).toLowerCase()
    const href = el.getAttribute('href') || ''
    const attrs = [
      el.getAttribute('aria-label') || '',
      el.getAttribute('placeholder') || '',
      el.getAttribute('title') || '',
      el.getAttribute('name') || '',
      el.getAttribute('data-testid') || '',
      href,
    ].join(' ').toLowerCase()

    if (document.activeElement === el) score += 100
    if (el.closest('[role="dialog"], dialog, [aria-modal="true"]')) score += 80
    if (tag === 'input' || tag === 'textarea' || tag === 'select') score += 50
    if (role === 'textbox' || role === 'searchbox' || role === 'combobox') score += 50
    if (el.getAttribute('contenteditable') === 'true') score += 45
    if (tag === 'button' || role === 'button') score += 25
    if (/(to|recipient|subject|body|message|compose|send|search|title|name|email|link|url|apply|save)/i.test(`${text} ${attrs}`)) score += 35
    if (/(cart|buy|add|product|item|checkout|shop|price|view|select|review|rating|star|booking|reserve)/i.test(`${text} ${attrs}`)) score += 50
    if (/(add to cart|add-to-cart|buy now|add to basket)/i.test(text)) score += 100

    // Boost potential e-commerce product detail links
    if (tag === 'a' && href) {
      if (/(?:\/dp\/|\/gp\/|\/p\/|\/pd\/|\/product\/|\/item\/|\/goods\/|\/shop\/)/i.test(href)) {
        score += 60
      }
    }

    // Penalize links inside headers, footers or navigation elements
    if (tag === 'a' && el.closest('header, footer, nav, #nav-belt, #nav-main, #navFooter, #footer, .footer, .nav-footer')) {
      score -= 80
    }

    // Boost elements containing price or rating indicators
    if (/[₹$€£]\s?\d|rs\.?\s?\d|\b\d{3,}\b/i.test(text)) {
      score += 35
    }
    if (/\b\d(?:\.\d)?\s*(?:★|stars?|rating|reviews?)\b/i.test(text)) {
      score += 30
    }

    const rect = el.getBoundingClientRect()
    if (rect.top >= 0 && rect.left >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth) score += 10

    return score
  }

  function scoreContentBlock(el: Element, text: string): number {
    const lower = text.toLowerCase()
    let score = 0
    if (text.length >= 40) score += 10
    if (text.length >= 120) score += 10
    if (/[₹$€£]\s?\d|rs\.?\s?\d|\b\d{3,}\b/i.test(text)) score += 35
    if (/\b\d(?:\.\d)?\s*(?:★|stars?|rating)\b/i.test(text)) score += 25
    if (/\b(add to cart|buy now|delivery|discount|reviews?|company|salary|hotel|flight|restaurant|repo|stars?)\b/i.test(lower)) score += 20
    if (el.matches('article, li, [role="listitem"], [role="row"], [data-component-type], [data-testid]')) score += 20
    const rect = el.getBoundingClientRect()
    if (rect.top >= 0 && rect.top <= window.innerHeight * 1.5) score += 10
    return score
  }

  function collectContentBlocks(): ContentBlock[] {
    const candidates = Array.from(document.querySelectorAll([
      'article',
      'li',
      '[role="listitem"]',
      '[role="row"]',
      '[data-component-type]',
      '[data-testid]',
      'section',
      'a[href]',
      'div',
    ].join(', ')))

    const seen = new Set<string>()

    return candidates
      .filter((el) => !isSensitiveElement(el))
      .filter(isVisible)
      .map((el, index) => {
        const text = sanitizeText((el.textContent || '').replace(/\s+/g, ' ').trim()).slice(0, 500)
        return { el, index, text, score: scoreContentBlock(el, text) }
      })
      .filter((item) => item.text.length >= 40 && item.score >= 25)
      .filter((item) => item.el.children.length <= 25)
      .filter((item) => {
        const key = item.text.slice(0, 120)
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
      .sort((a, b) => b.score - a.score || a.index - b.index)
      .slice(0, MAX_CONTENT_BLOCKS)
      .map(({ el, text }) => ({
        text,
        selector: buildSelector(el),
      }))
  }

  function collectImages(): string[] {
    const images: { src: string; area: number }[] = []
    const seen = new Set<string>()
    const imgElements = Array.from(document.querySelectorAll('img'))
    for (const img of imgElements) {
      // Prioritize data-src, lazy-loaded sources, and currentSrc (actual resolved srcset)
      let src = img.getAttribute('data-src') || 
                img.getAttribute('data-lazy-src') || 
                img.getAttribute('data-actual-src') || 
                img.getAttribute('data-original') || 
                img.getAttribute('srcset') ||
                img.currentSrc ||
                img.src;
                
      if (!src) continue

      // Exclude SVGs (both inline base64 data URLs and standard URLs)
      const isSvg = src.includes('image/svg+xml') || 
                    src.split('?')[0].toLowerCase().endsWith('.svg') ||
                    src.includes('.svg/');
      if (isSvg) continue

      // If the selected src is a base64 transparent placeholder gif, try falling back to standard src or other attributes
      if (src.startsWith('data:image/gif') || src.includes('placeholder') || src.includes('pixel') || src.includes('blank.gif')) {
        src = img.currentSrc || img.src || img.getAttribute('src') || '';
      }
      
      if (!src) continue

      // Exclude SVGs again after fallback
      if (src.includes('image/svg+xml') || src.split('?')[0].toLowerCase().endsWith('.svg') || src.includes('.svg/')) {
        continue
      }

      // If srcset, take the first URL
      if (src.includes(',')) {
        const parts = src.split(',')
        if (parts.length > 0) {
          const firstPart = parts[0].trim().split(/\s+/)[0]
          if (firstPart) src = firstPart
        }
      }
      
      // Resolve relative URLs using the browser's URL constructor
      try {
        src = new URL(src, window.location.href).href
      } catch {
        continue
      }
      
      if (!src.startsWith('http') && !src.startsWith('data:image')) continue
      
      const rect = img.getBoundingClientRect()
      const width = img.naturalWidth || rect.width
      const height = img.naturalHeight || rect.height
      
      // Filter out tiny tracker pixels or icon images
      if (width > 0 && width < 80) continue
      if (height > 0 && height < 80) continue
      
      // Avoid duplicates
      if (seen.has(src)) continue
      seen.add(src)
      
      const area = width * height
      images.push({ src, area })
    }

    // Sort images by area descending (largest first)
    images.sort((a, b) => b.area - a.area)

    // Return top 25 images
    return images.slice(0, 25).map(item => item.src)
  }

  // ── Extraction ────────────────────────────────────────────────────────────

  const interactiveElements: InteractiveElement[] = Array.from(
    document.querySelectorAll(INTERACTIVE_SELECTOR)
  )
    .filter((el) => !isSensitiveElement(el))
    .filter(isVisible)
    .map((el, index) => ({ el, index, score: scoreElement(el) }))
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, MAX_ELEMENTS)
    .map(({ el }) => el)
    .map((el): InteractiveElement => {
      const base: InteractiveElement = {
        type: el.tagName.toLowerCase(),
        text: getElementText(el),
        selector: buildSelector(el),
        visible: true,
      }
      if (el instanceof HTMLInputElement) {
        return { ...base, input_type: el.type, placeholder: el.placeholder || undefined }
      }
      return base
    })

  const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
    .slice(0, MAX_HEADINGS)
    .map((h) => sanitizeText((h.textContent || '').trim()))
    .filter((text) => text.length > 0)

  const selectedText = sanitizeText(window.getSelection()?.toString() || '').trim().slice(0, 500)
  const visibleText = sanitizeText(document.body.innerText || '').slice(0, MAX_TEXT_LENGTH)

  return {
    url: window.location.href,
    title: document.title,
    metadata: collectMetadata(),
    interactive_elements: interactiveElements,
    content_blocks: collectContentBlocks(),
    headings,
    selected_text: selectedText,
    visible_text: visibleText,
    images: collectImages(),
  }
}
