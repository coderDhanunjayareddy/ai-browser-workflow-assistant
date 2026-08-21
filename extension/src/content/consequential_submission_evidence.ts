import type { ConsequentialSubmissionDeclaration } from '../types'

export type SubmissionPageEvidence = {
  destination_observed: boolean
  content_observed: boolean
  preview_observed: boolean
  delivered_observed: boolean
  content_match_count: number
  evidence_source: 'explicit_adapter' | 'semantic_dom'
}

function normalized(value: unknown): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim().toLocaleLowerCase()
}

function visible(element: Element): boolean {
  const node = element as HTMLElement
  const style = window.getComputedStyle(node)
  const rect = node.getBoundingClientRect()
  return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0
}

/**
 * Runs inside the target page. Provider adapters can expose stable data
 * attributes; otherwise the broker uses bounded semantic DOM evidence. No
 * provider name or URL is part of the control flow.
 */
export function inspectConsequentialSubmission(
  declaration: ConsequentialSubmissionDeclaration,
): SubmissionPageEvidence {
  const destination = normalized(declaration.destination_entity)
  const content = normalized(declaration.content_identity)
  const explicitDestination = Array.from(document.querySelectorAll('[data-submission-destination]'))
    .some((node) => visible(node) && normalized(node.getAttribute('data-submission-destination')) === destination)
  const explicitContent = Array.from(document.querySelectorAll('[data-content-identity]'))
    .filter((node) => visible(node) && normalized(node.getAttribute('data-content-identity')) === content)
  const explicitDelivered = explicitContent.some((node) => {
    const state = normalized(node.getAttribute('data-delivery-state'))
    return state === 'delivered' || state === 'sent' || state === 'submitted' || state === 'published'
  })
  const text = normalized(document.body?.innerText)
  const destinationObserved = explicitDestination || (Boolean(destination) && text.includes(destination))
  const candidates = Array.from(document.querySelectorAll('body *')).filter((node) => {
    if (!visible(node)) return false
    const own = normalized(
      node.getAttribute('aria-label')
      || node.getAttribute('title')
      || node.getAttribute('data-content-identity')
      || (node.children.length === 0 ? node.textContent : ''),
    )
    return Boolean(content) && own.includes(content)
  })
  const previewObserved = explicitContent.some((node) => Boolean(node.closest('[role="dialog"], [data-submission-preview]')))
    || candidates.some((node) => Boolean(node.closest('[role="dialog"], [data-submission-preview]')))
  return {
    destination_observed: destinationObserved,
    content_observed: explicitContent.length > 0 || candidates.length > 0,
    preview_observed: previewObserved,
    delivered_observed: explicitDelivered,
    content_match_count: Math.max(explicitContent.length, candidates.length),
    evidence_source: explicitDestination || explicitContent.length > 0 ? 'explicit_adapter' : 'semantic_dom',
  }
}

export function verifyConsequentialDelivery(
  before: SubmissionPageEvidence,
  after: SubmissionPageEvidence,
): boolean {
  if (!after.destination_observed || !after.content_observed) return false
  if (after.delivered_observed) return true
  return before.preview_observed
    && !after.preview_observed
    && after.content_match_count >= before.content_match_count
}
