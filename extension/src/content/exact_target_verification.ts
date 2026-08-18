export type ExactTargetVerificationRequest = {
  expected_name: string
  semantic_kind: string | null
  observed_origin: string
}

export type ExactTargetVerificationResult = {
  required: boolean
  verified: boolean
  target_kind: 'chat' | 'thread' | 'document' | 'drive_item' | 'generic'
  expected_name: string
  observed_name: string | null
  evidence_selector: string | null
  reason: string
}

export function verifyExactOpenedTarget(request: ExactTargetVerificationRequest): ExactTargetVerificationResult {
  const normalize = (value: string | null | undefined) => (value || '').replace(/\s+/g, ' ').trim().toLowerCase()
  const expected = normalize(request.expected_name)
  const host = window.location.hostname.toLowerCase()

  const app = host === 'web.whatsapp.com'
    ? { kind: 'chat' as const, selectors: ['header [title]', 'header [aria-label]', 'header span[dir="auto"]', '[data-testid="conversation-info-header"] [title]'] }
    : host === 'mail.google.com'
      ? { kind: 'thread' as const, selectors: ['[role="main"] h2', 'h2.hP', '[data-thread-perm-id] h2', '[role="main"] [role="heading"]'] }
      : host === 'docs.google.com'
        ? { kind: 'document' as const, selectors: ['input.docs-title-input', 'input[aria-label*="Document title" i]', '[aria-label*="Document title" i]'] }
        : host === 'drive.google.com'
          ? { kind: 'drive_item' as const, selectors: ['[role="dialog"] [role="heading"]', '[role="main"] [role="heading"]', '[role="main"] [aria-label]'] }
          : { kind: 'generic' as const, selectors: ['main h1', 'main h2', '[role="main"] [role="heading"]'] }

  const required = Boolean(expected) && app.kind !== 'generic'
  const observations: Array<{ name: string; selector: string }> = []
  for (const selector of app.selectors) {
    let elements: Element[] = []
    try { elements = Array.from(document.querySelectorAll(selector)) } catch { continue }
    for (const element of elements.slice(0, 30)) {
      const rect = element.getBoundingClientRect()
      const style = window.getComputedStyle(element)
      if (rect.width <= 0 || rect.height <= 0 || style.display === 'none' || style.visibility === 'hidden') continue
      const inputValue = element instanceof HTMLInputElement ? element.value : ''
      const name = (inputValue || element.getAttribute('title') || element.getAttribute('aria-label') || element.textContent || '').replace(/\s+/g, ' ').trim()
      if (name) observations.push({ name, selector })
    }
  }

  const exact = observations.find((item) => normalize(item.name) === expected)
  if (exact) {
    return {
      required,
      verified: true,
      target_kind: app.kind,
      expected_name: request.expected_name,
      observed_name: exact.name,
      evidence_selector: exact.selector,
      reason: `exact_${app.kind}_identity_verified`,
    }
  }
  return {
    required,
    verified: false,
    target_kind: app.kind,
    expected_name: request.expected_name,
    observed_name: observations[0]?.name || null,
    evidence_selector: observations[0]?.selector || null,
    reason: required ? `exact_${app.kind}_identity_not_observed` : 'exact_identity_not_required_for_origin',
  }
}
