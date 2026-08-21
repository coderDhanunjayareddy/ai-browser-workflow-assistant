import type { ExecutionResult, SuggestedAction } from '../types'
import type { WorkflowState } from './hooks/useWorkflow'

export const DURABLE_WORKFLOW_LEDGER_KEY = 'phase3_durable_workflow_ledger'
export const DURABLE_LEDGER_SCHEMA_VERSION = 1
export const MAX_REVERSIBLE_ATTEMPTS = 2

export type DurableExecutionStatus = 'in_flight' | 'succeeded' | 'failed' | 'uncertain'
export type DurableApprovalStatus = 'none' | 'awaiting_user' | 'approved_manual' | 'approved_auto' | 'policy_paused'

export interface DurableExecutionRecord {
  key: string
  actionId: string
  actionType: string
  tabId: number
  status: DurableExecutionStatus
  attempts: number
  retryable: boolean
  startedAt: number
  updatedAt: number
  result?: ExecutionResult
}

export interface DurableWorkflowLedger {
  schemaVersion: number
  sessionId: string
  revision: number
  updatedAt: number
  workflow: WorkflowState
  approval: {
    status: DurableApprovalStatus
    actionId: string | null
    updatedAt: number
  }
  executions: Record<string, DurableExecutionRecord>
}

const REVERSIBLE_ACTIONS = new Set([
  'fill', 'hover', 'scroll', 'select_option', 'wait',
])

const SAFE_AUTONOMOUS_NAVIGATION = new Set([
  'navigate', 'open_new_tab', 'switch_tab', 'focus_existing_tab',
])

export function isLowRiskReversibleAction(action: SuggestedAction): boolean {
  return action.safety_level === 'safe' && REVERSIBLE_ACTIONS.has(action.action_type)
}

