import { useState, useCallback } from 'react'
import { sendToBackground } from '../../utils/messaging'
import type {
  PageContext,
  AnalyzeResponse,
  SuggestedAction,
  ExecutionResult,
  CompletedAction,
  PriorStep,
} from '../../types'

const BACKEND_URL = 'http://localhost:8000'
const ANALYZE_TIMEOUT_MS = 90_000
const MAX_DETAILED_PRIOR_STEPS = 30
const MAX_TOTAL_PRIOR_STEPS = 30
const MAX_ANALYSIS_SNAPSHOT_CHARS = 1000
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

// Phase describes what the workflow engine is currently doing.
export type WorkflowPhase =
  | 'idle'         // Nothing started yet
  | 'extracting'   // Reading the page
  | 'analyzing'    // Calling the AI (initial)
  | 'awaiting'     // Waiting for user to approve/reject the active action
  | 'executing'    // Running the approved action on the live page
  | 'reanalyzing'  // Re-extracting context + re-calling AI after a step
  | 'needs_input'  // Waiting for missing user-provided information
  | 'complete'     // Workflow finished (all done, stopped, or failed)

export interface WorkflowState {
  sessionId: string
  task: string
  analysisText: string
  pendingActions: SuggestedAction[]   // [0] = next to approve, rest = queued
  activeAction: SuggestedAction | null // Currently executing
  completedActions: CompletedAction[]
  userInputs: string[]
  clarificationQuestion: string | null
  phase: WorkflowPhase
  error: string | null
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

function buildPriorSteps(completed: CompletedAction[]): PriorStep[] {
  const startDetailedIndex = Math.max(0, completed.length - MAX_DETAILED_PRIOR_STEPS)
  return completed.slice(-MAX_TOTAL_PRIOR_STEPS).map(({ action, result, analysis_snapshot, page_snapshot }, index, visibleSteps) => {
    const originalIndex = completed.length - visibleSteps.length + index
    const includeDetails = originalIndex >= startDetailedIndex

    return {
    action_type: action.action_type,
    description: action.description,
    target_selector: includeDetails ? action.target_selector : null,
    value: includeDetails ? action.value : null,
    execution_result: result.message,
    page_analysis: includeDetails ? analysis_snapshot?.slice(0, MAX_ANALYSIS_SNAPSHOT_CHARS) : undefined,
    page_url: includeDetails ? page_snapshot?.url : undefined,
    page_title: includeDetails ? page_snapshot?.title : undefined,
    page_metadata: includeDetails ? compactMetadata(page_snapshot?.metadata) : {},
  }
  })
}

function buildSupplementalContext(userInputs: string[]): string {
  if (userInputs.length === 0) return ''
  return [
    'Authoritative user-provided answers. Use these answers directly. Do not ask for the same information again:',
    ...userInputs.map((input, index) => `${index + 1}. ${input}`),
  ].join('\n')
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
  return matchingCompleted.length >= 1
}

function nextAllowedActions(actions: SuggestedAction[], completed: CompletedAction[], currentUrl?: string): SuggestedAction[] {
  const nextAction = actions[0]
  if (!nextAction) return []
  return isRepeatedAction(nextAction, completed, currentUrl) ? [] : [nextAction]
}

function taskRequiresAddToCart(task: string): boolean {
  return /\b(add|put|place)\b.{0,30}\b(cart|basket|bag)\b/i.test(task)
}

function completedAddToCart(completed: CompletedAction[]): boolean {
  return completed.some(({ action, result }) => {
    if (!result.success || action.action_type !== 'click') return false
    const text = [
      action.description,
      action.reasoning,
      action.target_selector,
      action.value ?? '',
    ].join(' ').toLowerCase()
    return (
      /add\s*(to)?\s*(cart|basket|bag)/i.test(text) ||
      /\b(add-to-cart|addtocart)\b/i.test(text)
    )
  })
}

function isLikelyProductPage(ctx: PageContext, completed: CompletedAction[]): boolean {
  const currentText = [ctx.url, ctx.title, ctx.visible_text, ...ctx.headings].join(' ').toLowerCase()
  if (/\b(add\s*(to)?\s*(cart|basket|bag)|buy now|product details|ratings?|reviews?)\b/i.test(currentText)) {
    return true
  }

  return completed.slice(-3).some(({ action, result }) => {
    if (!result.success) return false
    const text = [action.action_type, action.description, action.reasoning].join(' ').toLowerCase()
    return /\b(product|details|view)\b/.test(text) && action.action_type === 'click'
  })
}

function buildAddToCartRecoveryAction(ctx: PageContext, completed: CompletedAction[]): SuggestedAction | null {
  const addToCartElement = ctx.interactive_elements.find((el) => {
    const text = [el.text, el.placeholder, el.selector].join(' ').toLowerCase()
    return (
      /add\s*(to)?\s*(cart|basket|bag)/i.test(text) ||
      /\b(add-to-cart|addtocart)\b/i.test(text)
    ) && !/\b(view|go to|open)\s*(cart|basket|bag)\b/i.test(text)
  })

  if (addToCartElement) {
    return {
      action_id: crypto.randomUUID(),
      action_type: 'click',
      target_selector: addToCartElement.selector,
      value: null,
      description: 'Click Add to Cart.',
      reasoning: 'The original task requires adding the selected product to the cart.',
      confidence: 0.85,
      safety_level: 'caution',
    }
  }

  if (!isLikelyProductPage(ctx, completed)) return null

  const scrollAction: SuggestedAction = {
    action_id: crypto.randomUUID(),
    action_type: 'scroll',
    target_selector: 'window',
    value: 'down',
    description: 'Scroll to find the Add to Cart button.',
    reasoning: 'The product page is open, but the Add to Cart button is not visible yet.',
    confidence: 0.6,
    safety_level: 'safe',
  }
  if (!isRepeatedAction(scrollAction, completed, ctx.url)) return scrollAction

  const waitAction: SuggestedAction = {
    action_id: crypto.randomUUID(),
    action_type: 'wait',
    target_selector: 'window',
    value: '2000',
    description: 'Wait for the product page controls to finish loading.',
    reasoning: 'The task still needs Add to Cart, and the product page controls may still be loading.',
    confidence: 0.5,
    safety_level: 'safe',
  }
  return isRepeatedAction(waitAction, completed, ctx.url) ? null : waitAction
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
    userInputs: [],
    clarificationQuestion: null,
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

  const analyze = useCallback(async (taskOverride?: string) => {
    const { sessionId } = state
    // taskOverride lets voice input bypass the stale closure on state.task.
    const task = (taskOverride ?? state.task).trim()
    if (!task) return

    setState((s) => ({
      ...s,
      task,           // Sync state.task if voice provided an override.
      phase: 'extracting',
      error: null,
      analysisText: '',
      pendingActions: [],
      activeAction: null,
      completedActions: [],
      userInputs: [],
      clarificationQuestion: null,
    }))

    // 1. Extract page context
    let ctx: PageContext
    try {
      const res = await sendToBackground<{ context?: PageContext; error?: string }>({
        type: 'EXTRACT_CONTEXT',
      })
      if (!res.context) {
        setState((s) => ({ ...s, phase: 'idle', error: res.error ?? 'Failed to read page.' }))
        return
      }
      ctx = res.context
      setPageContext(ctx)
    } catch (err) {
      setState((s) => ({ ...s, phase: 'idle', error: errMsg(err) }))
      return
    }

    // 2. Call AI
    setState((s) => ({ ...s, phase: 'analyzing' }))
    try {
      const response = await fetchAnalyzeWithRetry(
        `${BACKEND_URL}/analyze`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            task,
            page_context: ctx,
            supplemental_context: buildSupplementalContext([]),
          }),
        },
      )
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
        // FastAPI 422 detail is an array of {loc, msg, type} — flatten to a readable string.
        const detail = Array.isArray(err.detail)
          ? err.detail.map((e: { msg?: string; loc?: string[] }) =>
              `${(e.loc ?? []).slice(-1)[0] ?? 'field'}: ${e.msg ?? JSON.stringify(e)}`
            ).join(' | ')
          : (err.detail ?? `HTTP ${response.status}`)
        throw new Error(detail)
      }
      const result: AnalyzeResponse = await response.json()
      const allowedActions = nextAllowedActions(result.suggested_actions, [], ctx.url)
      const cartRecoveryAction = taskRequiresAddToCart(task)
        ? buildAddToCartRecoveryAction(ctx, [])
        : null

