import { useState, useCallback } from 'react'
import { sendToBackground } from '../../utils/messaging'
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
} from '../../types'

const BACKEND_URL = 'http://localhost:8000'
const ANALYZE_TIMEOUT_MS = 90_000
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
  pendingActions: SuggestedAction[]   // [0] = next to approve, rest = queued
  activeAction: SuggestedAction | null // Currently executing
  completedActions: CompletedAction[]
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

function actionNeedsObservableProgress(action: SuggestedAction): boolean {
  if (action.action_type === 'navigate') return true
  if (action.action_type !== 'click') return false
  return !/\b(focus|prepare|place (?:the )?cursor|click (?:on )?(?:the )?(?:input|field))\b/i.test(
    action.description,
  )
}

function validateObservableProgress(
  action: SuggestedAction,
  before: PageContext | null,
  after: PageContext,
): string | null {
  if (!before || !actionNeedsObservableProgress(action)) return null

  const changed = contextFingerprint(before) !== contextFingerprint(after)
  const navigated = before.url !== after.url
  if (navigated || changed) return null

  return `Action reported success, but the page did not visibly change after ${action.action_type}. Retrying from the current page state.`
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
  }
  })
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
  return {
    session_id: sessionId,
    task,
    page_context: pageContext,
    prior_steps: priorSteps.length > 0 ? priorSteps : undefined,
    supplemental_context: buildSupplementalContext(task, userInputs, workspace, tabWorkspace, missionSnapshot),
  }
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

  if (action.action_type === 'navigate') return matchingCompleted.length >= 2
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
  const nextAction = actions[0]
  if (!nextAction) return []
  return isRepeatedAction(nextAction, completed, currentUrl) ? [] : [nextAction]
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

