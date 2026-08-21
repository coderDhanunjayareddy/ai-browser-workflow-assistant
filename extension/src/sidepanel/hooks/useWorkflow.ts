import { useState, useCallback, useEffect, useRef } from 'react'
import { sendToBackground } from '../../utils/messaging'
import { BACKEND_URL } from '../../config'
import {
  createTaskWorkspace,
  summarizeTaskWorkspace,
  updateTaskWorkspace,
  type TaskWorkspace,
} from '../taskWorkspace'
export { createTaskWorkspace, updateTaskWorkspace } from '../taskWorkspace'
import {
  summarizeMultiTabWorkspace,
  updateTabFactCount,
  type MultiTabWorkspace,
} from '../../workspace/multiTabWorkspace'
export { createMultiTabWorkspace, registerTab, updateTab, activateTab, removeClosedTab, updateTabPurpose, updateTabFactCount, summarizeMultiTabWorkspace } from '../../workspace/multiTabWorkspace'
import {
  createMissionSnapshot,
  summarizeMissionSnapshot,
  updateMissionSnapshot,
  type MissionSnapshot,
} from '../missionState'
export { createMissionSnapshot, summarizeMissionSnapshot, updateMissionSnapshot } from '../missionState'
import {
  buildBudgetedPlannerContext,
  PLANNER_SUPPLEMENTAL_CONTEXT_BUDGET,
  type PlannerContextSection,
} from '../contextBudgetManager'
import {
  checkpointDurableLedger,
  clearDurableLedger,
  completionEvidenceValid,
  createDurableLedger,
  isLowRiskReversibleAction,
  isSafeAutonomousNavigation,
  loadDurableLedger,
  MAX_REVERSIBLE_ATTEMPTS,
  normalizeLedgerAfterRestart,
  reserveDurableExecution,
  completeDurableExecution,
  saveDurableLedger,
  type DurableWorkflowLedger,
} from '../durableWorkflowLedger'
import { buildCanonicalActionContract } from '../../execution/canonical_action_contract'
export { buildBudgetedPlannerContext, PLANNER_SUPPLEMENTAL_CONTEXT_BUDGET } from '../contextBudgetManager'
import type {
  PageContext,
  AnalyzeResponse,
  SuggestedAction,
  ExecutionResult,
  CompletedAction,
  PriorStep,
  PlannerOutcomeKind,
  ReportOutcome,
  ReplanOutcome,
  IntentDTO,
  IntentNextResponse,
  IntentUpdateResponse,
  MissionResult,
  PolicyExecutionContext,
  PolicyProvenanceLabel,
  CanonicalActionContract,
} from '../../types'
import { exactOpenOnlyCompletion } from '../../execution/exact_open_completion'

const ANALYZE_TIMEOUT_MS = 90_000
const ACTION_EXECUTION_TIMEOUT_MS = 45_000
const POST_ACTION_TIMEOUT_MS = 20_000
const INTENT_UPDATE_TIMEOUT_MS = 20_000
const MAX_DETAILED_PRIOR_STEPS = 30
const MAX_TOTAL_PRIOR_STEPS = 30
const MAX_ANALYSIS_SNAPSHOT_CHARS = 1000
const MAX_EXECUTION_FEEDBACK_CHARS = 900
const MAX_REPEATED_INTERACTIVE_ACTIONS = 2
const RETRYABLE_ANALYZE_STATUSES = new Set([502, 503, 504])

/** Safely convert any thrown value to a readable string. */
function errMsg(err: unknown): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  if (err && typeof err === 'object') {
    const e = err as Record<string, unknown>
    if (typeof e.message === 'string') return e.message
    return JSON.stringify(err)
  }
  return String(err)
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new Error(`${label} timed out after ${timeoutMs}ms`))
    }, timeoutMs)
    promise.then(
      (value) => {
        window.clearTimeout(timer)
        resolve(value)
      },
      (err) => {
        window.clearTimeout(timer)
        reject(err)
      },
    )
  })
}

interface LivePolicyDecision {
  policy_decision: 'allow' | 'warn' | 'allow_with_confirmation' | 'block' | 'handoff_required' | 'defer'
  allowed: boolean
  approval_required: boolean
  requires_handoff: boolean
  decision_reason: string
}

interface ConfirmationReceiptResponse {
  receipt_id: string
}

interface OriginGrantResponse {
  grant_id: string
}

function promptInjectionLabels(context: PageContext): string[] {
  const text = `${context.title}\n${context.visible_text}`.toLowerCase()
  const labels: string[] = ['page_observation']
  if (/ignore (all |any )?(previous|prior|system|developer) instructions/.test(text)) {
    labels.push('prompt_injection_detected')
  }
  if (/(reveal|send|upload|exfiltrate).{0,60}(password|otp|token|cookie|api key|secret)/.test(text)) {
    labels.push('secret_exfiltration')
  }
  if (/(bypass|disable|ignore).{0,40}(policy|approval|safety|confirmation)/.test(text)) {
    labels.push('policy_bypass_request')
  }
  return labels
}

function policyProvenance(sessionId: string, action: SuggestedAction, context: PageContext): PolicyProvenanceLabel[] {
  return [
    { source_type: 'user', source_id: `session:${sessionId}`, trust: 'trusted', labels: ['direct_user_task'] },
    { source_type: 'planner', source_id: `action:${action.action_id}`, trust: 'untrusted', labels: ['model_proposed'] },
    { source_type: 'page', source_id: `page:${context.tab_id ?? 'unknown'}`, trust: 'untrusted', labels: promptInjectionLabels(context) },
  ]
}

function bindObservationGrounding(action: SuggestedAction, context: PageContext): SuggestedAction {
  const observed = context.interactive_elements.find((element) =>
    element.selector === action.target_selector ||
    (element.selector_id && element.selector_id === action.target_selector) ||
    (element.element_id && element.element_id === action.target_selector)
  )
  if (!observed) return action
  const visualAction = new Set(['visual_region', 'canvas_action', 'svg_action', 'chart_action', 'map_action']).has(action.action_type)
  return {
    ...action,
    grounding: {
      ...(action.grounding || {}),
      source: visualAction ? 'vision_region' : 'dom_snapshot',
      selector_id: observed.selector_id ?? observed.element_id ?? null,
      accessibility_name: observed.accessibility_name ?? observed.aria_label ?? observed.text ?? null,
      role: observed.role ?? observed.type ?? null,
      semantic_kind: observed.semantic_kind ?? null,
      bounding_box: observed.bounding_box ?? null,
    },
  }
}

