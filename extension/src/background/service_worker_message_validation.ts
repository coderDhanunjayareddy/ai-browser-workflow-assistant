import type { CanonicalActionContract } from '../types'

export type ExecutableAction = {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
  grounding?: {
    source: 'dom_snapshot' | 'accessibility_snapshot' | 'vision_region'
    selector_id?: string | null
    frame_id?: string | null
    accessibility_name?: string | null
    role?: string | null
    semantic_kind?: string | null
    expected_url_path?: string | null
    screenshot_verified?: boolean
    screenshot_hash?: string | null
    bounding_box?: { x: number; y: number; width: number; height: number } | null
  }
  content_insertion?: {
    schema_version: 'content_insertion_request.v1'
    request_id: string
    kind: string
    expected_effect: string
    requires_bound_file: boolean
    destination_entity: string
    stage: string
    opens_native_chooser: boolean
    reveal_selector?: string | null
    requested_filename?: string | null
  } | null
  consequential_submission?: {
    schema_version: 'consequential_submission.v1'
    submission_id: string
    operation: 'send' | 'share' | 'submit' | 'post' | 'publish'
    destination_entity: string
    content_identity: string
    preview_required: boolean
    verification_mode: 'delivered_content_and_destination'
  } | null
}

export type PolicyProvenanceLabel = {
  source_type: 'user' | 'planner' | 'page' | 'tool' | 'system'
  source_id: string
  trust: 'trusted' | 'untrusted'
  labels: string[]
}

export type PolicyExecutionContext = {
  session_id: string
  provenance: PolicyProvenanceLabel[]
  origin_grant_id?: string | null
  confirmation_receipt_id?: string | null
}

export type MessageSenderDescriptor = {
  id?: string
  url?: string
  hasTab?: boolean
}

