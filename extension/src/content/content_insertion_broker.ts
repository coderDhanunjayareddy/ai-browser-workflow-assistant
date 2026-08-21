export type ContentInsertionKind =
  | 'local_file'
  | 'document'
  | 'image'
  | 'video'
  | 'audio'
  | 'camera'
  | 'contact'
  | 'poll'
  | 'event'
  | 'sticker'
  | 'gif'
  | 'emoji'

export type InsertionEffect =
  | 'preview_then_send'
  | 'selection_sends_immediately'
  | 'inserts_into_composer'
  | 'structured_draft'
  | 'device_capture'

export interface ContentInsertionRequest {
  request_id: string
  kind: ContentInsertionKind
  destination_origin: string
  destination_entity: string
  idempotency_key: string
  expected_effect: InsertionEffect
  approved_binding_id?: string | null
  confirmation_token?: string | null
}

export interface ApprovedContentBinding {
  binding_id: string
  kind: ContentInsertionKind
  filename: string | null
  mime_type: string | null
  size_bytes: number | null
  content_sha256: string | null
  destination_origin: string
  destination_entity: string
  idempotency_key: string
  approved_at_ms: number
  expires_at_ms: number
  synthetic: boolean
}

export interface ObservedInsertionCapability {
  kind: ContentInsertionKind
  effect: InsertionEffect
  selector: string
  backed_by_file_input: boolean
  accepted_mime_types: string[]
  multiple: boolean
}

export interface BrokerReservationState {
  chooser_count: number
  consumed: boolean
  effect_uncertain: boolean
  observed_origin: string
}

export interface BrokerDecision {
  allowed: boolean
  requires_confirmation: boolean
  reason: string
}

const FILE_BACKED_KINDS = new Set<ContentInsertionKind>([
  'local_file', 'document', 'image', 'video', 'audio',
])

const CONFIRM_BEFORE_SELECTION = new Set<InsertionEffect>([
  'selection_sends_immediately', 'device_capture',
])

function normalizedOrigin(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.origin : null
  } catch {
    return null
  }
}

function exactIdentity(left: string, right: string): boolean {
  return left.trim().normalize('NFKC') === right.trim().normalize('NFKC')
}

export function isFileBackedKind(kind: ContentInsertionKind): boolean {
  return FILE_BACKED_KINDS.has(kind)
}

export function validateContentInsertion(
  request: ContentInsertionRequest,
  binding: ApprovedContentBinding | null,
  capability: ObservedInsertionCapability,
  reservation: BrokerReservationState,
  nowMs: number,
): BrokerDecision {
  const requestedOrigin = normalizedOrigin(request.destination_origin)
  const observedOrigin = normalizedOrigin(reservation.observed_origin)
  if (!requestedOrigin || requestedOrigin !== observedOrigin) {
    return { allowed: false, requires_confirmation: false, reason: 'destination_origin_mismatch' }
  }
  if (!request.request_id || !request.idempotency_key || !request.destination_entity.trim()) {
    return { allowed: false, requires_confirmation: false, reason: 'insertion_contract_incomplete' }
  }
  if (request.kind !== capability.kind || request.expected_effect !== capability.effect) {
    return { allowed: false, requires_confirmation: false, reason: 'observed_capability_mismatch' }
  }
  if (reservation.consumed) {
    return { allowed: false, requires_confirmation: false, reason: 'insertion_reservation_consumed' }
  }
  if (reservation.effect_uncertain) {
    return { allowed: false, requires_confirmation: false, reason: 'uncertain_effect_blocks_retry' }
  }
  if (reservation.chooser_count > 0) {
    return { allowed: false, requires_confirmation: false, reason: 'second_chooser_blocked' }
  }
  const requiresConfirmation = CONFIRM_BEFORE_SELECTION.has(capability.effect)
  if (requiresConfirmation && !request.confirmation_token) {
    return { allowed: false, requires_confirmation: true, reason: 'confirmation_required_before_selection' }
  }
  if (!isFileBackedKind(request.kind)) {
    return { allowed: true, requires_confirmation: false, reason: 'typed_non_file_insertion_allowed' }
  }
  if (!capability.backed_by_file_input || !binding || request.approved_binding_id !== binding.binding_id) {
    return { allowed: false, requires_confirmation: false, reason: 'approved_file_binding_missing' }
  }
  if (!binding.synthetic) {
    return { allowed: false, requires_confirmation: false, reason: 'certification_requires_synthetic_content' }
  }
  if (binding.expires_at_ms <= nowMs || binding.approved_at_ms > nowMs) {
    return { allowed: false, requires_confirmation: false, reason: 'approved_file_binding_stale' }
  }
  if (
    normalizedOrigin(binding.destination_origin) !== requestedOrigin
    || !exactIdentity(binding.destination_entity, request.destination_entity)
    || binding.idempotency_key !== request.idempotency_key
    || binding.kind !== request.kind
  ) {
    return { allowed: false, requires_confirmation: false, reason: 'approved_file_binding_scope_mismatch' }
  }
  if (
    !binding.filename
    || !binding.mime_type
    || !binding.content_sha256
    || !/^[a-f0-9]{64}$/i.test(binding.content_sha256)
    || binding.size_bytes === null
    || binding.size_bytes <= 0
  ) {
    return { allowed: false, requires_confirmation: false, reason: 'approved_file_metadata_incomplete' }
  }
  if (
    capability.accepted_mime_types.length > 0
    && !capability.accepted_mime_types.some((accepted) => (
      accepted === binding.mime_type
      || (accepted.endsWith('/*') && binding.mime_type!.startsWith(accepted.slice(0, -1)))
    ))
  ) {
    return { allowed: false, requires_confirmation: false, reason: 'approved_file_mime_rejected' }
  }
  return { allowed: true, requires_confirmation: false, reason: 'approved_file_binding_verified' }
}