function buildReportAnalysis(result: AnalyzeResponse): string {
  const parts = [result.analysis]
  const answer = result.report?.answer?.trim()
  const claim = result.report?.claim?.trim()
  if (answer) parts.push(`Report answer: ${answer}`)
  if (claim) parts.push(`Report claim: ${claim}`)
  return parts.filter(Boolean).join('\n\n')
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
      rejectedReportPriorStep: null,
    }
  }

  if (outcomeKind === 'report') {
    // Production SGV Phase 1: the backend already validated the claim against
    // live page evidence and set sgv_verified on the response.
    // Verified   → complete the workflow now.
    // Unverified → continue with the existing 'reported' phase so the loop
    //              proceeds exactly as it did before SGV existed.
    if (result.sgv_verified) {
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
      rejectedReportPriorStep: null,
    }
  }

  if (allowedActions.length === 0) {
    const stoppedRepeat = result.suggested_actions.length > 0
    const unresolvedFailure = options.completedActions.some(({ result: execution }) => !execution.success)
    return {
      phase: 'completed',
      analysisText: result.analysis,
      pendingActions: [],
      clarificationQuestion: null,
      contractOutcome: outcomeKind,
      report: null,
      replan: null,
      goalConvergence: Boolean(result.goal_convergence),
      error: options.includeReanalysisErrors
        ? stoppedRepeat
          ? 'Stopped because the assistant proposed a repeated browser action instead of making progress.'
          : unresolvedFailure
            ? 'Stopped with unresolved failed actions. The task was not completed.'
            : null
        : null,
      continueAfterRejectedReport: false,
      rejectedReportPriorStep: null,
    }
  }

  return {
    phase: 'awaiting_execution',
    analysisText: result.analysis,
    pendingActions: allowedActions,
    clarificationQuestion: null,
    contractOutcome: outcomeKind,
    report: null,
    replan: null,
    goalConvergence: Boolean(result.goal_convergence),
    error: null,
    continueAfterRejectedReport: false,
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
) {
  fetch(`${BACKEND_URL}/workflow/log`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      event_type: eventType,
      action,
      tab_url: pageContext?.url ?? '',
      tab_title: pageContext?.title ?? '',
      execution_result: executionResult,
    }),
  }).catch(console.error)
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
      const res = await sendToBackground<{ context?: PageContext; error?: string }>({
        type: 'EXTRACT_CONTEXT',
      })
      if (!res.context) {
        setState((s) => ({
          ...s,
          phase: 'failed',
          pendingActions: [],
          activeAction: null,
          error: `${refresh ? 'Refresh' : 'Observation'} failed: ${res.error ?? 'Failed to read page.'}`,
        }))
        return
      }
      ctx = res.context
      setPageContext(ctx)
    } catch (err) {
      setState((s) => ({
        ...s,
        phase: 'failed',
        pendingActions: [],
        activeAction: null,
        error: `${refresh ? 'Refresh' : 'Observation'} error: ${errMsg(err)}`,
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
    } catch (err) {
      setState((s) => ({
        ...s,
        phase: 'failed',
        pendingActions: [],
        activeAction: null,
        error: `Analysis failed: ${errMsg(err)}`,
      }))
    }
  }, [])

  const analyze = useCallback(async (taskOverride?: string) => {
    const { sessionId } = state
    // taskOverride lets voice input bypass the stale closure on state.task.
    const task = (taskOverride ?? state.task).trim()
    if (!task) return
    const workspace = createTaskWorkspace(task)
    const missionSnapshot = createMissionSnapshot(task)

    setState((s) => ({
      ...s,
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
  }, [runWorkflowLoop, state.task, state.sessionId])

  // ── Re-analysis after a step ────────────────────────────────────────────────


  // ── Approve ─────────────────────────────────────────────────────────────────

  const approveAction = useCallback(async () => {
    const { pendingActions, sessionId, task, completedActions, validationPriorSteps, workspace, tabWorkspace, analysisText, userInputs } = state
    const action = pendingActions[0]
    if (!action) return

    // Snapshot remaining queue before state update
    const remaining = pendingActions.slice(1)

    // Move action to "executing"
    setState((s) => ({
      ...s,
      activeAction: action,
      pendingActions: remaining,
      phase: 'executing',
    }))

    logEvent(sessionId, 'approved', action, pageContext)

    // Execute on live page
    let result: ExecutionResult
    try {
      const res = await sendToBackground<{ result?: ExecutionResult; error?: string }>({
        type: 'EXECUTE_ACTION',
        action,
      })
      result = res.result ?? {
        success: false,
        message: res.error ?? 'Execution returned no result.',
        action_id: action.action_id,
      }
    } catch (err) {
      result = { success: false, message: errMsg(err), action_id: action.action_id }
    }

    let pageContextAfterAction = pageContext

    if (result.success) {
      if (action.action_type === 'navigate') {
        await sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_TAB_LOAD' })
      }

      if (
        action.action_type === 'fill' ||
        action.action_type === 'click' ||
        action.action_type === 'wait' ||
        action.action_type === 'select_option' ||
        action.action_type === 'choose_date' ||
        action.action_type === 'keyboard_shortcut'
      ) {
        await sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_DOM_SETTLE' })
      }

      if (actionNeedsObservableProgress(action)) {
        try {
          const res = await sendToBackground<{ context?: PageContext; error?: string }>({
            type: 'EXTRACT_CONTEXT',
          })
          if (res.context) {
            const progressError = validateObservableProgress(action, pageContext, res.context)
            const semanticMismatch = detectExecutionSemanticMismatch(action, pageContext, res.context)
            pageContextAfterAction = res.context
            setPageContext(res.context)
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
            result = {
              success: false,
              message: `Could not verify page progress after ${action.action_type}: ${res.error ?? 'page read failed'}`,
              action_id: action.action_id,
            }
          }
        } catch (err) {
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

    logEvent(sessionId, 'executed', action, pageContextAfterAction,
      result.success ? 'success' : result.message)

    if (!result.success) {
      await runWorkflowLoop({
        sessionId,
        task,
        completedActions: newCompleted,
        validationPriorSteps,
        workspace,
        tabWorkspace,
        userInputs,
        refresh: true,
      })
      return
    }

    await runWorkflowLoop({
      sessionId,
      task,
      completedActions: newCompleted,
      validationPriorSteps,
      workspace,
      tabWorkspace,
      userInputs,
      refresh: true,
    })
  }, [state, pageContext, runWorkflowLoop])

  const continueWithInput = useCallback(async (answer: string) => {
    const trimmed = answer.trim()
    if (!trimmed) return

    const { sessionId, task, completedActions, validationPriorSteps, workspace, tabWorkspace, userInputs } = state
    if (/^(done|complete|completed|finished)$/i.test(trimmed)) {
      setState((s) => ({
        ...s,
        phase: 'completed',
        clarificationQuestion: null,
        error: null,
      }))
      return
    }

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

  // ── Reset ───────────────────────────────────────────────────────────────────

  const reset = useCallback(() => {
    setPageContext(null)
    setState((s) => ({
      ...s,
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
  }, [])

  return { state, setTask, analyze, approveAction, rejectAction, stopWorkflow, reset, continueWithInput }
}
