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
  const kind = targetKind(request.semantic_kind)
  const selectors = semanticIdentitySelectors(kind)
  const required = Boolean(expected)
  const observations: Array<{ name: string; selector: string }> = []
  for (const selector of selectors) {
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
      target_kind: kind,
      expected_name: request.expected_name,
      observed_name: exact.name,
      evidence_selector: exact.selector,
      reason: `exact_${kind}_identity_verified`,
    }
  }
  return {
    required,
    verified: false,
    target_kind: kind,
    expected_name: request.expected_name,
    observed_name: observations[0]?.name || null,
    evidence_selector: observations[0]?.selector || null,
    reason: required ? `exact_${kind}_identity_not_observed` : 'exact_identity_not_requested',
  }
}

function targetKind(semanticKind: string | null): ExactTargetVerificationResult['target_kind'] {
  const normalized = String(semanticKind || '').trim().toLowerCase()
  if (['chat', 'conversation', 'recipient', 'contact'].includes(normalized)) return 'chat'
  if (['thread', 'mail_thread', 'discussion'].includes(normalized)) return 'thread'
  if (['document', 'doc', 'page'].includes(normalized)) return 'document'
  if (['drive_item', 'file', 'folder', 'resource'].includes(normalized)) return 'drive_item'
  return 'generic'
}

function semanticIdentitySelectors(kind: ExactTargetVerificationResult['target_kind']): string[] {
  const headingSelectors = [
    'header [title]', 'header [aria-label]', 'header h1', 'header h2',
    '[role="banner"] [role="heading"]', '[role="main"] h1', '[role="main"] h2',
    '[role="main"] [role="heading"]', 'main h1', 'main h2',
  ]
  if (kind === 'document' || kind === 'drive_item') {
    return [
      'input[aria-label*="title" i]', 'input[title]', '[role="dialog"] [role="heading"]',
      ...headingSelectors,
    ]
  }
  return headingSelectors
}
