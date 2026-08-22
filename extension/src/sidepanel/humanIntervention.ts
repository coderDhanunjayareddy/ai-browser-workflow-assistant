import type { BackendHumanInterventionRequest, PageContext } from '../types'

export const HUMAN_INTERVENTION_REQUEST_SCHEMA = 'human_intervention.request.v1'
export const HUMAN_INTERVENTION_RESUME_SCHEMA = 'human_intervention.resume.v1'

export type HumanInterventionKind =
  | 'authentication'
  | 'mfa'
  | 'captcha'
  | 'privileged_ui'
  | 'sensitive_input'
  | 'consequential_confirmation'
  | 'identity_ambiguity'
  | 'external_authorization'
  | 'external_blocker'

export type SecretHandling = 'none' | 'direct_browser_only'

export type ResumeEvidenceKind =
  | 'page_state'
  | 'url_and_origin'
  | 'authenticated_identity'
  | 'dialog_closed'
  | 'challenge_cleared'
  | 'explicit_user_confirmation'

export interface HumanInterventionCheckpoint {
  schemaVersion: typeof HUMAN_INTERVENTION_REQUEST_SCHEMA
  requestId: string
  missionId: string
  blockedObjectiveId: string
  kind: HumanInterventionKind
  message: string
  requestedUserAction: string
  secretHandling: SecretHandling
  checkpointRef: string
  completedObjectiveIds: string[]
  pendingObjectiveIds: string[]
  expectedEvidence: ResumeEvidenceKind[]
  expectedOrigin?: string
  expectedTabId?: number
  expectedFrameId?: string
  requestBudget: number
  unchangedGateAttempts: number
  state: 'awaiting_user' | 'ready_to_verify' | 'resumed' | 'expired'
  createdAt: number
  updatedAt: number
}

export interface HumanInterventionResumeEvidence {
  schemaVersion: typeof HUMAN_INTERVENTION_RESUME_SCHEMA
  requestId: string
  missionId: string
  resumedObjectiveId: string
  evidenceKinds: ResumeEvidenceKind[]
  observedOrigin?: string
  observedTabId?: number
  observedFrameId?: string
  duplicateDispatchPrevented: true
  verifiedAt: number
}

const DIRECT_BROWSER_KINDS = new Set<HumanInterventionKind>([
  'authentication', 'mfa', 'captcha', 'sensitive_input',
])

export function createHumanInterventionCheckpoint(
  input: Omit<HumanInterventionCheckpoint, 'schemaVersion' | 'state' | 'createdAt' | 'updatedAt'>,
  now = Date.now(),
): HumanInterventionCheckpoint {
  const completed = new Set(input.completedObjectiveIds)
  if (input.pendingObjectiveIds.some((id) => completed.has(id))) {
    throw new Error('Completed and pending objectives must be disjoint.')
  }
  if (completed.has(input.blockedObjectiveId)) {
    throw new Error('The blocked objective cannot already be complete.')
  }
  if (DIRECT_BROWSER_KINDS.has(input.kind) && input.secretHandling !== 'direct_browser_only') {
    throw new Error('Authentication, challenge, and sensitive input must be entered directly in the browser.')
  }
  if (input.requestBudget < 1) throw new Error('Intervention request budget must be at least one.')
  return {
    ...input,
    schemaVersion: HUMAN_INTERVENTION_REQUEST_SCHEMA,
    state: 'awaiting_user',
    createdAt: now,
    updatedAt: now,
  }
}

export function verifyHumanInterventionResume(
  checkpoint: HumanInterventionCheckpoint,
  observed: Omit<HumanInterventionResumeEvidence, 'schemaVersion' | 'requestId' | 'missionId' | 'resumedObjectiveId' | 'duplicateDispatchPrevented' | 'verifiedAt'>,
  now = Date.now(),
): HumanInterventionResumeEvidence | null {
  if (checkpoint.state === 'resumed' || checkpoint.state === 'expired') return null
  if (checkpoint.unchangedGateAttempts >= checkpoint.requestBudget) return null
  if (checkpoint.expectedOrigin && checkpoint.expectedOrigin !== observed.observedOrigin) return null
  if (checkpoint.expectedTabId !== undefined && checkpoint.expectedTabId !== observed.observedTabId) return null
  if (checkpoint.expectedFrameId !== undefined && checkpoint.expectedFrameId !== observed.observedFrameId) return null
  const evidence = new Set(observed.evidenceKinds)
  if (!checkpoint.expectedEvidence.every((kind) => evidence.has(kind))) return null
  return {
    ...observed,
    schemaVersion: HUMAN_INTERVENTION_RESUME_SCHEMA,
    requestId: checkpoint.requestId,
    missionId: checkpoint.missionId,
    resumedObjectiveId: checkpoint.blockedObjectiveId,
    duplicateDispatchPrevented: true,
    verifiedAt: now,
  }
}