const MESSAGE_TYPES = new Set([
  'EXTRACT_CONTEXT', 'EXECUTE_ACTION', 'START_VOICE_CAPTURE', 'WAIT_FOR_TAB_LOAD',
  'WAIT_FOR_DOM_SETTLE', 'GET_TAB_WORKSPACE', 'GET_RUNTIME_IDENTITY',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isBoundedString(value: unknown, max: number, allowNull = false): boolean {
  return (allowNull && value === null) || (typeof value === 'string' && value.length <= max)
}

function isInternalExtensionSender(sender: MessageSenderDescriptor, runtimeId: string): boolean {
  if (sender.id !== runtimeId) return false
  const ownOrigin = `chrome-extension://${runtimeId}/`
  // A packaged extension page has the same trusted origin whether Chrome
  // renders it as a side panel, popup, or full tab (the latter is used by the
  // production validation harness). Content scripts retain the website URL,
  // so the origin check—not the presence of sender.tab—is the trust boundary.
  return typeof sender.url === 'string' && sender.url.startsWith(ownOrigin)
}

export function validateProvenance(value: unknown): value is PolicyProvenanceLabel[] {
  if (!Array.isArray(value) || value.length < 3 || value.length > 20) return false
  const allowedSources = new Set(['user', 'planner', 'page', 'tool', 'system'])
  const valid = value.every((item) => isRecord(item)
    && allowedSources.has(String(item.source_type))
    && isBoundedString(item.source_id, 300)
    && (item.trust === 'trusted' || item.trust === 'untrusted')
    && Array.isArray(item.labels)
    && item.labels.length <= 20
    && item.labels.every((label) => isBoundedString(label, 100)))
  if (!valid) return false
  return value.some((item) => item.source_type === 'user' && item.trust === 'trusted')
    && value.some((item) => item.source_type === 'planner' && item.trust === 'untrusted')
    && value.some((item) => item.source_type === 'page' && item.trust === 'untrusted')
}

export function validateExecutableAction(value: unknown): value is ExecutableAction {
  if (!isRecord(value)) return false
  if (!isBoundedString(value.action_id, 200) || !String(value.action_id).trim()) return false
  if (!isBoundedString(value.action_type, 100) || !String(value.action_type).trim()) return false
  if (!isBoundedString(value.target_selector, 4096, true)) return false
  if (!isBoundedString(value.value, 200_000, true)) return false
  if (value.description !== undefined && !isBoundedString(value.description, 5000)) return false
  if (value.reasoning !== undefined && !isBoundedString(value.reasoning, 5000)) return false
  if (value.safety_level !== undefined && !['safe', 'caution', 'danger'].includes(String(value.safety_level))) return false
  if (value.grounding !== undefined && !validateGrounding(value.grounding)) return false
  if (value.content_insertion !== undefined && value.content_insertion !== null) {
    if (!validateContentInsertionDeclaration(value.content_insertion)) return false
  }
  if (value.consequential_submission !== undefined && value.consequential_submission !== null) {
    if (!validateConsequentialSubmission(value.consequential_submission)) return false
  }
  if (['navigate', 'open_new_tab'].includes(String(value.action_type))) {
    if (typeof value.value !== 'string') return false
    try {
      const url = new URL(value.value)
      if (!['http:', 'https:'].includes(url.protocol)) return false
    } catch {
      return false
    }
  }
  return true
}

function validateContentInsertionDeclaration(value: unknown): boolean {
  if (!isRecord(value) || value.schema_version !== 'content_insertion_request.v1') return false
  const kinds = new Set(['local_file', 'document', 'image', 'video', 'audio', 'camera', 'contact', 'poll', 'event', 'sticker', 'gif', 'emoji'])
  const effects = new Set(['preview_then_send', 'selection_sends_immediately', 'inserts_into_composer', 'structured_draft', 'device_capture'])
  return kinds.has(String(value.kind))
    && effects.has(String(value.expected_effect))
    && typeof value.requires_bound_file === 'boolean'
    && isBoundedString(value.request_id, 200) && Boolean(String(value.request_id).trim())
    && isBoundedString(value.destination_entity, 500)
    && ['open_insertion_menu', 'select_bound_content'].includes(String(value.stage))
    && typeof value.opens_native_chooser === 'boolean'
    && (value.reveal_selector === undefined || value.reveal_selector === null || isBoundedString(value.reveal_selector, 2000))
    && (value.requested_filename === undefined || value.requested_filename === null || (
      isBoundedString(value.requested_filename, 500)
      && Boolean(String(value.requested_filename).trim())
      && !/[\\/]/.test(String(value.requested_filename))
    ))
}

function validateConsequentialSubmission(value: unknown): boolean {
  if (!isRecord(value) || value.schema_version !== 'consequential_submission.v1') return false
  return isBoundedString(value.submission_id, 300)
    && Boolean(String(value.submission_id).trim())
    && ['send', 'share', 'submit', 'post', 'publish'].includes(String(value.operation))
    && isBoundedString(value.destination_entity, 500)
    && Boolean(String(value.destination_entity).trim())
    && isBoundedString(value.content_identity, 1000)
    && Boolean(String(value.content_identity).trim())
    && value.preview_required === true
    && value.verification_mode === 'delivered_content_and_destination'
}

function validateGrounding(value: unknown): boolean {
  if (!isRecord(value) || !['dom_snapshot', 'accessibility_snapshot', 'vision_region'].includes(String(value.source))) return false
  if (value.selector_id !== undefined && !isBoundedString(value.selector_id, 300, true)) return false
  if (value.frame_id !== undefined && !isBoundedString(value.frame_id, 300, true)) return false
  if (value.accessibility_name !== undefined && !isBoundedString(value.accessibility_name, 500, true)) return false
  if (value.role !== undefined && !isBoundedString(value.role, 100, true)) return false
  if (value.semantic_kind !== undefined && !isBoundedString(value.semantic_kind, 200, true)) return false
  if (value.expected_url_path !== undefined) {
    if (!isBoundedString(value.expected_url_path, 2048, true)) return false
    if (value.expected_url_path !== null && value.expected_url_path !== '' && !String(value.expected_url_path).startsWith('/')) return false
  }
  if (value.screenshot_verified !== undefined && typeof value.screenshot_verified !== 'boolean') return false
  if (value.screenshot_hash !== undefined && !isBoundedString(value.screenshot_hash, 128, true)) return false
  if (value.bounding_box !== undefined && value.bounding_box !== null) {
    if (!isRecord(value.bounding_box)) return false
    const box = value.bounding_box
    const coordinates = ['x', 'y', 'width', 'height'].map((key) => box[key])
    if (!coordinates.every((item) => typeof item === 'number' && Number.isFinite(item))) return false
    if (Number(value.bounding_box.width) <= 0 || Number(value.bounding_box.height) <= 0) return false
    if (coordinates.some((item) => Math.abs(Number(item)) > 1_000_000)) return false
  }
  return true
}

export function validateCanonicalActionContract(value: unknown): value is CanonicalActionContract {
  if (!isRecord(value) || value.schema_version !== '1.0') return false
  if (!isBoundedString(value.dispatch_id, 400) || !String(value.dispatch_id).trim()) return false
  if (!validateExecutableAction(value.action)) return false
  if (!isRecord(value.target_identity) || !['element', 'url', 'tab', 'page'].includes(String(value.target_identity.kind))) return false
  if (!isBoundedString(value.target_identity.selector, 4096, true)) return false
  if (!isBoundedString(value.target_identity.selector_id, 300, true)) return false
  if (!isBoundedString(value.target_identity.exact_name, 500, true)) return false
  if (!isBoundedString(value.target_identity.role, 100, true)) return false
  if (!isBoundedString(value.target_identity.semantic_kind, 200, true)) return false
  if (value.target_identity.selector !== value.action.target_selector) return false
  if (!isRecord(value.grounding_policy)) return false
  if (!Array.isArray(value.grounding_policy.ordered_sources) || value.grounding_policy.ordered_sources.join('|') !== 'stable_selector|accessibility_name|verified_screenshot') return false
  if (value.grounding_policy.accessibility_requires_exact_name !== true) return false
  if (typeof value.grounding_policy.screenshot_coordinates_verified !== 'boolean') return false
  if (!isBoundedString(value.grounding_policy.screenshot_hash, 128, true)) return false
  if (value.grounding_policy.screenshot_coordinates_verified) {
    if (!isRecord(value.action.grounding) || value.action.grounding.source !== 'vision_region') return false
    if (value.action.grounding.screenshot_verified !== true || !String(value.grounding_policy.screenshot_hash || '').trim()) return false
  }

  if (!isRecord(value.origin) || !isBoundedString(value.origin.origin, 2048) || !isBoundedString(value.origin.observed_url, 8192) || !isBoundedString(value.origin.target_url, 8192, true)) return false
  const navigationAction = ['navigate', 'open_new_tab'].includes(String(value.action.action_type))
  try {
    const observed = new URL(String(value.origin.observed_url))
    if (navigationAction) {
      const target = new URL(String(value.origin.target_url || ''))
      const actionTarget = new URL(String(value.action.value || ''))
      if (!['http:', 'https:'].includes(target.protocol) || target.href !== actionTarget.href || target.origin !== value.origin.origin) return false
      if (!['http:', 'https:'].includes(observed.protocol) && !['chrome://newtab/', 'about:blank'].includes(observed.href)) return false
    } else if (!['http:', 'https:'].includes(observed.protocol) || observed.origin !== value.origin.origin || value.origin.target_url !== null) {
      return false
    }
  } catch {
    return false
  }

  if (!isRecord(value.browser_binding)) return false
  if (!Number.isInteger(value.browser_binding.tab_id) || Number(value.browser_binding.tab_id) < 0) return false
  if (value.browser_binding.window_id !== null && (!Number.isInteger(value.browser_binding.window_id) || Number(value.browser_binding.window_id) < 0)) return false
  if (!isBoundedString(value.browser_binding.frame_id, 300) || !String(value.browser_binding.frame_id).trim()) return false
  const actionFrame = isRecord(value.action.grounding) && typeof value.action.grounding.frame_id === 'string'
    ? value.action.grounding.frame_id.trim() || 'top'
    : 'top'
  if (value.browser_binding.frame_id !== actionFrame) return false

  if (!isRecord(value.resource_identity) || !isBoundedString(value.resource_identity.url, 8192) || !isBoundedString(value.resource_identity.title, 2000)) return false
  if (value.resource_identity.url !== (navigationAction ? value.origin.target_url : value.origin.observed_url)) return false
  if (!isRecord(value.expected_effect)) return false
  const effectKinds = new Set(['url_change', 'target_state_change', 'value_change', 'selection_change', 'viewport_change', 'tab_state_change', 'page_state_change', 'no_mutation'])
  if (!effectKinds.has(String(value.expected_effect.kind)) || !isBoundedString(value.expected_effect.description, 5000)) return false
  if (value.expected_effect.url_path !== undefined && !isBoundedString(value.expected_effect.url_path, 2048, true)) return false
  const actionExpectedPath = isRecord(value.action.grounding) ? value.action.grounding.expected_url_path ?? null : null
  if ((value.expected_effect.url_path ?? null) !== actionExpectedPath) return false
  if (!['safe', 'caution', 'danger'].includes(String(value.safety_class)) || value.safety_class !== value.action.safety_level) return false
  if (!isBoundedString(value.idempotency_key, 1000) || !String(value.idempotency_key).trim()) return false

  if (value.action.action_type === 'click' && !String(value.target_identity.selector || '').trim()) {
    return false
  }
  return true
}

export function validatePolicyContext(value: unknown): value is PolicyExecutionContext {
  return isRecord(value)
    && isBoundedString(value.session_id, 200)
    && Boolean(String(value.session_id).trim())
    && validateProvenance(value.provenance)
    && (value.origin_grant_id === undefined || isBoundedString(value.origin_grant_id, 200, true))
    && (value.confirmation_receipt_id === undefined || isBoundedString(value.confirmation_receipt_id, 200, true))
}

export function validateServiceWorkerMessage(
  message: unknown,
  sender: MessageSenderDescriptor,
  runtimeId: string,
): string | null {
  if (!isRecord(message) || typeof message.type !== 'string' || !MESSAGE_TYPES.has(message.type)) {
    return 'Unknown or malformed extension message.'
  }
  if (!isInternalExtensionSender(sender, runtimeId)) {
    return 'Service-worker messages are accepted only from this extension UI.'
  }
  if (message.type === 'EXECUTE_ACTION') {
    if (!validateCanonicalActionContract(message.contract)) return 'Execution message has an invalid canonical action contract.'
    if (!validatePolicyContext(message.policy_context)) return 'Execution message has an invalid policy context.'
  } else if (message.type === 'EXTRACT_CONTEXT') {
    if (message.tab_id !== undefined && (!Number.isInteger(message.tab_id) || Number(message.tab_id) < 0)) {
      return 'Context message has an invalid tab binding.'
    }
  } else if (message.type === 'START_VOICE_CAPTURE') {
    if (message.language !== undefined && (!isBoundedString(message.language, 32) || !/^[A-Za-z0-9-]*$/.test(String(message.language)))) {
      return 'Voice message has an invalid language code.'
    }
  }
  return null
}