      if (result.clarification_question) {
        const repeatedQuestion = state.userInputs.some((input) =>
          input.toLowerCase().includes(`question: ${result.clarification_question}`.toLowerCase()),
        )
        setState((s) => ({
          ...s,
          phase: 'needs_input',
          analysisText: result.analysis,
          pendingActions: [],
          clarificationQuestion: repeatedQuestion
            ? `I already have an answer for "${result.clarification_question}". If it is wrong, provide the corrected value; otherwise click Continue to retry using the saved answer.`
            : result.clarification_question ?? null,
        }))
      } else if (allowedActions.length === 0 && cartRecoveryAction) {
        setState((s) => ({
          ...s, phase: 'awaiting', analysisText: result.analysis,
          pendingActions: [cartRecoveryAction], clarificationQuestion: null,
        }))
      } else if (allowedActions.length === 0) {
        setState((s) => ({
          ...s,
          phase: 'complete',
          analysisText: result.analysis,
          pendingActions: [],
          clarificationQuestion: null,
        }))
      } else {
        setState((s) => ({
          ...s, phase: 'awaiting', analysisText: result.analysis,
          pendingActions: allowedActions, clarificationQuestion: null,
        }))
      }
    } catch (err) {
      setState((s) => ({ ...s, phase: 'idle', error: errMsg(err) }))
    }
  }, [state.task, state.sessionId])

  // ── Re-analysis after a step ────────────────────────────────────────────────

  const reanalyze = useCallback(async (
    sessionId: string,
    task: string,
    completed: CompletedAction[],
    userInputs: string[],
  ) => {
    setState((s) => ({ ...s, phase: 'reanalyzing', clarificationQuestion: null }))

    // Re-extract fresh page context
    let ctx: PageContext
    try {
      const res = await sendToBackground<{ context?: PageContext; error?: string }>({
        type: 'EXTRACT_CONTEXT',
      })
      if (!res.context) {
        setState((s) => ({
          ...s, phase: 'complete', pendingActions: [],
          error: `Re-analysis: page read failed — ${res.error ?? 'unknown'}`,
        }))
        return
      }
      ctx = res.context
      setPageContext(ctx)
    } catch (err) {
      setState((s) => ({
        ...s, phase: 'complete', pendingActions: [],
        error: `Re-analysis: page read error — ${errMsg(err)}`,
      }))
      return
    }

    // Call AI with updated context + prior steps
    try {
      const response = await fetchAnalyzeWithRetry(
        `${BACKEND_URL}/analyze`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            task,
            page_context: ctx,
            prior_steps: buildPriorSteps(completed),
            supplemental_context: buildSupplementalContext(userInputs),
          }),
        },
      )
      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}))
        const detail = Array.isArray(errBody.detail)
          ? errBody.detail.map((e: { msg?: string; loc?: string[] }) =>
              `${(e.loc ?? []).slice(-1)[0] ?? 'field'}: ${e.msg ?? JSON.stringify(e)}`
            ).join(' | ')
          : (errBody.detail ?? `HTTP ${response.status}`)
        throw new Error(detail)
      }
      const result: AnalyzeResponse = await response.json()
      const allowedActions = nextAllowedActions(result.suggested_actions, completed, ctx.url)
      const needsCartCompletion = taskRequiresAddToCart(task) && !completedAddToCart(completed)
      const cartRecoveryAction = needsCartCompletion
        ? buildAddToCartRecoveryAction(ctx, completed)
        : null

      if (result.clarification_question) {
        const repeatedQuestion = userInputs.some((input) =>
          input.toLowerCase().includes(`question: ${result.clarification_question}`.toLowerCase()),
        )
        setState((s) => ({
          ...s,
          phase: 'needs_input',
          pendingActions: [],
          analysisText: result.analysis,
          clarificationQuestion: repeatedQuestion
            ? `I already have an answer for "${result.clarification_question}". If it is wrong, provide the corrected value; otherwise click Continue to retry using the saved answer.`
            : result.clarification_question ?? null,
        }))
      } else if (allowedActions.length === 0 && cartRecoveryAction) {
        setState((s) => ({
          ...s, phase: 'awaiting', pendingActions: [cartRecoveryAction],
          analysisText: result.analysis, clarificationQuestion: null, error: null,
        }))
      } else if (allowedActions.length === 0 && needsCartCompletion) {
        setState((s) => ({
          ...s, phase: 'complete', pendingActions: [], analysisText: result.analysis,
          clarificationQuestion: null,
          error: 'Stopped because the task still needs Add to Cart, but no Add to Cart control was found after retrying.',
        }))
      } else if (allowedActions.length === 0) {
        const stoppedRepeat = result.suggested_actions.length > 0
        setState((s) => ({
          ...s, phase: 'complete', pendingActions: [], analysisText: result.analysis,
          clarificationQuestion: null,
          error: stoppedRepeat
            ? 'Stopped because the assistant proposed a repeated browser action instead of making progress.'
            : null,
        }))
      } else {
        setState((s) => ({
          ...s, phase: 'awaiting', pendingActions: allowedActions,
          analysisText: result.analysis, clarificationQuestion: null,
        }))
      }
    } catch (err) {
      setState((s) => ({
        ...s, phase: 'complete', pendingActions: [],
        error: `Re-analysis failed: ${errMsg(err)}`,
      }))
    }
  }, [])

  // ── Approve ─────────────────────────────────────────────────────────────────

  const approveAction = useCallback(async () => {
    const { pendingActions, sessionId, task, completedActions, analysisText, userInputs } = state
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

    const newCompleted: CompletedAction[] = [
      ...completedActions,
      {
        action,
        result,
        analysis_snapshot: analysisText,
        page_snapshot: pageContext
          ? {
              url: pageContext.url,
              title: pageContext.title,
              metadata: compactMetadata(pageContext.metadata),
            }
          : undefined,
      },
    ]

    setState((s) => ({ ...s, activeAction: null, completedActions: newCompleted }))

    logEvent(sessionId, 'executed', action, pageContext,
      result.success ? 'success' : result.message)

    if (!result.success) {
      await reanalyze(sessionId, task, newCompleted, userInputs)
      return
    }

    // For navigate actions: wait for the new page to fully load before
    // re-analyzing — otherwise the extractor sees the old page.
    if (action.action_type === 'navigate') {
      await sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_TAB_LOAD' })
    }

    // For fill, click, and wait actions: wait until the DOM stops mutating before
    // re-analyzing. This lets search results, chat panels, and other async
    // UI updates fully render before we extract page context.
    // MutationObserver-based — adapts to actual network/CPU speed, no fixed timeout.
    if (action.action_type === 'fill' || action.action_type === 'click' || action.action_type === 'wait') {
      await sendToBackground<{ ready: boolean }>({ type: 'WAIT_FOR_DOM_SETTLE' })
    }

    // Re-analyze with fresh page context
    await reanalyze(sessionId, task, newCompleted, userInputs)
  }, [state, pageContext, reanalyze])

  const continueWithInput = useCallback(async (answer: string) => {
    const trimmed = answer.trim()
    if (!trimmed) return

    const { sessionId, task, completedActions, userInputs } = state
    if (/^(done|complete|completed|finished)$/i.test(trimmed)) {
      setState((s) => ({
        ...s,
        phase: 'complete',
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
    await reanalyze(sessionId, task, completedActions, nextInputs)
  }, [state, reanalyze])

  // ── Reject ──────────────────────────────────────────────────────────────────

  const rejectAction = useCallback(() => {
    const { pendingActions, sessionId } = state
    const action = pendingActions[0]
    if (!action) return

    logEvent(sessionId, 'rejected', action, pageContext)

    // Rejecting stops the remaining queue
    setState((s) => ({ ...s, pendingActions: [], phase: 'complete' }))
  }, [state, pageContext])

  // ── Stop ────────────────────────────────────────────────────────────────────

  const stopWorkflow = useCallback(() => {
    setState((s) => ({ ...s, pendingActions: [], phase: 'complete' }))
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
      userInputs: [],
      clarificationQuestion: null,
      phase: 'idle',
      error: null,
    }))
  }, [])

  return { state, setTask, analyze, approveAction, rejectAction, stopWorkflow, reset, continueWithInput }
}