export function sanitizeHumanInterventionCheckpoint(
  checkpoint: HumanInterventionCheckpoint,
): HumanInterventionCheckpoint {
  return {
    ...checkpoint,
    message: redactSensitiveText(checkpoint.message),
    requestedUserAction: redactSensitiveText(checkpoint.requestedUserAction),
  }
}

function redactSensitiveText(value: string): string {
  return value.replace(
    /\b(password|passcode|otp|one[- ]?time code|verification code|api key|access token|secret)\b\s*[:=]\s*\S+/gi,
    '$1: [omitted]',
  )
}

const BACKEND_EVIDENCE_MAP: Record<BackendHumanInterventionRequest['resume_condition']['evidence_kind'], ResumeEvidenceKind> = {
  url_matches: 'url_and_origin',
  origin_matches: 'url_and_origin',
  element_visible: 'page_state',
  element_absent: 'page_state',
  authenticated_state: 'authenticated_identity',
  authorization_granted: 'page_state',
  dialog_closed: 'dialog_closed',
  user_acknowledged: 'explicit_user_confirmation',
}

export function checkpointFromBackend(
  request: BackendHumanInterventionRequest,
  now = Date.now(),
): HumanInterventionCheckpoint {
  if (request.schema_version !== HUMAN_INTERVENTION_REQUEST_SCHEMA) {
    throw new Error('Unsupported human-intervention contract version.')
  }
  return createHumanInterventionCheckpoint({
    requestId: request.intervention_id,
    missionId: request.mission_id,
    blockedObjectiveId: request.objective_id,
    kind: request.kind,
    message: request.user_message,
    requestedUserAction: request.requested_action,
    secretHandling: request.secret_handling === 'direct_browser_only' ? 'direct_browser_only' : 'none',
    checkpointRef: request.checkpoint_ref,
    completedObjectiveIds: request.completed_objective_ids,
    pendingObjectiveIds: request.pending_objective_ids,
    expectedEvidence: request.kind === 'captcha'
      ? ['challenge_cleared']
      : [BACKEND_EVIDENCE_MAP[request.resume_condition.evidence_kind]],
    expectedOrigin: request.resume_condition.observed_origin,
    expectedTabId: request.resume_condition.tab_id,
    expectedFrameId: request.resume_condition.frame_id,
    requestBudget: request.request_budget,
    unchangedGateAttempts: request.unchanged_gate_attempts,
  }, now)
}

function observedOrigin(url: string): string | undefined {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.origin : undefined
  } catch {
    return undefined
  }
}

const AUTHENTICATION_GATE = /\b(sign[ -]?in|log[ -]?in|scan (?:the )?qr|qr code|authenticate|authentication required|verify (?:your )?identity|otp|passcode|verification code|one[- ]time (?:code|password)|two[- ]factor|multi[- ]factor)\b/i
const CHALLENGE_GATE = /\b(captcha|recaptcha|hcaptcha|verify you are human|security challenge|challenge required)\b/i

function contextHasGate(context: PageContext, pattern: RegExp): boolean {
  if (pattern.test(`${context.title}\n${context.headings.join('\n')}\n${context.visible_text.slice(0, 4000)}`)) return true
  return context.interactive_elements.some((element) => pattern.test([
    element.text, element.placeholder, element.aria_label, element.accessibility_name,
    element.input_type, element.role,
  ].filter(Boolean).join(' ')))
}

export function observeInterventionResume(
  checkpoint: HumanInterventionCheckpoint,
  context: PageContext,
): Omit<HumanInterventionResumeEvidence, 'schemaVersion' | 'requestId' | 'missionId' | 'resumedObjectiveId' | 'duplicateDispatchPrevented' | 'verifiedAt'> {
  const evidenceKinds: ResumeEvidenceKind[] = []
  const origin = observedOrigin(context.url)
  const sameOrigin = !checkpoint.expectedOrigin || checkpoint.expectedOrigin === origin
  if (sameOrigin) evidenceKinds.push('url_and_origin', 'page_state')
  if (checkpoint.kind === 'authentication' || checkpoint.kind === 'mfa') {
    if (sameOrigin && !contextHasGate(context, AUTHENTICATION_GATE)) evidenceKinds.push('authenticated_identity')
  }
  if (checkpoint.kind === 'captcha') {
    if (sameOrigin && !contextHasGate(context, CHALLENGE_GATE)) evidenceKinds.push('challenge_cleared')
  }
  if (checkpoint.kind === 'privileged_ui' && sameOrigin) evidenceKinds.push('dialog_closed')
  return {
    evidenceKinds: [...new Set(evidenceKinds)],
    observedOrigin: origin,
    observedTabId: context.tab_id,
    observedFrameId: 'top',
  }
}
