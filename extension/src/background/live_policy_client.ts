import type { ExecutableAction, PolicyExecutionContext } from './service_worker_message_validation'
import type { CanonicalActionContract } from '../types'

export type LivePolicyDecision = {
  allowed: boolean
  policy_decision: string
  decision_reason: string
  decision_id: string
}

const denied = (reason: string, decisionId: string): LivePolicyDecision => ({
  allowed: false,
  policy_decision: 'block',
  decision_reason: reason,
  decision_id: decisionId,
})

export async function enforceLivePolicy(
  backendUrl: string,
  contract: CanonicalActionContract,
  tabUrl: string,
  context: PolicyExecutionContext,
  fetchImplementation: typeof fetch = fetch,
): Promise<LivePolicyDecision> {
  const action: ExecutableAction = contract.action
  const response = await fetchImplementation(`${backendUrl}/policy/enforce`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: context.session_id,
      origin: tabUrl,
      action,
      execution_contract: contract,
      provenance: context.provenance,
      origin_grant_id: context.origin_grant_id ?? null,
      confirmation_receipt_id: context.confirmation_receipt_id ?? null,
    }),
  }).catch(() => null)
  if (!response) return denied('policy_engine_unavailable', 'unavailable')
  if (!response.ok) return denied(`policy_engine_http_${response.status}`, 'http-error')

  const payload = await response.json().catch(() => null) as LivePolicyDecision | null
  if (
    !payload
    || typeof payload.allowed !== 'boolean'
    || typeof payload.policy_decision !== 'string'
    || typeof payload.decision_reason !== 'string'
    || typeof payload.decision_id !== 'string'
  ) {
    return denied('invalid_policy_engine_response', 'invalid-response')
  }
  return payload
}
