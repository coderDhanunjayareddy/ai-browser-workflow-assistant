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
  expectedFrameId?: number
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
  observedFrameId?: number
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
