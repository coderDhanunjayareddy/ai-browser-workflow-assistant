import type {
  ActionGrounding,
  CanonicalActionContract,
  ExpectedEffectKind,
  PageContext,
  SuggestedAction,
} from '../types'

function expectedEffectKind(actionType: string): ExpectedEffectKind {
  if (actionType === 'navigate') return 'url_change'
  if (actionType === 'click') return 'target_state_change'
  if (actionType === 'fill') return 'value_change'
  if (['select_option', 'choose_date'].includes(actionType)) return 'selection_change'
  if (actionType === 'scroll') return 'viewport_change'
  if (['open_new_tab', 'switch_tab', 'focus_existing_tab', 'close_tab'].includes(actionType)) return 'tab_state_change'
  if (actionType === 'wait') return 'no_mutation'
  return 'page_state_change'
}

function targetKind(actionType: string): CanonicalActionContract['target_identity']['kind'] {
  if (actionType === 'navigate') return 'url'
  if (['open_new_tab', 'switch_tab', 'focus_existing_tab', 'close_tab'].includes(actionType)) return 'tab'
  if (!actionType || actionType === 'wait' || actionType === 'scroll') return 'page'
  return 'element'
}

export function buildCanonicalActionContract(
  action: SuggestedAction,
  context: PageContext,
  idempotencyKey: string,
): CanonicalActionContract {
  if (!Number.isInteger(context.tab_id) || Number(context.tab_id) < 0) {
    throw new Error('Cannot build action contract without an observed tab binding.')
  }
  const navigationAction = action.action_type === 'navigate' || action.action_type === 'open_new_tab'
  let observedOrigin: string
  let targetUrl: string | null = null
  let resourceUrl = context.url
  let resourceTitle = context.title
  try {
    const parsed = new URL(context.url)
    if (navigationAction) {
      if (!['http:', 'https:', 'chrome:', 'about:'].includes(parsed.protocol)) throw new Error('unsupported source protocol')
      if (!['http:', 'https:'].includes(parsed.protocol) && !['chrome://newtab/', 'about:blank'].includes(parsed.href)) {
        throw new Error('unsupported privileged source')
      }
      const destination = new URL(String(action.value || ''))
      if (!['http:', 'https:'].includes(destination.protocol)) throw new Error('unsupported destination protocol')
      observedOrigin = destination.origin
      targetUrl = destination.href
      resourceUrl = destination.href
      resourceTitle = ''
    } else {
      if (!['http:', 'https:'].includes(parsed.protocol)) throw new Error('unsupported protocol')
      observedOrigin = parsed.origin
    }
  } catch {
    throw new Error(navigationAction
      ? 'Cannot build navigation contract without an explicit safe http/https destination or from this privileged source.'
      : 'Cannot build action contract for a non-http/https origin.')
  }
  if (!idempotencyKey.trim()) throw new Error('Cannot build action contract without an idempotency key.')

  const rawGrounding = action.grounding as ActionGrounding | Record<string, never> | undefined
  const grounding = rawGrounding && Object.keys(rawGrounding).length === 0
    ? undefined
    : action.grounding
  const contractAction = grounding === action.grounding
    ? action
    : { ...action, grounding: undefined }
  const exactName = grounding?.accessibility_name?.trim() || null
  // Preserve the action's selector byte-for-byte in the immutable contract. Empty
  // selectors are valid for URL/tab actions; converting "" to null makes the live
  // policy gate correctly reject the contract as an identity mismatch.
  const selector = action.target_selector ?? ''
  if (action.action_type === 'click' && !selector.trim()) {
    throw new Error('Click contract requires an exact observed selector.')
  }

  return {
    schema_version: '1.0',
    dispatch_id: `${action.action_id}:${Date.now()}`,
    action: contractAction,
    target_identity: {
      kind: targetKind(action.action_type),
      selector,
      selector_id: grounding?.selector_id?.trim() || null,
      exact_name: exactName,
      role: grounding?.role?.trim() || null,
      semantic_kind: grounding?.semantic_kind?.trim() || null,
    },
    grounding_policy: {
      ordered_sources: ['stable_selector', 'accessibility_name', 'verified_screenshot'],
      accessibility_requires_exact_name: true,
      screenshot_coordinates_verified: grounding?.source === 'vision_region' && grounding?.screenshot_verified === true,
      screenshot_hash: grounding?.screenshot_hash?.trim() || null,
    },
    origin: {
      origin: observedOrigin,
      observed_url: context.url,
      target_url: targetUrl,
    },
    browser_binding: {
      tab_id: Number(context.tab_id),
      window_id: Number.isInteger(context.window_id) ? Number(context.window_id) : null,
      frame_id: grounding?.frame_id?.trim() || 'top',
    },
    resource_identity: {
      url: resourceUrl,
      title: resourceTitle,
    },
    expected_effect: {
      kind: expectedEffectKind(action.action_type),
      description: action.description || `${action.action_type} must produce a verified ${expectedEffectKind(action.action_type)}`,
    },
    safety_class: action.safety_level,
    idempotency_key: idempotencyKey,
  }
}

export function attachCanonicalContractEvidence<
  T extends { adapter_trace?: Record<string, string | number | boolean | null> },
>(result: T, contract: CanonicalActionContract, dispatchPath: string): T & {
  dispatch_id: string
  dispatch_path: string
  contract_schema_version: string
  contract_idempotency_key: string
  contract_target_name: string | null
  contract_resource_url: string
} {
  return {
    ...result,
    dispatch_id: contract.dispatch_id,
    dispatch_path: dispatchPath,
    contract_schema_version: contract.schema_version,
    contract_idempotency_key: contract.idempotency_key,
    contract_target_name: contract.target_identity.exact_name,
    contract_resource_url: contract.resource_identity.url,
    adapter_trace: {
      ...(result.adapter_trace || {}),
      canonical_contract: true,
      dispatch_id: contract.dispatch_id,
      dispatch_path: dispatchPath,
      target_selector_preserved: contract.target_identity.selector === contract.action.target_selector,
      target_name: contract.target_identity.exact_name,
      frame_id: contract.browser_binding.frame_id,
      expected_effect: contract.expected_effect.kind,
      safety_class: contract.safety_class,
      idempotency_key: contract.idempotency_key,
    },
  }
}
