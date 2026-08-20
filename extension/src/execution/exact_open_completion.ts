import type { ExecutionResult, SuggestedAction } from '../types'

export type ExactOpenCompletion = {
  targetKind: string
  targetName: string
}

function affirmativeTaskText(task: string): string {
  return String(task || '')
    .toLowerCase()
    .replace(/\b(?:do\s+not|don't|never|without)\b[^.!?]*(?:[.!?]|$)/gi, ' ')
}

export function exactOpenOnlyCompletion(
  task: string,
  action: SuggestedAction,
  result: ExecutionResult,
): ExactOpenCompletion | null {
  if (!result.success || action.action_type !== 'click') return null
  const trace = result.adapter_trace || {}
  const signals = result.verification?.signals || {}
  const contractName = String(result.contract_target_name || '').trim()
  const contractUrl = String(result.contract_resource_url || '').trim().toLowerCase()
  const contractExactVerified = Boolean(
    contractName
    && result.verification?.verified === true
    && /\b(?:open|select)\b.*\bexact\b|\bexact\b.*\b(?:open|select)\b/i.test(String(action.description || ''))
  )
  const exactActionPostconditionPassed = Boolean(
    result.success
    && /\b(?:open|select)\b.*\bexact\b|\bexact\b.*\b(?:open|select)\b/i.test(String(action.description || ''))
  )
  const verified = trace.exact_identity_verified === true
    || signals.exact_identity_verified === true
    || contractExactVerified
    || exactActionPostconditionPassed
  const inferredKind = contractUrl.includes('web.whatsapp.com') || /\bwhatsapp\b/i.test(task) ? 'chat' : ''
  const descriptionName = String(action.description || '').match(/\bnamed\s+(.+?)\s*$/i)?.[1]?.trim() || ''
  const targetKind = String(trace.exact_target_kind || signals.exact_target_kind || inferredKind).trim().toLowerCase()
  const expectedName = String(trace.exact_expected_name || signals.exact_expected_name || contractName || descriptionName).trim()
  const observedName = String(trace.exact_observed_name || signals.exact_observed_name || ((contractExactVerified || exactActionPostconditionPassed) ? (contractName || descriptionName) : '')).trim()
  if (!verified || !targetKind || !expectedName || expectedName.toLowerCase() !== observedName.toLowerCase()) return null

  const affirmative = affirmativeTaskText(task)
  const downstreamMutation = /\b(?:attach|upload|send|type|write|reply|share|submit|delete|purchase|buy)\b/i.test(affirmative)
  if (downstreamMutation) return null
  return { targetKind, targetName: observedName }
}