async function policyJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetchWithTimeout(`${BACKEND_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, POST_ACTION_TIMEOUT_MS)
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: unknown }
    throw new Error(formatErrorDetail(payload.detail, `Policy request failed (${response.status})`))
  }
  return await response.json() as T
}

async function preparePolicyExecution(
  sessionId: string,
  action: SuggestedAction,
  context: PageContext,
  source: ExecutionMode,
  contract: CanonicalActionContract,
): Promise<PolicyExecutionContext> {
  const provenance = policyProvenance(sessionId, action, context)
  const policyOrigin = contract.origin.target_url || context.url
  const request = { session_id: sessionId, origin: policyOrigin, action, execution_contract: contract, provenance }
  const decision = await policyJson<LivePolicyDecision>('/policy/evaluate', request)

  if (decision.policy_decision === 'block' || decision.policy_decision === 'handoff_required' || decision.policy_decision === 'defer') {
    throw new Error(`Policy stopped this action: ${decision.decision_reason}`)
  }
  if (source === 'auto' && decision.policy_decision !== 'allow') {
    throw new Error('Policy requires explicit user approval before this action can execute.')
  }

  let confirmationReceiptId: string | null = null
  let originGrantId: string | null = null
  if (decision.policy_decision === 'allow_with_confirmation') {
    const receipt = await policyJson<ConfirmationReceiptResponse>('/policy/confirm', {
      request,
      ttl_seconds: 120,
      confirmation_source: 'human_sidepanel',
    })
    confirmationReceiptId = receipt.receipt_id
  } else if (decision.policy_decision === 'warn') {
    const grant = await policyJson<OriginGrantResponse>('/policy/origin-grants', {
      session_id: sessionId,
      origin: policyOrigin,
      action_types: [action.action_type],
      ttl_seconds: 900,
      grant_source: 'human_sidepanel',
    })
    originGrantId = grant.grant_id
  }

  return {
    session_id: sessionId,
    provenance,
    origin_grant_id: originGrantId,
    confirmation_receipt_id: confirmationReceiptId,
  }
}

function formatErrorDetail(detail: unknown, fallback: string): string {
  if (detail == null) return fallback
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => formatErrorDetail(item, fallback)).join(' | ')
  }
  if (typeof detail === 'object') {
    const item = detail as Record<string, unknown>
    if (typeof item.message === 'string') return item.message
    if (typeof item.reason === 'string') return item.reason
    if (typeof item.error === 'string') return item.error
    try {
      return JSON.stringify(detail)
    } catch {
      return fallback
    }
  }
  return String(detail)
}

export type WorkflowFailureCategory =
  | 'network'
  | 'timeout'
  | 'permission'
  | 'policy'
  | 'no_effect'
  | 'target_not_found'
  | 'uncertain_dispatch'
  | 'service'
  | 'unexpected'

export interface MeaningfulWorkflowFailure {
  category: WorkflowFailureCategory
  userMessage: string
  retryable: boolean
}

export function meaningfulWorkflowFailure(
  rawMessage: string,
  stage: 'observation' | 'analysis' | 'execution',
  actionDescription = '',
): MeaningfulWorkflowFailure {
  const text = String(rawMessage || '').trim().toLowerCase()
  const subject = actionDescription.trim() ? ` “${actionDescription.trim()}”` : ''
  if (/may already have been dispatched|uncertain_prior_dispatch|not repeated/.test(text)) {
    return { category: 'uncertain_dispatch', userMessage: `I could not verify whether${subject || ' the browser action'} already happened, so I stopped without repeating it. Refresh the page and review its current state before continuing.`, retryable: false }
  }
  if (/policy|confirmation|approval|privileged url/.test(text)) {
    return { category: 'policy', userMessage: `I paused${subject} because the safety policy or required confirmation did not allow it to continue. No additional action was taken.`, retryable: false }
  }
  if (/frame with id .* showing error page|chrome-error:\/\/|extraction failed.*error page|err_unsafe_port/.test(text)) {
    return { category: 'network', userMessage: `The destination for${subject || ' the requested navigation'} returned a browser error page. I stopped after one attempt and did not repeat the navigation.`, retryable: false }
  }
  if (/timed out|timeout/.test(text)) {
    return { category: 'timeout', userMessage: `The ${stage} step${subject} did not finish within the safe time limit. I stopped the attempt instead of waiting or retrying indefinitely.`, retryable: true }
  }
  if (/failed to fetch|network|connection|err_|temporarily unavailable|503|502|504/.test(text)) {
    return { category: stage === 'analysis' ? 'service' : 'network', userMessage: `I could not reach the required ${stage === 'analysis' ? 'planning service' : 'website or browser service'}. I stopped safely; check the connection and try again.`, retryable: true }
  }
  if (/permission|access denied|not allowed|restricted/.test(text)) {
    return { category: 'permission', userMessage: `The browser blocked${subject || ' this step'} because the required permission or destination is unavailable. No further action was attempted.`, retryable: false }
  }
  if (/no[_ ]effect|unchanged|did not change|could not verify page progress/.test(text)) {
    return { category: 'no_effect', userMessage: `The page did not show the expected result after${subject || ' the attempted action'}. I recorded the no-effect result and stopped repeating the same step.`, retryable: true }
  }
  if (/target.*not found|selector|not grounded|exact.*not.*found|could not find/.test(text)) {
    return { category: 'target_not_found', userMessage: `I could not find one verified page control for${subject || ' the requested step'}. I did not click a substitute or guess a target.`, retryable: true }
  }
  return { category: 'unexpected', userMessage: `I could not complete${subject || ` the ${stage} step`}. I stopped safely, recorded the failure, and did not claim success.`, retryable: false }
}

// Phase describes what the workflow engine is currently doing.
export type WorkflowPhase =
  | 'idle'         // Nothing started yet
  | 'observing'    // Reading the page before the first planner call
  | 'analyzing'    // Calling the AI planner
  | 'awaiting_execution' // Waiting for user to approve/reject the active action
  | 'executing'    // Running the approved action on the live page
  | 'refreshing'   // Reading fresh page state after execution or user input
  | 'awaiting_user' // Waiting for missing user-provided information
  | 'reported'     // Planner reported an answer; not SGV-verified in production yet
  | 'replan'       // Planner requested a different plan; presentation only in Phase 1
  | 'completed'    // Workflow finished successfully or with no more actions
  | 'cancelled'    // User stopped or rejected the workflow
  | 'failed'       // Workflow could not continue because of an error

export interface WorkflowState {
  sessionId: string
  task: string
  analysisText: string
  pendingActions: SuggestedAction[]   // DTO view of the currently assigned ledger intent; never a local queue.
  activeAction: SuggestedAction | null // DTO view of the ledger intent currently executing.
  completedActions: CompletedAction[] // Presentation-only local audit trail; not execution authority.
  validationPriorSteps: PriorStep[]
  workspace: TaskWorkspace | null
  tabWorkspace: MultiTabWorkspace | null
  missionSnapshot: MissionSnapshot | null
  userInputs: string[]
  clarificationQuestion: string | null
  contractOutcome: PlannerOutcomeKind | null
  report: ReportOutcome | null
  replan: ReplanOutcome | null
  goalConvergence: boolean
  phase: WorkflowPhase
  error: string | null
}

export type ExecutionMode = 'manual' | 'auto'

const CRITICAL_ACTION_PATTERNS = [
  /\bpayment\b/,
  /\bpurchase\b/,
  /\bbuy\b/,
  /\bcheckout\b/,
  /\bdelete\b/,
  /\bremove\b/,
  /\bshare\b/,
  /\bsend\b.*\b(email|message)\b/,
  /\bsubmit\b/,
  /\bpassword\b/,
  /\b(one[- ]?time (?:password|code)|otp|verification code|api key|access token|secret)\b/,
  /\blogin\b.*\bchange\b/,
  /\bsecurity\b/,
  /\baccount\b.*\b(change|close|delete|security)\b/,
  /\baccount settings?\b/,
  /\b(change|update|modify|enable|disable|turn on|turn off)\b.{0,40}\b(account|setting|preference|notification|profile)\b/,
]

export function actionRequiresExplicitApproval(action: SuggestedAction | null | undefined): boolean {
  if (!action) return false
  if (action.safety_level === 'danger') return true

  const searchableText = [
    action.action_type,
    action.target_selector,
    action.description,
    action.reasoning,
    action.value ?? '',
  ].join(' ').toLowerCase()

  return CRITICAL_ACTION_PATTERNS.some((pattern) => pattern.test(searchableText))
}

export function shouldAutoExecuteAction(
  action: SuggestedAction | null | undefined,
  mode: ExecutionMode,
): boolean {
  if (!action || mode !== 'auto') return false
  if (actionRequiresExplicitApproval(action)) return false
  return isLowRiskReversibleAction(action) || isSafeAutonomousNavigation(action)
}

interface AnalyzeRoutingOptions {
  completedActions: CompletedAction[]
  currentUrl?: string
  userInputs: string[]
  includeReanalysisErrors?: boolean
}

interface AnalyzeRoutingResult {
  phase: WorkflowPhase
  analysisText: string
  pendingActions: SuggestedAction[]
  clarificationQuestion: string | null
  contractOutcome: PlannerOutcomeKind
  report: ReportOutcome | null
  replan: ReplanOutcome | null
  goalConvergence: boolean
  error: string | null
  continueAfterRejectedReport: boolean
  continueAfterBackendStep: boolean
  rejectedReportPriorStep: PriorStep | null
}

interface WorkflowLoopInput {
  sessionId: string
  task: string
  completedActions: CompletedAction[]
  validationPriorSteps: PriorStep[]
  workspace: TaskWorkspace | null
  tabWorkspace: MultiTabWorkspace | null
  userInputs: string[]
  refresh: boolean
}

interface AnalyzeRequestBody {
  session_id: string
  task: string
  page_context: PageContext
  prior_steps?: PriorStep[]
  supplemental_context: string
}

async function fetchWithTimeout(url: string, options: RequestInit, ms: number): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), ms)
  try {
    return await fetch(url, { ...options, signal: ctrl.signal })
  } catch (err) {
    if ((err as Error).name === 'AbortError')
      throw new Error(`AI analysis is taking longer than ${ms / 1000}s. The backend may still be running, or the page context may be too large. Try continuing again after a moment.`)
    throw err
  } finally {
    clearTimeout(timer)
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function fetchAnalyzeWithRetry(url: string, options: RequestInit): Promise<Response> {
  let lastResponse: Response | null = null
  let lastError: unknown = null

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const response = await fetchWithTimeout(url, options, ANALYZE_TIMEOUT_MS)
      if (!RETRYABLE_ANALYZE_STATUSES.has(response.status)) return response
      lastResponse = response
    } catch (err) {
      lastError = err
      if (attempt === 2) throw err
    }

    if (attempt < 2) await delay(1200 * (attempt + 1))
  }

  if (lastResponse) return lastResponse
  throw lastError instanceof Error ? lastError : new Error(String(lastError))
}

function compactMetadata(metadata?: Record<string, string>): Record<string, string> {
  if (!metadata) return {}
  return Object.fromEntries(
    Object.entries(metadata)
      .filter(([, value]) => Boolean(value))
      .slice(0, 12)
      .map(([key, value]) => [key, value.slice(0, 300)]),
  )
}

function normalizeForCompare(value: string | null | undefined): string {
  return (value ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
}

function contextFingerprint(ctx: PageContext | null): string {
  if (!ctx) return ''
  return [
    ctx.url,
    ctx.title,
    ctx.headings.slice(0, 5).join('|'),
    ctx.visible_text.slice(0, 1200),
    ctx.interactive_elements
      .slice(0, 60)
      .map((el) => `${el.type}:${el.selector}:${el.text}:${el.placeholder ?? ''}`)
      .join('|'),
    ctx.content_blocks
      .slice(0, 12)
      .map((block) => `${block.selector}:${block.text.slice(0, 180)}`)
      .join('|'),
  ].map(normalizeForCompare).join('\n')
}

function normalizeUrlForCompare(value: string | null | undefined): string {
  const raw = (value ?? '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    parsed.hash = ''
    if ((parsed.protocol === 'https:' && parsed.port === '443') || (parsed.protocol === 'http:' && parsed.port === '80')) {
      parsed.port = ''
    }
    const normalized = parsed.toString()
    return normalized.endsWith('/') ? normalized.slice(0, -1) : normalized
  } catch {
    return raw.replace(/#.*$/, '').replace(/\/$/, '')
  }
}

function actionNeedsObservableProgress(action: SuggestedAction): boolean {
  if (action.action_type === 'navigate') return true
  if (action.action_type === 'navigate_next_page') return true
  if (action.action_type === 'focus_existing_tab' || action.action_type === 'switch_tab') return true
  if (action.action_type !== 'click') return false
  return !/\b(focus|prepare|place (?:the )?cursor|click (?:on )?(?:the )?(?:input|field))\b/i.test(
    action.description,
  )
}

export function validateObservableProgress(
  action: SuggestedAction,
  before: PageContext | null,
  after: PageContext,
  result?: Pick<ExecutionResult, 'success' | 'tab_switch_verified'>,
): string | null {
  if (!before || !actionNeedsObservableProgress(action)) return null
  if (
    (action.action_type === 'focus_existing_tab' || action.action_type === 'switch_tab') &&
    result?.success &&
    result.tab_switch_verified === true
  ) {
    return null
  }

  const changed = contextFingerprint(before) !== contextFingerprint(after)
  const navigated = before.url !== after.url
  const requestedNavigationReached =
    action.action_type === 'navigate' &&
    Boolean(action.value) &&
    normalizeUrlForCompare(action.value) === normalizeUrlForCompare(after.url)
  if (requestedNavigationReached) return null
  if (navigated || changed) return null

  return `Action reported success, but the page did not visibly change after ${action.action_type}. Retrying from the current page state.`
}

export function actionRequiresDomSettle(actionType: SuggestedAction['action_type']): boolean {
  return (
    actionType === 'navigate' ||
    actionType === 'navigate_next_page' ||
    actionType === 'fill' ||
    actionType === 'click' ||
    actionType === 'wait' ||
    actionType === 'select_option' ||
    actionType === 'choose_date' ||
    actionType === 'keyboard_shortcut'
  )
}

export function pageContextEvidenceScore(context: PageContext): number {
  return (
    context.interactive_elements.filter((element) => element.visible !== false).length * 10_000 +
    context.content_blocks.length * 1_000 +
    context.headings.length * 100 +
    context.visible_text.trim().length
  )
}

export function selectRicherPageContext(current: PageContext | null, candidate: PageContext): PageContext {
  if (!current) return candidate
  return pageContextEvidenceScore(candidate) > pageContextEvidenceScore(current) ? candidate : current
}

export function pageContextHasNamedEditableControl(context: PageContext): boolean {
  return context.interactive_elements.some((element) => {
    const role = (element.role ?? '').toLowerCase()
    const editableType = (
      element.type === 'input' ||
      element.type === 'textarea' ||
      role === 'textbox' ||
      role === 'searchbox' ||
      role === 'combobox' ||
      element.input_type === 'contenteditable'
    )
    const name = [element.text, element.aria_label, element.accessibility_name, element.placeholder]
      .filter(Boolean)
      .join(' ')
      .trim()
    return editableType && name.length > 0
  })
}

export function postNavigationObservationAttempts(task: string): number {
  return /\b(search|contact|recipient|message|field|form|login|sign in|upload|attach)\b/i.test(task) ? 8 : 3
}

export function initialObservationAttempts(task: string): number {
  return /\b(search|contact|recipient|message|field|form|login|sign in|upload|attach)\b/i.test(task) ? 8 : 1
}

function detectExecutionSemanticMismatch(
  action: SuggestedAction,
  before: PageContext | null,
  after: PageContext,
): Pick<
  ExecutionResult,
  'semantic_mismatch' |
  'semantic_mismatch_reason' |
  'semantic_mismatch_observed_result' |
  'semantic_mismatch_assessment'
> | null {
  if (!before || !actionNeedsObservableProgress(action)) return null

  const pageText = normalizeForCompare([
    after.title,
    after.headings.slice(0, 3).join(' '),
    after.visible_text.slice(0, 500),
  ].join(' '))
  const obviousWrongPage = /\b(404|page not found|not found|does not exist|doesn't exist|cannot be found|isn't available)\b/i
    .test(pageText)

  if (!obviousWrongPage) return null

  return {
    semantic_mismatch: true,
    semantic_mismatch_reason: 'obvious_wrong_page',
    semantic_mismatch_observed_result: 'The browser reached a page state that appears unrelated to the intended goal.',
    semantic_mismatch_assessment: "The selected element's semantic purpose did not match the intended goal.",
  }
}

function buildExecutionFeedback(action: SuggestedAction, result: ExecutionResult): string {
  const verification = result.verification
  const lines = [
    'Execution Feedback',
    `Action: ${action.action_type}`,
    `Execution: ${result.success ? 'success' : 'failed'}`,
  ]

  if (verification) {
    lines.push(`Verification: ${verification.verified ? 'verified' : verification.reason}`)
  }

  if (typeof result.recovery_attempted === 'boolean') {
    lines.push(`Recovery: ${result.recovery_attempted ? 'attempted' : 'not_attempted'}`)
  }

  if (typeof result.form_valid === 'boolean') {
    lines.push(`Form Valid: ${result.form_valid ? 'yes' : 'no'}`)
  }
  if (typeof result.invalid_field_count === 'number') {
    lines.push(`Invalid Fields: ${result.invalid_field_count}`)
  }
  if (result.validation_message) {
    lines.push(`Validation Message: ${result.validation_message}`)
  }

  if (result.recovery_attempted) {
    lines.push(`Recovery Result: ${result.recovery_verified ? 'verified' : 'failed'}`)
    if (result.recovery_reason) lines.push(`Recovery Reason: ${result.recovery_reason}`)
  } else if (result.recovery_reason) {
    lines.push(`Recovery Reason: ${result.recovery_reason}`)
  }

  if (result.semantic_mismatch) {
    lines.push('Semantic Assessment: mismatch')
    if (result.semantic_mismatch_observed_result) {
      lines.push(`Observed Result: ${result.semantic_mismatch_observed_result}`)
    }
    if (result.semantic_mismatch_assessment) {
      lines.push(`Execution Assessment: ${result.semantic_mismatch_assessment}`)
    }
    lines.push('Recommendation: Avoid repeating the previous selector unless page evidence changes.')
    lines.push('Recommendation: Select an element whose semantic purpose matches the requested goal.')
  } else if (verification?.reason === 'no_effect') {
    lines.push('Recommendation: Avoid repeating this selector unless the page evidence has changed.')
  } else if (verification?.verified) {
    lines.push('Recommendation: Treat the action as having produced the intended browser effect.')
  } else if (!result.success) {
    lines.push('Recommendation: Do not assume the browser action completed.')
  }

  return lines.join('\n').slice(0, MAX_EXECUTION_FEEDBACK_CHARS)
}

function sanitizeExecutionMessageForPlanner(message: string): string {
  return message
    .replace(/Clicked at \([^)]+\): .*/i, 'Clicked target')
    .replace(/Clicked once: .*/i, 'Clicked target')
    .replace(/Clicked: .*/i, 'Clicked target')
    .replace(/Filled field: .*/i, 'Filled field')
    .replace(/Selected option: (.*?) on select: .*/i, 'Selected option: $1')
    .replace(/Selected visible option: .*/i, 'Selected visible option')
    .replace(/Scrolled (.*?) on: .*/i, 'Scrolled $1')
}

function buildExecutionResultForPlanner(
  action: SuggestedAction,
  result: ExecutionResult,
  includeFeedback: boolean,
): string {
  const message = sanitizeExecutionMessageForPlanner(result.message)
  if (!includeFeedback) return message
  const feedback = buildExecutionFeedback(action, result)
  return [message, feedback].filter(Boolean).join('\n\n')
}

function buildPriorSteps(completed: CompletedAction[]): PriorStep[] {
  const startDetailedIndex = Math.max(0, completed.length - MAX_DETAILED_PRIOR_STEPS)
  return completed.slice(-MAX_TOTAL_PRIOR_STEPS).map(({ action, result, analysis_snapshot, page_snapshot }, index, visibleSteps) => {
    const originalIndex = completed.length - visibleSteps.length + index
    const includeDetails = originalIndex >= startDetailedIndex
    const includeExecutionFeedback = originalIndex === completed.length - 1

    return {
    action_type: action.action_type,
    description: action.description,
    target_selector: includeDetails ? action.target_selector : null,
    value: includeDetails ? action.value : null,
    execution_result: buildExecutionResultForPlanner(action, result, includeExecutionFeedback),
    page_analysis: includeDetails ? analysis_snapshot?.slice(0, MAX_ANALYSIS_SNAPSHOT_CHARS) : undefined,
    page_url: includeDetails ? page_snapshot?.url : undefined,
    page_title: includeDetails ? page_snapshot?.title : undefined,
    page_metadata: includeDetails ? compactMetadata(page_snapshot?.metadata) : {},
    browser_evidence: includeDetails ? buildBrowserEvidence(action, result, page_snapshot) : undefined,
  }
  })
}

function primitiveEvidence(
  value: unknown,
): string | number | boolean | null | undefined {
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || value === null) {
    return value
  }
  return undefined
}

export function buildBackendIntentPriorStep(
  result: AnalyzeResponse,
  pageContext?: PageContext | null,
): PriorStep | null {
  const raw = result.intent_execution as any
  if (!raw || raw.status !== 'succeeded') return null

  const executions = Array.isArray(raw.executions) ? raw.executions : []
  const execution = executions[executions.length - 1] ?? executions[0] ?? raw
  const evidence = Array.isArray(raw.evidence) ? raw.evidence : []
  const payload = execution?.payload && typeof execution.payload === 'object'
    ? execution.payload as Record<string, unknown>
    : {}
  const evidencePayload = evidence
    .map((item: any) => item?.payload)
    .find((item: unknown) => item && typeof item === 'object') as Record<string, unknown> | undefined
  const mergedPayload = { ...(evidencePayload ?? {}), ...payload }
  const intent = String(execution?.intent ?? raw.intent ?? payload.action_type ?? 'backend_intent')
  const evidenceSummary = evidence
    .map((item: any) => typeof item?.summary === 'string' ? item.summary : '')
    .filter(Boolean)
    .join('\n')

  const browserEvidence: Record<string, string | number | boolean | null> = {}
  for (const [key, value] of Object.entries(mergedPayload)) {
    const primitive = primitiveEvidence(value)
    if (primitive !== undefined) browserEvidence[key] = primitive
  }

  return {
    action_type: intent,
    description: String(payload.description ?? `Backend intent completed: ${intent}`),
    target_selector: null,
    value: typeof payload.value === 'string' ? payload.value : null,
    execution_result: [
      raw.reason ? String(raw.reason) : 'Backend intent execution succeeded.',
      evidenceSummary,
    ].filter(Boolean).join('\n').slice(0, MAX_EXECUTION_FEEDBACK_CHARS),
    page_analysis: result.analysis?.slice(0, MAX_ANALYSIS_SNAPSHOT_CHARS),
    page_url: pageContext?.url,
    page_title: pageContext?.title,
    page_metadata: compactMetadata(pageContext?.metadata),
    browser_evidence: Object.keys(browserEvidence).length > 0 ? browserEvidence : undefined,
  }
}

function buildBrowserEvidence(
  action: SuggestedAction,
  result: ExecutionResult,
  pageSnapshot?: CompletedAction['page_snapshot'],
): Record<string, string | number | boolean | null> | undefined {
  const evidence: Record<string, string | number | boolean | null> = {}
  const timeline = result.browser_timeline || {}

  if (action.action_id) evidence.action_id = action.action_id
  if (result.action_id) evidence.result_action_id = result.action_id
  if (pageSnapshot?.url) evidence.page_url = pageSnapshot.url
  if (pageSnapshot?.title) evidence.page_title = pageSnapshot.title
  if (typeof result.opened_tab_id === 'number') evidence.opened_tab_id = result.opened_tab_id
  if (typeof result.previous_tab_id === 'number') evidence.previous_tab_id = result.previous_tab_id
  if (typeof result.active_tab_id === 'number') evidence.active_tab_id = result.active_tab_id
  if (typeof result.closed_tab_id === 'number') evidence.closed_tab_id = result.closed_tab_id
  if (typeof result.tab_switch_verified === 'boolean') evidence.tab_switch_verified = result.tab_switch_verified
  if (typeof result.execution_duration_ms === 'number') evidence.execution_duration_ms = result.execution_duration_ms
  if (result.execution_adapter) evidence.execution_adapter = result.execution_adapter
  if (result.cdp_grounding_source !== undefined) evidence.cdp_grounding_source = result.cdp_grounding_source
  if (typeof result.cdp_frame_count === 'number') evidence.cdp_frame_count = result.cdp_frame_count
  if (typeof result.cdp_target_count === 'number') evidence.cdp_target_count = result.cdp_target_count
  if (result.cdp_screenshot_hash !== undefined) evidence.cdp_screenshot_hash = result.cdp_screenshot_hash
  for (const [key, value] of Object.entries(result.adapter_trace || {}).slice(0, 30)) {
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || value === null) {
      evidence[`adapter_${key}`] = value
    }
  }

  for (const key of [
    'form_field_name',
    'form_field_label',
    'form_field_type',
    'form_id',
    'field_valid',
    'validation_message',
    'form_valid',
    'invalid_field_count',
    'filled_field_count',
    'submit_control_detected',
    'next_page_url',
    'pagination_mode',
    'pagination_control_label',
    'pagination_used_fallback_click',
    'upload_target_selector',
    'upload_input_hidden',
    'upload_files_count',
    'upload_backed_by_file_input',
    'upload_requires_user_file_selection',
    'upload_accepted',
  ]) {
    const value = result[key as keyof ExecutionResult]
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || value === null) {
      evidence[key] = value
    }
  }

  for (const key of ['requested_url', 'opened_window_id', 'tab_created_ms', 'navigation_complete_ms', 'capture_completed_ms']) {
    const value = timeline[key]
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean' || value === null) {
      evidence[key] = value
    }
  }

  return Object.keys(evidence).length > 0 ? evidence : undefined
}

function buildSupplementalContext(
  task: string,
  userInputs: string[],
  workspace?: TaskWorkspace | null,
  tabWorkspace?: MultiTabWorkspace | null,
  missionSnapshot?: MissionSnapshot | null,
): string {
  const sections: PlannerContextSection[] = []
  sections.push({
    heading: 'Active Goal',
    content: task,
    priority: 1,
  })
  const missionSummary = summarizeMissionSnapshot(missionSnapshot)
  if (missionSummary) sections.push(summarySection(missionSummary, 1))
  const workspaceSummary = summarizeTaskWorkspace(workspace)
  if (workspaceSummary) sections.push(summarySection(workspaceSummary, 2))
  const tabWorkspaceSummary = summarizeMultiTabWorkspace(tabWorkspace)
  if (tabWorkspaceSummary) sections.push(summarySection(tabWorkspaceSummary, 2))

  if (userInputs.length > 0) {
    sections.push({
      heading: 'Authoritative user-provided answers',
      content: [
        'Use these answers directly. Do not ask for the same information again:',
        ...userInputs.map((input, index) => `${index + 1}. ${input}`),
      ].join('\n'),
      priority: 1,
    })
  }

  return buildBudgetedPlannerContext(sections, PLANNER_SUPPLEMENTAL_CONTEXT_BUDGET)
}

function summarySection(summary: string, priority: PlannerContextSection['priority']): PlannerContextSection {
  const [heading, ...rest] = summary.split('\n')
  return {
    heading,
    content: rest.join('\n'),
    priority,
  }
}

export function workflowLoopObservationPhase(refresh: boolean): WorkflowPhase {
  return refresh ? 'refreshing' : 'observing'
}

export function buildAnalyzeRequestBody(
  sessionId: string,
  task: string,
  pageContext: PageContext,
  completedActions: CompletedAction[],
  userInputs: string[],
  workspace?: TaskWorkspace | null,
  tabWorkspace?: MultiTabWorkspace | null,
  validationPriorSteps: PriorStep[] = [],
  missionSnapshot?: MissionSnapshot | null,
): AnalyzeRequestBody {
  const actionPriorSteps = completedActions.length > 0 ? buildPriorSteps(completedActions) : []
  const priorSteps = [...actionPriorSteps, ...validationPriorSteps]
  const body = {
    session_id: sessionId,
    task,
    page_context: pageContext,
    prior_steps: priorSteps.length > 0 ? priorSteps : undefined,
    supplemental_context: buildSupplementalContext(task, userInputs, workspace, tabWorkspace, missionSnapshot),
  }
  logAnalyzePayloadDiagnostics(body)
  return body
}

function logAnalyzePayloadDiagnostics(body: AnalyzeRequestBody): void {
  const ctx: any = body.page_context
  const semanticKeys = Object.keys(ctx || {}).filter((key) => /semantic|entity|browser_intelligence|page_model/i.test(key))
  const interactive = Array.isArray(ctx?.interactive_elements) ? ctx.interactive_elements : []
  const blocks = Array.isArray(ctx?.content_blocks) ? ctx.content_blocks : []
  console.info('[V4.5.1 live-path] SIDEPANEL_POST_ANALYZE_BODY', {
    session_id: body.session_id,
    pageContextKeys: Object.keys(ctx || {}),
    semanticKeys,
    interactiveCount: interactive.length,
    contentBlockCount: blocks.length,
    hasSemanticEntities: Array.isArray(ctx?.semantic_entities),
    semanticEntityCount: Array.isArray(ctx?.semantic_entities) ? ctx.semantic_entities.length : 0,
    firstInteractive: interactive.slice(0, 6).map((item: any) => ({
      text: item?.text,
      href: item?.href,
      semantic_kind: item?.semantic_kind,
      selector_id: item?.selector_id,
    })),
    firstContentBlocks: blocks.slice(0, 6).map((item: any) => ({
      text: String(item?.text || '').slice(0, 120),
      href: item?.href,
      selector: item?.selector,
    })),
  })
}

function normalizeActionValue(action: SuggestedAction): string {
  const value = (action.value ?? '').trim()
  if (action.action_type !== 'navigate') return value.toLowerCase()

  try {
    const url = new URL(value)
    const params = [...url.searchParams.entries()]
      .filter(([key]) => !/^utm_|^ref$|^tag$|^ascsubtag$/i.test(key))
      .sort(([a], [b]) => a.localeCompare(b))
    const query = new URLSearchParams(params).toString()
    return `${url.origin}${url.pathname.replace(/\/$/, '')}${query ? `?${query}` : ''}`.toLowerCase()
  } catch {
    return value.toLowerCase()
  }
}

function actionSignature(action: SuggestedAction): string {
  return [
    action.action_type,
    (action.target_selector ?? '').trim().toLowerCase(),
    normalizeActionValue(action),
  ].join('|')
}

function isRepeatedAction(action: SuggestedAction, completed: CompletedAction[], currentUrl?: string): boolean {
  const signature = actionSignature(action)
  const matchingFailures = completed.filter(({ action: completedAction, result, page_snapshot }) => {
    if (result.success || actionSignature(completedAction) !== signature) return false
    if (currentUrl && page_snapshot?.url && page_snapshot.url !== currentUrl) return false
    return true
  })
  if (matchingFailures.length >= 2) return true

  const matchingCompleted = completed.filter(({ action: completedAction, result, page_snapshot }) => {
    if (!result.success || actionSignature(completedAction) !== signature) return false
    if (currentUrl && page_snapshot?.url && page_snapshot.url !== currentUrl) return false
    return true
  })

  if (action.action_type === 'navigate' || action.action_type === 'navigate_next_page') {
    return matchingCompleted.length >= 2
  }
  if (action.action_type === 'wait' || action.action_type === 'scroll') {
    const lastThree = completed.slice(-3)
    if (lastThree.length < 3) return false
    return lastThree.every(({ action: completedAction, result, page_snapshot }) => {
      if (!result.success || actionSignature(completedAction) !== signature) return false
      if (currentUrl && page_snapshot?.url && page_snapshot.url !== currentUrl) return false
      return true
    })
  }
  return matchingCompleted.length >= MAX_REPEATED_INTERACTIVE_ACTIONS
}

function nextAllowedActions(actions: SuggestedAction[], completed: CompletedAction[], currentUrl?: string): SuggestedAction[] {
  const allowed: SuggestedAction[] = []
  const seen = new Set<string>()
  for (const action of actions) {
    const signature = actionSignature(action)
    if (seen.has(signature)) continue
    seen.add(signature)
    if (!isRepeatedAction(action, completed, currentUrl)) {
      allowed.push(action)
    }
  }
  return allowed
}

export function shouldRequestSemanticRecovery(
  action: SuggestedAction,
  completed: CompletedAction[],
  postActionObservationAvailable = true,
): boolean {
  // Re-analysis is only useful when the mutated browser state can be observed.
  // Chrome error pages (for example ERR_CONNECTION_REFUSED/ERR_UNSAFE_PORT)
  // cannot be extracted by the content-script pipeline. Re-entering the loop
  // from the stale pre-action snapshot hides the real failure and can produce
  // a duplicate navigation attempt.
  if (!postActionObservationAvailable) return false
  if (action.safety_level !== 'safe' || actionRequiresExplicitApproval(action)) return false
  const latestMessage = String(completed[completed.length - 1]?.result?.message || '').toLowerCase()
  if (/frame with id .* showing error page|chrome-error:\/\/|extraction failed.*error page/.test(latestMessage)) return false
  if (/policy|confirmation|approval|may already have been dispatched|uncertain|privileged/.test(latestMessage)) return false
  const signature = actionSignature(action)
  const failures = completed.filter(({ action: priorAction, result }) =>
    !result.success && actionSignature(priorAction) === signature
  )
  return failures.length < 2
}

function repeatedClarificationQuestion(question: string | null | undefined, userInputs: string[]): string | null {
  if (!question) return null
  const repeatedQuestion = userInputs.some((input) =>
    input.toLowerCase().includes(`question: ${question}`.toLowerCase()),
  )
  return repeatedQuestion
    ? `I already have an answer for "${question}". If it is wrong, provide the corrected value; otherwise click Continue to retry using the saved answer.`
    : question
}

export function phaseContinuationActions(
  result: AnalyzeResponse,
  completed: CompletedAction[],
  currentUrl?: string,
): SuggestedAction[] {
  const directive = result.execution_orchestrator
  if (!directive || directive.should_replan) return []
  if (!Array.isArray(directive.continuation_actions)) return []
  return nextAllowedActions(directive.continuation_actions, completed, currentUrl)
}

function buildReportAnalysis(result: AnalyzeResponse): string {
  const parts = [result.analysis]
  const answer = result.report?.answer?.trim()
  const claim = result.report?.claim?.trim()
  if (answer) parts.push(`Report answer: ${answer}`)
  if (claim) parts.push(`Report claim: ${claim}`)
  return parts.filter(Boolean).join('\n\n')
}

function buildMissionResultAnalysis(result: MissionResult): string {
  return result.final_answer?.trim() || result.completion_reason || 'Mission result is ready.'
}

const REPORT_VALIDATION_REJECTION_TEXT = [
  'Report Validation',
  '',
  'Result:',
  'Rejected',
  '',
  'Reason:',
  'The previous report could not be verified against current page evidence.',
  '',
  'Planner Guidance:',
  '- continue gathering evidence',
  '- avoid repeating the rejected report unless page evidence changes',
  '- determine what information is still missing to satisfy the user goal',
].join('\n')

export function buildRejectedReportPriorStep(
  result: AnalyzeResponse,
  pageContext?: PageContext | null,
): PriorStep {
  const answer = result.report?.answer?.trim()
  const claim = result.report?.claim?.trim()
  const executionResult = [
    REPORT_VALIDATION_REJECTION_TEXT,
    answer ? `Rejected answer: ${answer.slice(0, 300)}` : '',
    claim ? `Rejected claim: ${claim.slice(0, 500)}` : '',
  ].filter(Boolean).join('\n\n')

  return {
    action_type: 'report_validation',
    description: 'Report Validation: rejected unsupported report',
    target_selector: null,
    value: null,
    execution_result: executionResult.slice(0, 1200),
    page_analysis: result.analysis.slice(0, MAX_ANALYSIS_SNAPSHOT_CHARS),
    page_url: pageContext?.url,
    page_title: pageContext?.title,
    page_metadata: pageContext?.metadata ? compactMetadata(pageContext.metadata) : {},
  }
}

function priorStepSignature(step: PriorStep): string {
  return [
    step.action_type,
    step.description,
    step.execution_result,
    step.page_url ?? '',
  ].join('|')
}

export function appendValidationPriorStepOnce(
  steps: PriorStep[],
  nextStep: PriorStep,
): PriorStep[] {
  const signature = priorStepSignature(nextStep)
  if (steps.some((step) => priorStepSignature(step) === signature)) return steps
  return [...steps, nextStep].slice(-5)
}

function buildReplanAnalysis(result: AnalyzeResponse): string {
  const reason = result.replan?.reason?.trim()
  return [result.analysis, reason ? `Replan reason: ${reason}` : 'Replan requested by planner.']
    .filter(Boolean)
    .join('\n\n')
}


export function routeAnalyzeOutcome(
  result: AnalyzeResponse,
  options: AnalyzeRoutingOptions,
): AnalyzeRoutingResult {
  const outcomeKind = result.outcome_kind ?? (result.clarification_question ? 'ask' : 'act')
  const allowedActions = nextAllowedActions(
    result.suggested_actions,
    options.completedActions,
    options.currentUrl,
  )
  const continuationActions = phaseContinuationActions(
    result,
    options.completedActions,
    options.currentUrl,
  )

  if (outcomeKind === 'ask') {
    return {
      phase: 'awaiting_user',
      analysisText: result.analysis,
      pendingActions: [],
      clarificationQuestion: repeatedClarificationQuestion(result.clarification_question, options.userInputs),
      contractOutcome: outcomeKind,
      report: null,
      replan: null,
      goalConvergence: Boolean(result.goal_convergence),
      error: null,
      continueAfterRejectedReport: false,
      continueAfterBackendStep: false,
      rejectedReportPriorStep: null,
    }
  }

  if (outcomeKind === 'report') {
    // Production SGV Phase 1: the backend already validated the claim against
    // live page evidence and set sgv_verified on the response.
    // Verified   → complete the workflow now.
    // Unverified → continue with the existing 'reported' phase so the loop
    //              proceeds exactly as it did before SGV existed.
    if (completionEvidenceValid({ sgvVerified: result.sgv_verified })) {
      return {
        phase: 'completed',
        analysisText: buildReportAnalysis(result),
        pendingActions: [],
        clarificationQuestion: null,
        contractOutcome: outcomeKind,
        report: result.report ?? null,
        replan: null,
        goalConvergence: Boolean(result.goal_convergence),
        error: null,
        continueAfterRejectedReport: false,
        continueAfterBackendStep: false,
        rejectedReportPriorStep: null,
      }
    }
    return {
      phase: 'refreshing',
      analysisText: buildReportAnalysis(result),
      pendingActions: [],
      clarificationQuestion: null,
      contractOutcome: outcomeKind,
      report: result.report ?? null,
      replan: null,
      goalConvergence: Boolean(result.goal_convergence),
      error: null,
      continueAfterRejectedReport: true,
      continueAfterBackendStep: false,
      rejectedReportPriorStep: buildRejectedReportPriorStep(result),
    }
  }

  if (outcomeKind === 'replan') {
    return {
      phase: 'replan',
      analysisText: buildReplanAnalysis(result),
      pendingActions: [],
      clarificationQuestion: null,
      contractOutcome: outcomeKind,
      report: null,
      replan: result.replan ?? null,
      goalConvergence: Boolean(result.goal_convergence),
      error: null,
      continueAfterRejectedReport: false,
      continueAfterBackendStep: false,
      rejectedReportPriorStep: null,
    }
  }

  if (allowedActions.length === 0) {
    if (result.intent_execution?.status === 'succeeded') {
      return {
        phase: 'refreshing',
        analysisText: [
          result.analysis,
          result.intent_execution.reason ? `Backend step completed: ${result.intent_execution.reason}` : '',
        ].filter(Boolean).join('\n\n'),
        pendingActions: [],
        clarificationQuestion: null,
        contractOutcome: outcomeKind,
        report: null,
        replan: null,
        goalConvergence: Boolean(result.goal_convergence),
        error: null,
        continueAfterRejectedReport: false,
        continueAfterBackendStep: true,
        rejectedReportPriorStep: null,
      }
    }
    return {
      phase: 'failed',
      analysisText: [
        result.analysis,
        'No executable browser action was returned, and no verified report/result was available.',
      ].filter(Boolean).join('\n\n'),
      pendingActions: [],
      clarificationQuestion: null,
      contractOutcome: outcomeKind,
      report: null,
      replan: null,
      goalConvergence: Boolean(result.goal_convergence),
      error: 'No executable browser action was returned before mission completion evidence was available.',
      continueAfterRejectedReport: false,
      continueAfterBackendStep: false,
      rejectedReportPriorStep: null,
    }
  }

  const queuedActions = [...allowedActions, ...continuationActions]

  return {
    phase: 'awaiting_execution',
    analysisText: result.analysis,
    pendingActions: queuedActions.slice(0, 1),
    clarificationQuestion: null,
    contractOutcome: outcomeKind,
    report: null,
    replan: null,
    goalConvergence: Boolean(result.goal_convergence),
    error: null,
    continueAfterRejectedReport: false,
    continueAfterBackendStep: false,
    rejectedReportPriorStep: null,
  }
}

export function cancelWorkflowPatch(): Pick<WorkflowState, 'pendingActions' | 'phase'> {
  return { pendingActions: [], phase: 'cancelled' }
}
function logEvent(
  sessionId: string,
  eventType: 'approved' | 'rejected' | 'executed',
  action: SuggestedAction,
  pageContext: PageContext | null,
  executionResult?: string,
  attachIntent = true,
) {
  fetch(`${BACKEND_URL}/workflow/log`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      intent_id: attachIntent ? action.intent_id ?? null : null,
      event_type: eventType,
      action,
      tab_url: pageContext?.url ?? '',
      tab_title: pageContext?.title ?? '',
      execution_result: executionResult,
    }),
  }).catch(console.error)
}

async function updateIntentEvidence(
  sessionId: string,
  task: string,
  action: SuggestedAction,
  pageContext: PageContext | null,
  result: ExecutionResult,
): Promise<{ nextIntent: IntentDTO | null; updated: boolean }> {
  if (!action.intent_id) return { nextIntent: null, updated: false }
  const response = await fetch(`${BACKEND_URL}/intent/update`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mission_id: action.mission_id ?? sessionId,
      intent_id: action.intent_id,
      outcome: result.success ? 'success' : 'failure',
      evidence: {
        evidence_type: 'browser_execution',
        success: result.success,
        message: result.success ? 'success' : result.message,
        payload: {
          task,
          page_context: pageContext,
          action_type: action.action_type,
          target_selector: action.target_selector,
          value: action.value,
          execution_result: result,
        },
        browser_metadata: {
          tab_url: pageContext?.url ?? '',
          tab_title: pageContext?.title ?? '',
        },
        provider_metadata: {
          provider: 'browser_control',
        },
        runtime_resource_updates: [],
      },
    }),
  }).catch((err) => {
    console.error(err)
    return null
  })
  if (!response || !response.ok) return { nextIntent: null, updated: false }
  const data = await response.json().catch(() => null) as IntentUpdateResponse | null
  return { nextIntent: data?.next_intent ?? null, updated: Boolean(data?.updated) }
}

async function requestNextBrowserIntent(sessionId: string): Promise<IntentDTO | null> {
  const response = await fetch(`${BACKEND_URL}/intent/next`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mission_id: sessionId,
      provider: 'browser_control',
    }),
  }).catch((err) => {
    console.error(err)
    return null
  })
  if (!response || !response.ok) return null
  const data = await response.json().catch(() => null) as IntentNextResponse | null
  return data?.intent ?? null
}

async function fetchMissionResult(sessionId: string): Promise<MissionResult | null> {
  const response = await fetch(`${BACKEND_URL}/mission/${encodeURIComponent(sessionId)}/result`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  }).catch((err) => {
    console.error(err)
    return null
  })
  if (!response || response.status === 404 || !response.ok) return null
  return await response.json().catch(() => null) as MissionResult | null
}

function actionFromIntent(intent: IntentDTO): SuggestedAction {
  const payload = intent.payload ?? {}
  const rawSafety = payload.safety_level
  const safety_level =
    rawSafety === 'danger' || rawSafety === 'caution' || rawSafety === 'safe'
      ? rawSafety
      : 'safe'
  const rawValue = payload.value
  const value = rawValue === undefined || rawValue === null ? null : String(rawValue)

  return {
    action_id: String(payload.action_id ?? intent.intent_id),
    intent_id: intent.intent_id,
    mission_id: intent.mission_id,
    action_type: String(payload.action_type ?? intent.intent),
    target_selector: String(payload.target_selector ?? ''),
    value,
    description: String(payload.description ?? intent.intent),
    reasoning: String(payload.reasoning ?? `Assigned by mission ledger intent ${intent.intent_id}`),
    confidence: typeof payload.confidence === 'number' ? payload.confidence : 0.8,
    safety_level,
  }
}

export function useWorkflow() {
  const [state, setState] = useState<WorkflowState>({
    sessionId: crypto.randomUUID(),
    task: '',
    analysisText: '',
    pendingActions: [],
    activeAction: null,
    completedActions: [],
    validationPriorSteps: [],
    workspace: null,
    tabWorkspace: null,
    missionSnapshot: null,
    userInputs: [],
    clarificationQuestion: null,
    contractOutcome: null,
    report: null,
    replan: null,
    goalConvergence: false,
    phase: 'idle',
    error: null,
  })

  // Keep a ref-style snapshot of the latest page context for logging.
  // We don't need it in render, so it doesn't live in state.
  const [pageContext, setPageContext] = useState<PageContext | null>(null)
  const durableLedgerRef = useRef<DurableWorkflowLedger | null>(null)
  const durableLedgerLoadedRef = useRef(false)

  useEffect(() => {
    let cancelled = false
    void loadDurableLedger().then(async (stored) => {
      if (cancelled) return
      if (stored) {
        const restored = normalizeLedgerAfterRestart(stored)
        durableLedgerRef.current = restored
        setState(restored.workflow)
        await saveDurableLedger(restored)
      }
      durableLedgerLoadedRef.current = true
    }).catch((error) => {
      console.error('Durable workflow restore failed', error)
      durableLedgerLoadedRef.current = true
    })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (!durableLedgerLoadedRef.current) return
    const ledger = checkpointDurableLedger(durableLedgerRef.current, state)
    durableLedgerRef.current = ledger
    void saveDurableLedger(ledger).catch((error) => {
      console.error('Durable workflow checkpoint failed', error)
    })
  }, [state])

  const setTask = useCallback((task: string) => {
    setState((s) => ({ ...s, task, error: null }))
  }, [])

  // ── Initial analysis ────────────────────────────────────────────────────────

  const runWorkflowLoop = useCallback(async ({
    sessionId,
    task,
    completedActions,
    validationPriorSteps,
    workspace,
    tabWorkspace,
    userInputs,
    refresh,
  }: WorkflowLoopInput) => {
    setState((s) => ({
      ...s,
      phase: workflowLoopObservationPhase(refresh),
      pendingActions: [],
      activeAction: null,
      clarificationQuestion: null,
      contractOutcome: null,
      report: null,
      replan: null,
      goalConvergence: false,
      error: null,
    }))

    let ctx: PageContext
    try {
      const observationAttempts = completedActions.length === 0 ? initialObservationAttempts(task) : 1
      let bestContext: PageContext | null = null
      let observationError = ''
      for (let attempt = 0; attempt < observationAttempts; attempt += 1) {
        const res = await sendToBackground<{ context?: PageContext; error?: string }>({
          type: 'EXTRACT_CONTEXT',
        })
        if (res.context) {
          bestContext = selectRicherPageContext(bestContext, res.context)
          if (pageContextHasNamedEditableControl(res.context)) break
        } else {
          observationError = res.error ?? 'Failed to read page.'
        }
        if (attempt + 1 < observationAttempts) {
          await withTimeout(
            sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_DOM_SETTLE' }),
            POST_ACTION_TIMEOUT_MS,
            'initial DOM settle wait',
          )
        }
      }
      if (!bestContext) {
        const friendly = meaningfulWorkflowFailure(
          observationError || 'Failed to read page.',
          'observation',
        )
        setState((s) => ({
          ...s,
          phase: 'failed',
          pendingActions: [],
          activeAction: null,
          analysisText: friendly.userMessage,
          error: friendly.userMessage,
        }))
        return
      }
      ctx = bestContext
      setPageContext(ctx)
    } catch (err) {
      const rawError = errMsg(err)
      console.error('[Workflow] Observation failed', rawError)
      const friendly = meaningfulWorkflowFailure(rawError, 'observation')
      setState((s) => ({
        ...s,
        phase: 'failed',
        pendingActions: [],
        activeAction: null,
        analysisText: friendly.userMessage,
        error: friendly.userMessage,
      }))
      return
    }

    const updatedWorkspace = updateTaskWorkspace(
      workspace ?? createTaskWorkspace(task),
      ctx,
      completedActions,
    )
    let updatedTabWorkspace = tabWorkspace
    try {
      const tabResponse = await sendToBackground<{ tab_workspace?: MultiTabWorkspace; error?: string }>({
        type: 'GET_TAB_WORKSPACE',
      })
      const snapshot = tabResponse.tab_workspace ?? tabWorkspace
      updatedTabWorkspace = snapshot
        ? updateTabFactCount(snapshot, ctx.tab_id, updatedWorkspace.extractedFacts.length)
        : null
    } catch {
      updatedTabWorkspace = tabWorkspace
    }
    const updatedMissionSnapshot = updateMissionSnapshot({
      goal: task,
      workspace: updatedWorkspace,
      tabWorkspace: updatedTabWorkspace,
      completedActions,
      validationPriorSteps,
      goalConvergence: false,
    })

    setState((s) => ({ ...s, phase: 'analyzing' }))
    try {
      const response = await fetchAnalyzeWithRetry(
        `${BACKEND_URL}/analyze`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(buildAnalyzeRequestBody(
            sessionId,
            task,
            ctx,
            completedActions,
            userInputs,
            updatedWorkspace,
            updatedTabWorkspace,
            validationPriorSteps,
            updatedMissionSnapshot,
          )),
        },
      )
      if (!response.ok) {
        const errBody = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
        const detail = Array.isArray(errBody.detail)
          ? errBody.detail.map((e: { msg?: string; loc?: string[] }) =>
              `${(e.loc ?? []).slice(-1)[0] ?? 'field'}: ${e.msg ?? JSON.stringify(e)}`
            ).join(' | ')
          : formatErrorDetail(errBody.detail, `HTTP ${response.status}`)
        throw new Error(detail)
      }
      const result: AnalyzeResponse = await response.json()
      const routed = routeAnalyzeOutcome(result, {
        completedActions,
        currentUrl: ctx.url,
        userInputs,
        includeReanalysisErrors: refresh,
      })
      if (routed.phase === 'awaiting_execution' && routed.pendingActions.length === 0) {
        const nextIntent = await requestNextBrowserIntent(sessionId)
        if (nextIntent) {
          routed.pendingActions = [actionFromIntent(nextIntent)]
        } else {
          routed.phase = 'failed'
          routed.analysisText = [
            routed.analysisText,
            'Mission Ledger has no browser intent awaiting execution before completion evidence was available.',
          ].filter(Boolean).join('\n\n')
          routed.error = 'No executable browser action was available after analysis.'
        }
      }
      setState((s) => ({
        ...s,
        completedActions,
        validationPriorSteps,
        workspace: updatedWorkspace,
        tabWorkspace: updatedTabWorkspace,
        missionSnapshot: routed.contractOutcome === 'report' && result.sgv_verified
          ? updateMissionSnapshot({
              goal: task,
              workspace: updatedWorkspace,
              tabWorkspace: updatedTabWorkspace,
              completedActions,
              validationPriorSteps,
              verifiedReport: true,
              goalConvergence: routed.goalConvergence,
            })
          : updateMissionSnapshot({
              goal: task,
              workspace: updatedWorkspace,
              tabWorkspace: updatedTabWorkspace,
              completedActions,
              validationPriorSteps,
              goalConvergence: routed.goalConvergence,
            }),
        userInputs,
        ...routed,
      }))
      if (routed.continueAfterRejectedReport && routed.rejectedReportPriorStep) {
        const nextValidationPriorSteps = appendValidationPriorStepOnce(
          validationPriorSteps,
          buildRejectedReportPriorStep(result, ctx),
        )
        await runWorkflowLoop({
          sessionId,
          task,
          completedActions,
          validationPriorSteps: nextValidationPriorSteps,
          workspace: updatedWorkspace,
          tabWorkspace: updatedTabWorkspace,
          userInputs,
          refresh: true,
        })
      }
      if (routed.continueAfterBackendStep) {
        const backendStep = buildBackendIntentPriorStep(result, ctx)
        const nextValidationPriorSteps = backendStep
          ? appendValidationPriorStepOnce(validationPriorSteps, backendStep)
          : validationPriorSteps
        await runWorkflowLoop({
          sessionId,
          task,
          completedActions,
          validationPriorSteps: nextValidationPriorSteps,
          workspace: updatedWorkspace,
          tabWorkspace: updatedTabWorkspace,
          userInputs,
          refresh: true,
        })
      }
    } catch (err) {
      const rawError = errMsg(err)
      console.error('[Workflow] Analysis failed', rawError)
      const friendly = meaningfulWorkflowFailure(rawError, 'analysis')
      setState((s) => ({
        ...s,
        phase: 'failed',
        pendingActions: [],
        activeAction: null,
        analysisText: friendly.userMessage,
        error: friendly.userMessage,
      }))
    }
  }, [])

  const analyze = useCallback(async (taskOverride?: string) => {
    // taskOverride lets voice input bypass the stale closure on state.task.
    const task = (taskOverride ?? state.task).trim()
    if (!task) return
    // A submitted task is a new mission, not a continuation of a restored one.
    // Reusing the previous session id lets the backend mission ledger return a
    // stale intent from an unrelated task. Resume/continue paths intentionally
    // retain their current session id; only Analyze rotates it.
    const sessionId = createFreshWorkflowSessionId()
    const workspace = createTaskWorkspace(task)
    const missionSnapshot = createMissionSnapshot(task)

    setState((s) => ({
      ...s,
      sessionId,
      task,           // Sync state.task if voice provided an override.
      phase: 'observing',
      error: null,
      analysisText: '',
      pendingActions: [],
      activeAction: null,
      completedActions: [],
      validationPriorSteps: [],
      workspace,
      tabWorkspace: null,
      missionSnapshot,
      userInputs: [],
      clarificationQuestion: null,
      contractOutcome: null,
      report: null,
      replan: null,
      goalConvergence: false,
    }))

    const initialLedgerState: WorkflowState = {
      ...state,
      sessionId,
      task,
      phase: 'observing',
      error: null,
      analysisText: '',
      pendingActions: [],
      activeAction: null,
      completedActions: [],
      validationPriorSteps: [],
      workspace,
      tabWorkspace: null,
      missionSnapshot,
      userInputs: [],
      clarificationQuestion: null,
      contractOutcome: null,
      report: null,
      replan: null,
      goalConvergence: false,
    }
    durableLedgerRef.current = createDurableLedger(initialLedgerState)
    await saveDurableLedger(durableLedgerRef.current)

    await runWorkflowLoop({
      sessionId,
      task,
      completedActions: [],
      validationPriorSteps: [],
      workspace,
      tabWorkspace: null,
      userInputs: [],
      refresh: false,
    })
  }, [runWorkflowLoop, state.task])

  // ── Re-analysis after a step ────────────────────────────────────────────────


  // ── Approve ─────────────────────────────────────────────────────────────────

  const approveAction = useCallback(async (approvalSource: ExecutionMode = 'manual') => {
    const {
      pendingActions,
      sessionId,
      task,
      completedActions,
      analysisText,
      validationPriorSteps,
      workspace,
      tabWorkspace,
      userInputs,
    } = state
    const pendingAction = pendingActions[0]
    if (!pendingAction) return
    const action = pageContext ? bindObservationGrounding(pendingAction, pageContext) : pendingAction

    setState((s) => ({
      ...s,
      activeAction: action,
      pendingActions: [],
      phase: 'executing',
    }))

    logEvent(sessionId, 'approved', action, pageContext)

    // Execute on live page
    let result: ExecutionResult
    let durableExecutionKey: string | null = null
    let executionLedger = durableLedgerRef.current ?? createDurableLedger(state)
    try {
      if (typeof pageContext?.tab_id !== 'number') {
        throw new Error('Browser action is not grounded to an observed tab. Refresh the page context and retry.')
      }

      while (true) {
        const reservation = reserveDurableExecution(
          executionLedger,
          action,
          pageContext.tab_id,
          approvalSource,
        )
        if (!reservation.accepted) {
          if (reservation.reason === 'already_succeeded' && reservation.record.result) {
            result = reservation.record.result
            break
          }
          throw new Error(
            reservation.reason === 'uncertain_prior_dispatch'
              ? 'This action may already have been dispatched before a restart, so it was not repeated. Resume from a fresh page observation.'
              : 'The bounded retry limit was reached for this action.',
          )
        }

        executionLedger = reservation.ledger
        durableExecutionKey = reservation.record.key
        durableLedgerRef.current = executionLedger
        await saveDurableLedger(executionLedger)

        const contract = buildCanonicalActionContract(action, pageContext, reservation.record.key)
        const policyContext = await preparePolicyExecution(sessionId, action, pageContext, approvalSource, contract)
        const res = await withTimeout(
          sendToBackground<{ result?: ExecutionResult; error?: string }>({
            type: 'EXECUTE_ACTION',
            contract,
            policy_context: policyContext,
          }),
          ACTION_EXECUTION_TIMEOUT_MS,
          `${action.action_type} execution`,
        )
        result = res.result ?? {
          success: false,
          message: res.error ?? 'Execution returned no result.',
          action_id: action.action_id,
        }
        if (result.success) break

        executionLedger = completeDurableExecution(executionLedger, reservation.record.key, result)
        durableLedgerRef.current = executionLedger
        await saveDurableLedger(executionLedger)
        if (!reservation.record.retryable || reservation.record.attempts >= MAX_REVERSIBLE_ATTEMPTS) break
      }
    } catch (err) {
      result = { success: false, message: errMsg(err), action_id: action.action_id }
    }

    let pageContextAfterAction = pageContext
    let postActionObservationAvailable = true

    if (result.success) {
      if (result.page_context) {
        pageContextAfterAction = result.page_context
        setPageContext(result.page_context)
      } else if (action.action_type === 'open_new_tab' && typeof result.opened_tab_id === 'number') {
        try {
          const res = await withTimeout(
            sendToBackground<{ context?: PageContext; error?: string }>({
              type: 'EXTRACT_CONTEXT',
              tab_id: result.opened_tab_id,
            }),
            POST_ACTION_TIMEOUT_MS,
            'opened tab context extraction',
          )
          if (res.context) {
            pageContextAfterAction = res.context
            setPageContext(res.context)
          }
        } catch {
          // The execution result remains authoritative; evidence falls back to the prior context below.
        }
      }

      try {
        if (action.action_type === 'navigate' || action.action_type === 'navigate_next_page') {
          await withTimeout(
            sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_TAB_LOAD' }),
            POST_ACTION_TIMEOUT_MS,
            'tab load wait',
          )
        }

        if (actionRequiresDomSettle(action.action_type)) {
          await withTimeout(
            sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_DOM_SETTLE' }),
            POST_ACTION_TIMEOUT_MS,
            'DOM settle wait',
          )
        }
      } catch (err) {
        result = {
          success: false,
          message: `Post-action wait failed after ${action.action_type}: ${errMsg(err)}`,
          action_id: action.action_id,
        }
      }

      if (result.success && actionNeedsObservableProgress(action)) {
        try {
          const isNavigation = action.action_type === 'navigate' || action.action_type === 'navigate_next_page'
          const observationAttempts = isNavigation ? postNavigationObservationAttempts(task) : 1
          let bestContext: PageContext | null = null
          let extractionError = ''
          for (let attempt = 0; attempt < observationAttempts; attempt += 1) {
            const res = await withTimeout(
              sendToBackground<{ context?: PageContext; error?: string }>({
                type: 'EXTRACT_CONTEXT',
              }),
              POST_ACTION_TIMEOUT_MS,
              'post-action context extraction',
            )
            if (res.context) {
              bestContext = selectRicherPageContext(bestContext, res.context)
              if (isNavigation && pageContextHasNamedEditableControl(res.context)) break
            } else {
              extractionError = res.error ?? 'page read failed'
            }
            if (attempt + 1 < observationAttempts) {
              await withTimeout(
                sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_DOM_SETTLE' }),
                POST_ACTION_TIMEOUT_MS,
                'post-navigation DOM settle wait',
              )
            }
          }
          if (bestContext) {
            const progressError = validateObservableProgress(action, pageContext, bestContext, result)
            const semanticMismatch = detectExecutionSemanticMismatch(action, pageContext, bestContext)
            pageContextAfterAction = bestContext
            setPageContext(bestContext)
            if (semanticMismatch) {
              result = {
                ...result,
                ...semanticMismatch,
              }
            }
            if (progressError) {
              result = {
                success: false,
                message: progressError,
                action_id: action.action_id,
              }
            }
          } else {
            postActionObservationAvailable = false
            result = {
              success: false,
              message: `Could not verify page progress after ${action.action_type}: ${extractionError || 'page read failed'}`,
              action_id: action.action_id,
            }
          }
        } catch (err) {
          postActionObservationAvailable = false
          result = {
            success: false,
            message: `Could not verify page progress after ${action.action_type}: ${errMsg(err)}`,
            action_id: action.action_id,
          }
        }
      }
    }

    const newCompleted: CompletedAction[] = [
      ...completedActions,
      {
        action,
        result,
        analysis_snapshot: analysisText,
        page_snapshot: pageContextAfterAction
          ? {
              url: pageContextAfterAction.url,
              title: pageContextAfterAction.title,
              metadata: compactMetadata(pageContextAfterAction.metadata),
            }
          : undefined,
      },
    ]

    setState((s) => ({ ...s, activeAction: null, completedActions: newCompleted }))

    const intentUpdate = await withTimeout(
      updateIntentEvidence(sessionId, task, action, pageContextAfterAction, result),
      INTENT_UPDATE_TIMEOUT_MS,
      'intent evidence update',
    ).catch((err) => {
      console.error(err)
      return { nextIntent: null, updated: false }
    })
    const nextIntent = intentUpdate.nextIntent
    logEvent(sessionId, 'executed', action, pageContextAfterAction,
      result.success ? 'success' : result.message, !intentUpdate.updated)

    if (!result.success) {
      const friendly = meaningfulWorkflowFailure(result.message || 'Intent execution failed.', 'execution', action.description)
      if (friendly.retryable && shouldRequestSemanticRecovery(action, newCompleted, postActionObservationAvailable)) {
        setState((s) => ({
          ...s,
          phase: 'refreshing',
          activeAction: null,
          pendingActions: [],
          completedActions: newCompleted,
          analysisText: `${analysisText}\n\n${friendly.userMessage}`,
          error: null,
        }))
        await runWorkflowLoop({
          sessionId,
          task,
          refresh: true,
          completedActions: newCompleted,
          validationPriorSteps,
          workspace,
          tabWorkspace,
          userInputs,
        })
        return
      }
      setState((s) => ({
        ...s,
        phase: 'failed',
        activeAction: null,
        pendingActions: [],
        completedActions: newCompleted,
        analysisText: `${analysisText}\n\n${friendly.userMessage}`,
        error: friendly.userMessage,
      }))
      return
    }

    if (durableExecutionKey) {
      executionLedger = completeDurableExecution(executionLedger, durableExecutionKey, result)
      durableLedgerRef.current = executionLedger
      await saveDurableLedger(executionLedger)
    }

    const exactOpenCompletion = exactOpenOnlyCompletion(task, action, result)
    if (exactOpenCompletion) {
      const label = exactOpenCompletion.targetKind === 'chat' ? 'WhatsApp chat' : exactOpenCompletion.targetKind
      setState((s) => ({
        ...s,
        phase: 'completed',
        activeAction: null,
        pendingActions: [],
        completedActions: newCompleted,
        analysisText: `Verified the exact ${label} "${exactOpenCompletion.targetName}" and stopped because no further action was requested.`,
        contractOutcome: 'report',
        report: {
          answer: `Opened and verified the exact ${label} "${exactOpenCompletion.targetName}". Nothing was typed, attached, or sent.`,
          claim: `Trusted post-click verification observed the exact ${exactOpenCompletion.targetKind} identity "${exactOpenCompletion.targetName}".`,
        },
        goalConvergence: true,
        error: null,
      }))
      return
    }

    if (nextIntent) {
      const nextAction = actionFromIntent(nextIntent)
      setState((s) => ({
        ...s,
        phase: 'awaiting_execution',
        activeAction: null,
        pendingActions: [nextAction],
        completedActions: newCompleted,
        error: null,
      }))
      return
    }

    const missionResult = await withTimeout(
      fetchMissionResult(sessionId),
      POST_ACTION_TIMEOUT_MS,
      'mission result fetch',
    ).catch((err) => {
      console.error(err)
      return null
    })
    if (missionResult && completionEvidenceValid({ missionResultAvailable: true })) {
      setState((s) => ({
        ...s,
        phase: 'completed',
        activeAction: null,
        pendingActions: [],
        completedActions: newCompleted,
        analysisText: buildMissionResultAnalysis(missionResult),
        contractOutcome: 'report',
        report: {
          answer: missionResult.final_answer,
          claim: missionResult.completion_reason,
        },
        goalConvergence: true,
        error: null,
      }))
      return
    }

    await runWorkflowLoop({
      sessionId,
      task,
      refresh: true,
      completedActions: newCompleted,
      validationPriorSteps,
      workspace,
      tabWorkspace,
      userInputs,
    })
  }, [state, pageContext])

  const continueWithInput = useCallback(async (answer: string) => {
    const trimmed = answer.trim()
    if (!trimmed) return

    const { sessionId, task, completedActions, validationPriorSteps, workspace, tabWorkspace, userInputs } = state
    const currentQuestion = state.clarificationQuestion || 'Missing information'
    const nextInputs = [
      ...userInputs,
      `Question: ${currentQuestion}\nAnswer: ${trimmed}`,
    ]
    setState((s) => ({
      ...s,
      userInputs: nextInputs,
      clarificationQuestion: null,
      error: null,
    }))
    await runWorkflowLoop({
      sessionId,
      task,
      completedActions,
      validationPriorSteps,
      workspace,
      tabWorkspace,
      userInputs: nextInputs,
      refresh: true,
    })
  }, [state, runWorkflowLoop])

  // ── Reject ──────────────────────────────────────────────────────────────────

  const rejectAction = useCallback(() => {
    const { pendingActions, sessionId } = state
    const action = pendingActions[0]
    if (!action) return

    logEvent(sessionId, 'rejected', action, pageContext)

    // Rejecting stops the remaining queue
    setState((s) => ({ ...s, ...cancelWorkflowPatch() }))
  }, [state, pageContext])

  // ── Stop ────────────────────────────────────────────────────────────────────

  const stopWorkflow = useCallback(() => {
    setState((s) => ({ ...s, ...cancelWorkflowPatch() }))
  }, [])

  const resumeWorkflow = useCallback(async () => {
    const { sessionId, task, completedActions, validationPriorSteps, workspace, tabWorkspace, userInputs } = state
    if (!task.trim()) return
    await runWorkflowLoop({
      sessionId,
      task,
      completedActions,
      validationPriorSteps,
      workspace,
      tabWorkspace,
      userInputs,
      refresh: true,
    })
  }, [state, runWorkflowLoop])

  // ── Reset ───────────────────────────────────────────────────────────────────

  const reset = useCallback(() => {
    setPageContext(null)
    setState((s) => ({
      ...s,
      sessionId: crypto.randomUUID(),
      task: '',
      analysisText: '',
      pendingActions: [],
      activeAction: null,
      completedActions: [],
      validationPriorSteps: [],
      workspace: null,
      tabWorkspace: null,
      missionSnapshot: null,
      userInputs: [],
      clarificationQuestion: null,
      contractOutcome: null,
      report: null,
      replan: null,
      goalConvergence: false,
      phase: 'idle',
      error: null,
    }))
    durableLedgerRef.current = null
    void clearDurableLedger().catch((error) => console.error('Durable workflow reset failed', error))
  }, [])

  return { state, setTask, analyze, approveAction, rejectAction, stopWorkflow, resumeWorkflow, reset, continueWithInput }
}

export function createFreshWorkflowSessionId(): string {
  return crypto.randomUUID()
}