export function isSafeAutonomousNavigation(action: SuggestedAction): boolean {
  if (action.safety_level !== 'safe' || !SAFE_AUTONOMOUS_NAVIGATION.has(action.action_type)) return false
  if (action.action_type === 'switch_tab' || action.action_type === 'focus_existing_tab') return true
  try {
    const url = new URL(action.value || '')
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

export function durableExecutionKey(action: SuggestedAction, tabId: number): string {
  const submission = action.consequential_submission
  const identity = submission
    ? `submission:${submission.submission_id}:${submission.operation}:${submission.destination_entity}:${submission.content_identity}`
    : action.intent_id || action.action_id || [
    action.action_type,
    action.target_selector || '',
    action.value || '',
  ].join('|')
  return `${action.mission_id || 'local'}:${tabId}:${identity}`
}

export function createDurableLedger(state: WorkflowState, now = Date.now()): DurableWorkflowLedger {
  return {
    schemaVersion: DURABLE_LEDGER_SCHEMA_VERSION,
    sessionId: state.sessionId,
    revision: 1,
    updatedAt: now,
    workflow: state,
    approval: { status: approvalStatusForState(state), actionId: pendingActionId(state), updatedAt: now },
    executions: {},
  }
}

export function checkpointDurableLedger(
  current: DurableWorkflowLedger | null,
  state: WorkflowState,
  now = Date.now(),
): DurableWorkflowLedger {
  const base = current?.sessionId === state.sessionId ? current : createDurableLedger(state, now)
  const derivedApproval = approvalStatusForState(state)
  const preserveActiveApproval = state.phase === 'executing' && base.approval.actionId === state.activeAction?.action_id
  return {
    ...base,
    revision: base.revision + 1,
    updatedAt: now,
    workflow: state,
    approval: {
      status: preserveActiveApproval ? base.approval.status : derivedApproval,
      actionId: preserveActiveApproval ? base.approval.actionId : pendingActionId(state),
      updatedAt: now,
    },
  }
}

export function reserveDurableExecution(
  ledger: DurableWorkflowLedger,
  action: SuggestedAction,
  tabId: number,
  mode: 'manual' | 'auto',
  now = Date.now(),
): { ledger: DurableWorkflowLedger; record: DurableExecutionRecord; accepted: boolean; reason?: string } {
  const key = durableExecutionKey(action, tabId)
  const previous = ledger.executions[key]
  if (previous?.status === 'succeeded') {
    return { ledger, record: previous, accepted: false, reason: 'already_succeeded' }
  }
  if (previous?.status === 'in_flight' || previous?.status === 'uncertain') {
    return { ledger, record: previous, accepted: false, reason: 'uncertain_prior_dispatch' }
  }
  const retryable = isLowRiskReversibleAction(action)
  const attempts = (previous?.attempts ?? 0) + 1
  if (attempts > (retryable ? MAX_REVERSIBLE_ATTEMPTS : 1)) {
    return { ledger, record: previous!, accepted: false, reason: 'attempt_limit' }
  }
  const record: DurableExecutionRecord = {
    key,
    actionId: action.action_id,
    actionType: action.action_type,
    tabId,
    status: 'in_flight',
    attempts,
    retryable,
    startedAt: previous?.startedAt ?? now,
    updatedAt: now,
  }
  return {
    accepted: true,
    record,
    ledger: {
      ...ledger,
      revision: ledger.revision + 1,
      updatedAt: now,
      approval: {
        status: mode === 'manual' ? 'approved_manual' : 'approved_auto',
        actionId: action.action_id,
        updatedAt: now,
      },
      executions: { ...ledger.executions, [key]: record },
    },
  }
}

export function completeDurableExecution(
  ledger: DurableWorkflowLedger,
  key: string,
  result: ExecutionResult,
  now = Date.now(),
): DurableWorkflowLedger {
  const current = ledger.executions[key]
  if (!current) return ledger
  const record: DurableExecutionRecord = {
    ...current,
    status: result.success ? 'succeeded' : result.dispatch_uncertain ? 'uncertain' : 'failed',
    result,
    updatedAt: now,
  }
  return {
    ...ledger,
    revision: ledger.revision + 1,
    updatedAt: now,
    approval: { status: 'none', actionId: null, updatedAt: now },
    executions: { ...ledger.executions, [key]: record },
  }
}

export function normalizeLedgerAfterRestart(
  ledger: DurableWorkflowLedger,
  now = Date.now(),
): DurableWorkflowLedger {
  const executions = Object.fromEntries(Object.entries(ledger.executions).map(([key, record]) => [
    key,
    record.status === 'in_flight'
      ? { ...record, status: 'uncertain' as const, updatedAt: now }
      : record,
  ]))
  const interrupted = Object.values(executions).some((record) => record.status === 'uncertain')
  const transient = ['observing', 'analyzing', 'executing', 'refreshing'].includes(ledger.workflow.phase)
  const workflow: WorkflowState = interrupted || transient
    ? {
        ...ledger.workflow,
        phase: 'failed',
        activeAction: null,
        pendingActions: [],
        error: interrupted
          ? 'A browser action may have been dispatched before restart. It will not be repeated. Resume to re-observe the page and continue safely.'
          : 'The workflow was interrupted before its checkpoint completed. Resume to continue from the last durable state.',
      }
    : ledger.workflow
  return {
    ...ledger,
    revision: ledger.revision + 1,
    updatedAt: now,
    workflow,
    approval: { status: 'none', actionId: null, updatedAt: now },
    executions,
  }
}

export function completionEvidenceValid(input: {
  sgvVerified?: boolean
  missionResultAvailable?: boolean
}): boolean {
  return input.sgvVerified === true || input.missionResultAvailable === true
}

export async function loadDurableLedger(): Promise<DurableWorkflowLedger | null> {
  const stored = await chrome.storage.local.get(DURABLE_WORKFLOW_LEDGER_KEY)
  const value = stored[DURABLE_WORKFLOW_LEDGER_KEY] as DurableWorkflowLedger | undefined
  if (!value || value.schemaVersion !== DURABLE_LEDGER_SCHEMA_VERSION || !value.workflow?.sessionId) return null
  return value
}

export async function saveDurableLedger(ledger: DurableWorkflowLedger): Promise<void> {
  await chrome.storage.local.set({ [DURABLE_WORKFLOW_LEDGER_KEY]: sanitizeLedgerForStorage(ledger) })
}

export async function clearDurableLedger(): Promise<void> {
  await chrome.storage.local.remove(DURABLE_WORKFLOW_LEDGER_KEY)
}

function pendingActionId(state: WorkflowState): string | null {
  return state.activeAction?.action_id ?? state.pendingActions[0]?.action_id ?? null
}

function approvalStatusForState(state: WorkflowState): DurableApprovalStatus {
  if (state.phase === 'awaiting_execution' && state.pendingActions.length > 0) return 'awaiting_user'
  return 'none'
}

function sanitizeLedgerForStorage(ledger: DurableWorkflowLedger): DurableWorkflowLedger {
  const scrubAction = (action: SuggestedAction): SuggestedAction => {
    const descriptor = `${action.action_type} ${action.target_selector || ''} ${action.description}`
    return /\b(password|passcode|otp|one[- ]?time|verification code|api key|access token|secret)\b/i.test(descriptor)
      ? { ...action, value: null }
      : action
  }
  return {
    ...ledger,
    workflow: {
      ...ledger.workflow,
      pendingActions: ledger.workflow.pendingActions.map(scrubAction),
      activeAction: ledger.workflow.activeAction ? scrubAction(ledger.workflow.activeAction) : null,
      completedActions: ledger.workflow.completedActions.map((item) => ({
        ...item,
        action: scrubAction(item.action),
        result: { ...item.result, page_context: undefined },
      })),
      userInputs: ledger.workflow.userInputs.map((input) =>
        /\b(password|passcode|otp|one[- ]?time|verification code|api key|access token|secret)\b/i.test(input)
          ? '[Sensitive answer omitted from durable checkpoint]'
          : input
      ),
    },
  }
}
