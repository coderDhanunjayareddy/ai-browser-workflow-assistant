export type ExecutableAction = {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
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
  'WAIT_FOR_DOM_SETTLE', 'GET_TAB_WORKSPACE',
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
  return typeof sender.url === 'string' && sender.url.startsWith(ownOrigin) && !sender.hasTab
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
    if (!Number.isInteger(message.tab_id) || Number(message.tab_id) < 0) return 'Execution message has an invalid tab binding.'
    if (!validateExecutableAction(message.action)) return 'Execution message has an invalid action contract.'
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
