import { useState, useCallback } from 'react'
import { sendToBackground } from '../../utils/messaging'
import type { PageContext } from '../../types'
import type { AssistState, AssistResponse, ReadView, ChatMessage, ChatMessageType, IntelligenceLayer } from '../../types/assist'

const BACKEND_URL = 'http://localhost:8000'
const ASSIST_TIMEOUT_MS = 60_000

function errMsg(err: unknown): string {
  if (err instanceof Error) return err.message
  if (typeof err === 'string') return err
  if (err && typeof err === 'object') {
    const e = err as Record<string, unknown>
    if (typeof e.message === 'string') return e.message
  }
  return String(err)
}

function projectReadView(ctx: PageContext): ReadView {
  return {
    url: ctx.url,
    title: ctx.title,
    favicon: '',
    headings: ctx.headings.slice(0, 10),
    content_blocks: ctx.content_blocks.slice(0, 50).map(b => ({
      selector: b.selector,
      text: b.text.slice(0, 500),
    })),
    visible_text: ctx.visible_text.slice(0, 8000),
    selected_text: ctx.selected_text ?? '',
    metadata: Object.fromEntries(
      Object.entries(ctx.metadata ?? {}).slice(0, 12)
    ),
  }
}

function computeFingerprint(ctx: PageContext): string {
  return [ctx.url, ctx.title, ctx.visible_text.slice(0, 200)].join('|')
}

async function fetchWithTimeout(url: string, options: RequestInit): Promise<Response> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), ASSIST_TIMEOUT_MS)
  try {
    return await fetch(url, { ...options, signal: ctrl.signal })
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      throw new Error(`Assist timed out after ${ASSIST_TIMEOUT_MS / 1000}s.`)
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}

async function assistFetch(
  conversationId: string,
  message: string,
  scope: 'page' | 'selection',
): Promise<AssistResponse> {
  const res = await sendToBackground<{ context?: PageContext; error?: string }>({
    type: 'EXTRACT_CONTEXT',
  })
  if (!res.context) throw new Error(res.error ?? 'Failed to read page.')

  const ctx = res.context
  const readView = projectReadView(ctx)
  const fingerprint = computeFingerprint(ctx)

  const response = await fetchWithTimeout(`${BACKEND_URL}/assist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
      read_view: readView,
      context_fingerprint: fingerprint,
      selection_scope: scope,
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }))
    const detail = Array.isArray(err.detail)
      ? err.detail.map((e: { msg?: string }) => e.msg ?? JSON.stringify(e)).join(' | ')
      : (err.detail ?? `HTTP ${response.status}`)
    throw new Error(detail)
  }

  return response.json() as Promise<AssistResponse>
}

function makeUserMessage(text: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    type: 'user_text',
    content: text,
    suggestedFollowups: [],
    availableActions: [],
    timestamp: Date.now(),
  }
}

function makeAssistantMessage(response: AssistResponse, sourceQuery: string = ''): ChatMessage {
  const typeMap: Record<string, ChatMessageType> = {
    summary: 'summary',
    answer: 'answer',
    not_implemented: 'not_implemented',
    research_report: 'research_report',
  }
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    type: typeMap[response.type] ?? 'not_implemented',
    content: response.content,
    suggestedFollowups: response.suggested_followups,
    availableActions: response.available_actions,
    handoff: response.handoff.available ? response.handoff : undefined,
    sourceQuery: response.handoff.available ? sourceQuery : undefined,
    meta: response.meta,
    researchReport: response.research_report ?? undefined,
    intelligence: (response.intelligence ?? undefined) as IntelligenceLayer | undefined,
    taskId: response.task_id ?? undefined,
    taskState: response.task_state ?? undefined,
    timestamp: Date.now(),
  }
}

function makeErrorMessage(text: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'assistant',
    type: 'error',
    content: text,
    suggestedFollowups: [],
    availableActions: [],
    timestamp: Date.now(),
  }
}

export function useAssist() {
  const [state, setState] = useState<AssistState>({
    conversationId: crypto.randomUUID(),
    phase: 'idle',
    messages: [],
    error: null,
  })

  const summarize = useCallback(async (scope: 'page' | 'selection' = 'page') => {
    const { conversationId } = state
    const messageText =
      scope === 'selection' ? 'Summarize the selected text' : 'Summarize this page'

    setState(s => ({
      ...s,
      phase: 'loading',
      error: null,
      messages: [...s.messages, makeUserMessage(messageText)],
    }))

    try {
      const result = await assistFetch(conversationId, messageText, scope)
      setState(s => ({
        ...s,
        phase: 'idle',
        messages: [...s.messages, makeAssistantMessage(result, messageText)],
      }))
    } catch (err) {
      setState(s => ({
        ...s,
        phase: 'idle',
        messages: [...s.messages, makeErrorMessage(errMsg(err))],
      }))
    }
  }, [state.conversationId])

  const ask = useCallback(async (question: string) => {
    if (!question.trim()) return
    const { conversationId } = state

    setState(s => ({
      ...s,
      phase: 'loading',
      error: null,
      messages: [...s.messages, makeUserMessage(question)],
    }))

    try {
      const result = await assistFetch(conversationId, question, 'page')
      setState(s => ({
        ...s,
        phase: 'idle',
        messages: [...s.messages, makeAssistantMessage(result, question)],
      }))
    } catch (err) {
      setState(s => ({
        ...s,
        phase: 'idle',
        messages: [...s.messages, makeErrorMessage(errMsg(err))],
      }))
    }
  }, [state.conversationId])

  const reset = useCallback(() => {
    setState({
      conversationId: crypto.randomUUID(),
      phase: 'idle',
      messages: [],
      error: null,
    })
  }, [])

  return { state, summarize, ask, reset }
}
