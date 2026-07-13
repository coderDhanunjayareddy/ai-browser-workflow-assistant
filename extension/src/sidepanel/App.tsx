import { useState, useEffect, useCallback, useRef } from 'react'
import { useWorkflow } from './hooks/useWorkflow'
import { useHistory } from './hooks/useHistory'
import { useSpeechInput } from './hooks/useSpeechInput'
import { useAssist } from './hooks/useAssist'
import type { SuggestedAction, SessionHistory, EventHistory } from '../types'
import type { StructuredSummary, ChatMessage, ResearchReport, IntelligenceLayer, WorkflowRecommendation, ApprovalLevel } from '../types/assist'

type Tab = 'workflow' | 'history' | 'analytics' | 'assist'

// ── App shell ────────────────────────────────────────────────────────────────

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('workflow')
  const workflow = useWorkflow()
  const history = useHistory()

  function switchTab(tab: Tab) {
    setActiveTab(tab)
    if (tab === 'history') history.fetchHistory()
  }

  return (
    <div style={s.container}>
      <h2 style={s.heading}>AI Browser Assistant</h2>
      <div style={s.tabBar}>
        <button style={{ ...s.tabBtn, ...(activeTab === 'workflow' ? s.tabActive : {}) }}
          onClick={() => switchTab('workflow')}>Workflow</button>
        <button style={{ ...s.tabBtn, ...(activeTab === 'history' ? s.tabActive : {}) }}
          onClick={() => switchTab('history')}>History</button>
        <button style={{ ...s.tabBtn, ...(activeTab === 'analytics' ? s.tabActive : {}) }}
          onClick={() => switchTab('analytics')}>Analytics</button>
        <button style={{ ...s.tabBtn, ...(activeTab === 'assist' ? s.tabActive : {}) }}
          onClick={() => switchTab('assist')}>Assist</button>
      </div>
      {activeTab === 'workflow' && <WorkflowPanel {...workflow} />}
      {activeTab === 'history' && <HistoryPanel sessions={history.sessions} loading={history.loading}
        error={history.error} onRefresh={history.fetchHistory} />}
      {activeTab === 'analytics' && <AnalyticsPanel sessionId={workflow.state.sessionId} />}
      {activeTab === 'assist' && (
        <AssistPanel onHandoffToWorkflow={(query) => {
          workflow.setTask(query)
          setActiveTab('workflow')
        }} />
      )}
    </div>
  )
}

// ── Workflow panel ────────────────────────────────────────────────────────────

type WorkflowProps = ReturnType<typeof useWorkflow>

// ── Language list ─────────────────────────────────────────────────────────────

const LANGUAGES = [
  { code: '',      label: 'Auto (Browser)' },
  // Indian languages
  { code: 'te-IN', label: '🇮🇳 Telugu' },
  { code: 'hi-IN', label: '🇮🇳 Hindi' },
  { code: 'ta-IN', label: '🇮🇳 Tamil' },
  { code: 'kn-IN', label: '🇮🇳 Kannada' },
  { code: 'ml-IN', label: '🇮🇳 Malayalam' },
  { code: 'bn-IN', label: '🇮🇳 Bengali' },
  { code: 'mr-IN', label: '🇮🇳 Marathi' },
  { code: 'gu-IN', label: '🇮🇳 Gujarati' },
  { code: 'pa-IN', label: '🇮🇳 Punjabi' },
  // International
  { code: 'en-US', label: '🇺🇸 English (US)' },
  { code: 'en-GB', label: '🇬🇧 English (UK)' },
  { code: 'es-ES', label: '🇪🇸 Spanish' },
  { code: 'fr-FR', label: '🇫🇷 French' },
  { code: 'de-DE', label: '🇩🇪 German' },
  { code: 'it-IT', label: '🇮🇹 Italian' },
  { code: 'pt-BR', label: '🇧🇷 Portuguese' },
  { code: 'ru-RU', label: '🇷🇺 Russian' },
  { code: 'ja-JP', label: '🇯🇵 Japanese' },
  { code: 'ko-KR', label: '🇰🇷 Korean' },
  { code: 'zh-CN', label: '🇨🇳 Chinese (Simplified)' },
  { code: 'zh-TW', label: '🇹🇼 Chinese (Traditional)' },
  { code: 'ar-SA', label: '🇸🇦 Arabic' },
  { code: 'tr-TR', label: '🇹🇷 Turkish' },
  { code: 'vi-VN', label: '🇻🇳 Vietnamese' },
  { code: 'th-TH', label: '🇹🇭 Thai' },
  { code: 'id-ID', label: '🇮🇩 Indonesian' },
  { code: 'ms-MY', label: '🇲🇾 Malay' },
  { code: 'nl-NL', label: '🇳🇱 Dutch' },
  { code: 'pl-PL', label: '🇵🇱 Polish' },
  { code: 'sv-SE', label: '🇸🇪 Swedish' },
  { code: 'uk-UA', label: '🇺🇦 Ukrainian' },
]

function WorkflowPanel({ state, setTask, analyze, approveAction, rejectAction, stopWorkflow, reset, continueWithInput }: WorkflowProps) {
  const [autoMode, setAutoMode] = useState(false)
  const [clarificationAnswer, setClarificationAnswer] = useState('')
  const [language, setLanguage] = useState<string>(() =>
    localStorage.getItem('ai_assist_lang') ?? ''
  )

  const handleLanguageChange = (code: string) => {
    setLanguage(code)
    localStorage.setItem('ai_assist_lang', code)
  }

  // ── Voice input ─────────────────────────────────────────────────────────────
  const handleVoiceResult = useCallback((text: string) => {
    analyze(text) // passes text directly — bypasses stale closure on state.task
  }, [analyze])

  const { listening, speechError, startListening, stopListening, supported: speechSupported } =
    useSpeechInput(handleVoiceResult, language)

  const submitClarification = useCallback(() => {
    const answer = clarificationAnswer.trim() || 'Retry analysis from the current page.'
    setClarificationAnswer('')
    continueWithInput(answer)
  }, [clarificationAnswer, continueWithInput])

  // ── Auto-approve effect ──────────────────────────────────────────────────────
  // When auto mode is on and a new action is awaiting approval, approve it
  // automatically after a short delay so the user can see what's happening.
  useEffect(() => {
    if (!autoMode) return
    if (state.phase !== 'awaiting_execution') return
    if (state.pendingActions.length === 0) return
    const timer = setTimeout(() => approveAction(), 800)
    return () => clearTimeout(timer)
  }, [autoMode, state.phase, state.pendingActions, approveAction])

  // ── Derived state ─────────────────────────────────────────────────────────
  const { phase, task, analysisText, pendingActions, activeAction, completedActions, error, clarificationQuestion, report, replan, goalConvergence } = state
  const isWorking   = phase === 'observing' || phase === 'analyzing' || phase === 'executing' || phase === 'refreshing'
  const isAwaiting  = phase === 'awaiting_execution'
  const needsInput  = phase === 'awaiting_user'
  const isComplete  = phase === 'completed'
  const isCancelled = phase === 'cancelled'
  const isFailed    = phase === 'failed'
  const isReported  = phase === 'reported'
  const isReplan    = phase === 'replan'
  const isRunning   = isWorking || isAwaiting || needsInput

  const phaseLabel: Record<string, string> = {
    idle: 'Analyze', observing: 'Reading page…', analyzing: 'Thinking…',
    awaiting_execution: 'Analyze', executing: 'Executing…', refreshing: 'Refreshing…',
    awaiting_user: 'Waiting for info', reported: 'Analyze', replan: 'Analyze',
    completed: 'Analyze', cancelled: 'Analyze', failed: 'Analyze',
  }

  const showResults = analysisText || completedActions.length > 0 || pendingActions.length > 0 || activeAction || isComplete || isCancelled || isFailed || needsInput || isReported || isReplan

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); analyze() }
  }

  const handleClarificationKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); submitClarification() }
  }

  return (
    <>
      {/* ── Task input ── */}
      <textarea style={s.textarea} rows={3}
        placeholder={listening ? '🎤 Listening… speak your task' : 'Describe what you want to do… (Enter to submit)'}
        value={task}
        onChange={(e) => setTask(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={isWorking || needsInput || (isAwaiting && !autoMode) || listening}
      />

      {/* ── Controls row ── */}
      <div style={s.controlRow}>
        {/* Mic button */}
        {speechSupported && (
          <button
            onClick={listening ? stopListening : startListening}
            disabled={isRunning}
            style={{ ...s.micBtn, ...(listening ? s.micActive : {}) }}
            title={listening ? 'Stop listening' : 'Speak your task'}
          >
            {listening ? '🔴' : '🎤'}
          </button>
        )}

        {/* Analyze button */}
        <button onClick={() => analyze()} style={s.primaryBtn}
          disabled={isWorking || needsInput || (isAwaiting && !autoMode) || !task.trim() || listening}>
          {phaseLabel[phase] ?? 'Analyze'}
        </button>

        {/* Clear */}
        {showResults && !isWorking && (
          <button onClick={() => { reset(); setAutoMode(false) }} style={s.resetBtn}>Clear</button>
        )}

        {/* Language selector */}
        <select
          value={language}
          onChange={(e) => handleLanguageChange(e.target.value)}
          style={s.langSelect}
          title="Voice & AI language"
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>{l.label}</option>
          ))}
        </select>

        {/* Auto-mode toggle */}
        <label style={s.autoLabel} title="Auto mode: executes all steps without manual approval">
          <div style={{ ...s.toggleTrack, ...(autoMode ? s.toggleOn : {}) }}
            onClick={() => setAutoMode(v => !v)}>
            <div style={{ ...s.toggleThumb, ...(autoMode ? s.toggleThumbOn : {}) }} />
          </div>
          <span style={{ ...s.autoText, ...(autoMode ? s.autoTextOn : {}) }}>🤖 Auto</span>
        </label>
      </div>

      {/* Speech error */}
      {speechError && <p style={s.speechErr}>{speechError}</p>}

      {/* Auto-mode banner */}
      {autoMode && isRunning && (
        <div style={s.autoBanner}>
          <span>🤖 Auto-executing — steps run automatically</span>
          <button onClick={() => { stopWorkflow(); setAutoMode(false) }} style={s.stopInline}>■ Stop</button>
        </div>
      )}

      {/* Workflow error */}
      {error && <p style={s.error}>{error}</p>}

      {/* ── Results area ── */}
      {showResults && (
        <div style={s.results}>

          {/* AI analysis */}
          {analysisText && (
            <div style={s.analysisBox}>
              <p style={s.analysisLabel}>AI Analysis</p>
              <p style={s.analysisText}>{analysisText}</p>
            </div>
          )}

          {goalConvergence && (
            <div style={s.convergenceBox}>
              <p style={s.convergenceLabel}>Goal convergence</p>
              <p style={s.convergenceText}>Semantic progress has stalled.</p>
            </div>
          )}

          {/* Live execution feed — completed steps */}
          {completedActions.length > 0 && (
            <div style={s.feed}>
              {completedActions.map(({ action, result }, i) => (
                <div key={action.action_id} style={s.feedRow}>
                  <span style={{ ...s.feedIcon, color: result.success ? '#27ae60' : '#e74c3c' }}>
                    {result.success ? '⚡' : '✗'}
                  </span>
                  <div style={s.feedBody}>
                    <span style={s.feedStep}>Step {i + 1}</span>
                    <span style={s.feedType}>{action.action_type.toUpperCase()}</span>
                    <span style={s.feedDesc}>{action.description}</span>
                    {!result.success && <span style={s.feedErr}>{result.message}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Currently executing */}
          {phase === 'executing' && activeAction && (
            <div style={s.statusCard}>
              <span style={s.spinner}>⏳</span>
              <span style={s.statusMsg}>
                Executing Step {completedActions.length + 1}: {activeAction.description}
              </span>
            </div>
          )}

          {/* Re-analyzing */}
          {phase === 'refreshing' && (
            <div style={s.statusCard}>
              <span style={s.spinner}>⟳</span>
              <span style={s.statusMsg}>Re-analyzing updated page…</span>
            </div>
          )}

          {/* Missing information */}
          {needsInput && clarificationQuestion && (
            <div style={s.clarifyBox}>
              <p style={s.clarifyLabel}>Need information</p>
              <p style={s.clarifyQuestion}>{clarificationQuestion}</p>
              <div style={s.clarifyRow}>
                <input
                  value={clarificationAnswer}
                  onChange={(e) => setClarificationAnswer(e.target.value)}
                  onKeyDown={handleClarificationKeyDown}
                  placeholder="Type the missing detail..."
                  style={s.clarifyInput}
                  autoFocus
                />
                <button
                  onClick={submitClarification}
                  style={s.primaryBtn}
                >
                  Continue
                </button>
              </div>
            </div>
          )}

          {isReported && report && (
            <div style={s.reportBox}>
              <p style={s.reportLabel}>Planner report</p>
              {report.answer && <p style={s.reportAnswer}>{report.answer}</p>}
              <p style={s.reportClaim}>{report.claim}</p>
              <p style={s.reportNote}>This answer has not been semantically verified yet.</p>
            </div>
          )}

          {isReplan && replan && (
            <div style={s.replanBox}>
              <p style={s.replanLabel}>Planner requested replan</p>
              <p style={s.replanReason}>{replan.reason}</p>
            </div>
          )}

          {/* Active action card (manual mode OR danger action in auto mode) */}
          {isAwaiting && pendingActions.length > 0 && (
            <ActionCard
              action={pendingActions[0]}
              stepNumber={completedActions.length + 1}
              autoMode={autoMode}
              onApprove={approveAction}
              onReject={() => { rejectAction(); setAutoMode(false) }}
            />
          )}

          {/* Queue preview (shown when there are more steps ahead) */}
          {isAwaiting && pendingActions.length > 1 && (
            <div style={s.queueBox}>
              <p style={s.queueLabel}>{pendingActions.length - 1} more step{pendingActions.length - 1 !== 1 ? 's' : ''} queued</p>
              {pendingActions.slice(1).map((a, i) => (
                <div key={a.action_id} style={s.queueRow}>
                  <span style={s.queueNum}>{completedActions.length + i + 2}</span>
                  <span style={s.queueType}>{a.action_type.toUpperCase()}</span>
                  <span style={s.queueDesc}>{a.description}</span>
                </div>
              ))}
            </div>
          )}

          {/* Stop button (manual mode only — auto mode has the banner) */}
          {isAwaiting && !autoMode && pendingActions.length > 0 && (
            <button onClick={stopWorkflow} style={s.stopBtn}>✕ Stop workflow</button>
          )}

          {/* Complete */}
          {isComplete && completedActions.length > 0 && !error && (
            <div style={s.completeBox}>
              ✓ Done — {completedActions.filter(c => c.result.success).length} of {completedActions.length} step{completedActions.length !== 1 ? 's' : ''} succeeded
            </div>
          )}
          {isComplete && completedActions.length === 0 && !error && analysisText && (
            <div style={s.completeBox}>✓ No actions needed for this task.</div>
          )}
          {isCancelled && (
            <div style={s.cancelledBox}>Workflow cancelled.</div>
          )}
        </div>
      )}
    </>
  )
}

// ── Action card ───────────────────────────────────────────────────────────────

interface ActionCardProps {
  action: SuggestedAction
  stepNumber: number
  autoMode: boolean
  onApprove: () => void
  onReject: () => void
}

function ActionCard({ action, stepNumber, autoMode, onApprove, onReject }: ActionCardProps) {
  const safetyColors: Record<string, string> = {
    safe: '#27ae60', caution: '#e67e22', danger: '#e74c3c',
  }
  const isDanger = action.safety_level === 'danger'

  return (
    <div style={{ ...s.card, borderColor: isDanger ? '#e74c3c' : '#2563eb' }}>
      <div style={s.cardMeta}>
        <span style={s.cardStep}>Step {stepNumber}</span>
        {autoMode && (
          <span style={s.autoChip}>Auto-executing…</span>
        )}
        {isDanger && !autoMode && (
          <span style={s.dangerChip}>⚠ Requires approval</span>
        )}
      </div>
      <div style={s.cardHeader}>
        <span style={s.actionType}>{action.action_type.toUpperCase()}</span>
        <span style={{ ...s.safetyBadge, background: safetyColors[action.safety_level] ?? '#888' }}>
          {action.safety_level}
        </span>
        <span style={s.confidence}>{Math.round(action.confidence * 100)}% confident</span>
      </div>
      <p style={s.cardDescription}>{action.description}</p>
      <p style={s.cardReasoning}>{action.reasoning}</p>
      {action.target_selector && <code style={s.selector}>{action.target_selector}</code>}
      {action.value && <p style={s.value}>Value: <strong>{action.value}</strong></p>}

      {/* Always show buttons — in auto mode they're secondary. For danger, always manual. */}
      <div style={s.actionButtons}>
        <button onClick={onApprove} style={s.approveBtn}>✓ Approve</button>
        <button onClick={onReject} style={s.rejectBtn}>✕ Reject</button>
      </div>
    </div>
  )
}

// ── History panel ─────────────────────────────────────────────────────────────

interface HistoryPanelProps {
  sessions: SessionHistory[]
  loading: boolean
  error: string | null
  onRefresh: () => void
}

function HistoryPanel({ sessions, loading, error, onRefresh }: HistoryPanelProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  function toggle(id: string) {
    setExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n })
  }

  if (loading) return <p style={s.histEmpty}>Loading history…</p>
  if (error) return <div><p style={s.error}>{error}</p><button onClick={onRefresh} style={s.resetBtn}>Retry</button></div>
  if (sessions.length === 0) return (
    <div style={{ textAlign: 'center', marginTop: '24px' }}>
      <p style={s.histEmpty}>No workflow history yet.</p>
      <p style={{ fontSize: '11px', color: '#aaa' }}>Completed workflows will appear here.</p>
    </div>
  )

  return (
    <div style={s.histList}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '8px' }}>
        <button onClick={onRefresh} style={s.refreshBtn}>↻ Refresh</button>
      </div>
      {sessions.map(session => (
        <div key={session.id} style={s.sessionCard}>
          <button style={s.sessionHeader} onClick={() => toggle(session.id)}>
            <div style={s.sessionMeta}>
              <span style={s.sessionTitle}>{session.tab_title || 'Untitled page'}</span>
              <span style={s.sessionDate}>{formatDate(session.created_at)}</span>
            </div>
            <div style={s.sessionUrl}>{truncate(session.tab_url, 45)}</div>
            <div style={s.sessionStats}>
              <span style={s.statChip}>{session.events.length} event{session.events.length !== 1 ? 's' : ''}</span>
              <span style={{ fontSize: '10px', color: '#aaa', marginLeft: 'auto' }}>{expanded.has(session.id) ? '▲' : '▼'}</span>
            </div>
          </button>
          {expanded.has(session.id) && (
            <div style={s.eventList}>
              {session.events.length === 0
                ? <p style={{ fontSize: '11px', color: '#aaa', padding: '6px 0' }}>No events recorded.</p>
                : session.events.map(event => <EventRow key={event.id} event={event} />)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function EventRow({ event }: { event: EventHistory }) {
  const icon = event.event_type === 'rejected' ? '✕'
    : event.event_type === 'executed' ? (event.execution_result === 'success' ? '⚡' : '✗') : '✓'
  const color = event.event_type === 'rejected' ? '#999'
    : event.event_type === 'executed' ? (event.execution_result === 'success' ? '#27ae60' : '#e74c3c') : '#2563eb'
  return (
    <div style={s.eventRow}>
      <span style={{ ...s.eventIcon, color }}>{icon}</span>
      <div style={s.eventBody}>
        <span style={s.eventType}>{(event.action_type ?? event.event_type).toUpperCase()}</span>
        <span style={s.eventDesc}>{event.description ?? '—'}</span>
        {event.execution_result && event.execution_result !== 'success' && (
          <span style={s.eventResult}>{event.execution_result}</span>
        )}
      </div>
    </div>
  )
}

interface AnalyticsData {
  status: string
  budget_usage: Record<string, { used: number; max: number }>
  token_usage: number
  recovery_count: number
  failure_types: Record<string, number>
  success_rate: number
  false_success_rate: number
  workflow_stability_score: number
  average_completion_time_seconds: number
  cost_metrics: { planner_calls: number; vision_calls: number; average_tokens_per_step: number }
}

function AnalyticsPanel({ sessionId }: { sessionId: string }) {
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const refresh = useCallback(() => {
    setError(null)
    fetch(`http://localhost:8000/workflow/${sessionId}/analytics`)
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 404 ? 'Run a workflow to create analytics.' : `HTTP ${response.status}`)
        return response.json()
      })
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : String(err)))
  }, [sessionId])
  useEffect(refresh, [refresh])

  if (error) return <div><p style={s.error}>{error}</p><button style={s.resetBtn} onClick={refresh}>Refresh</button></div>
  if (!data) return <p style={s.histEmpty}>Loading workflow analytics…</p>
  const metrics = [
    ['Token Usage', data.token_usage.toLocaleString()],
    ['Recovery Count', data.recovery_count],
    ['Success Rate', `${(data.success_rate * 100).toFixed(1)}%`],
    ['False Success Rate', `${(data.false_success_rate * 100).toFixed(1)}%`],
    ['Stability Score', data.workflow_stability_score.toFixed(1)],
    ['Avg. Step Time', `${data.average_completion_time_seconds.toFixed(1)}s`],
    ['Planner Calls', data.cost_metrics.planner_calls],
    ['Vision Calls', data.cost_metrics.vision_calls],
  ]
  return <div>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <h3 style={{ fontSize: '13px' }}>Workflow Analytics</h3>
      <button style={s.refreshBtn} onClick={refresh}>↻ Refresh</button>
    </div>
    <p style={{ fontSize: '11px', color: '#666' }}>Status: {data.status}</p>
    {Object.entries(data.budget_usage).map(([name, usage]) => <div key={name} style={{ marginBottom: '8px' }}>
      <div style={{ fontSize: '11px', display: 'flex', justifyContent: 'space-between' }}><span>{name}</span><span>{Math.round(usage.used)} / {usage.max}</span></div>
      <progress value={usage.used} max={usage.max} style={{ width: '100%' }} />
    </div>)}
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '7px', marginTop: '12px' }}>
      {metrics.map(([label, value]) => <div key={label} style={{ ...s.sessionCard, padding: '8px' }}>
        <div style={{ fontSize: '10px', color: '#777' }}>{label}</div><strong>{value}</strong>
      </div>)}
    </div>
    <h4 style={{ fontSize: '11px' }}>Failure Types</h4>
    <pre style={{ fontSize: '10px', whiteSpace: 'pre-wrap' }}>{JSON.stringify(data.failure_types, null, 2)}</pre>
  </div>
}

// ── Chat message renderer ────────────────────────────────────────────────────

interface ChatMessageViewProps {
  message: ChatMessage
  onFollowup: (question: string) => void
  onHandoff: (query: string) => void
  isLoading: boolean
}

function ChatMessageView({ message, onFollowup, onHandoff, isLoading }: ChatMessageViewProps) {
  if (message.role === 'user') {
    return (
      <div style={s.userBubble}>
        <p style={s.userBubbleText}>{message.content as string}</p>
      </div>
    )
  }

  if (message.type === 'error') {
    return (
      <div style={s.assistError}>
        <p style={s.assistErrorText}>{message.content as string}</p>
      </div>
    )
  }

  if (message.type === 'not_implemented') {
    return (
      <div style={s.assistInfo}>
        <p style={s.assistInfoText}>{message.content as string}</p>
        {message.handoff?.available && message.sourceQuery && (
          <button
            style={{ ...s.handoffBtn, ...(isLoading ? s.chipDisabled : {}) }}
            onClick={() => !isLoading && onHandoff(message.sourceQuery!)}
            disabled={isLoading}
          >
            Open in Workflow →
          </button>
        )}
        {message.suggestedFollowups.map(f => (
          <button key={f}
            style={{ ...s.chip, ...(isLoading ? s.chipDisabled : {}), marginTop: '6px' }}
            onClick={() => !isLoading && onFollowup(f)}
            disabled={isLoading}
          >{f}</button>
        ))}
      </div>
    )
  }

  if (message.type === 'answer') {
    return (
      <div style={s.answerCard}>
        <p style={s.answerText}>{message.content as string}</p>
        {message.meta && (
          <p style={s.msgMeta}>{message.meta.latency_ms}ms · {message.meta.context_chars} chars</p>
        )}
      </div>
    )
  }

  if (message.type === 'research_report' && message.researchReport) {
    return (
      <ResearchReportView
        report={message.researchReport}
        meta={message.meta}
        suggestedFollowups={message.suggestedFollowups}
        onFollowup={onFollowup}
        onHandoff={onHandoff}
        handoff={message.handoff}
        sourceQuery={message.sourceQuery}
        isLoading={isLoading}
        intelligence={message.intelligence}
      />
    )
  }

  if (message.type === 'summary') {
    const summary = message.content as StructuredSummary
    return (
      <div style={s.summaryBox}>
        <div style={s.summarySection}>
          <p style={s.summaryLabel}>TL;DR</p>
          <p style={s.summaryTldr}>{summary.tldr}</p>
        </div>

        {summary.key_points.length > 0 && (
          <div style={s.summarySection}>
            <p style={s.summaryLabel}>Key Points</p>
            <ul style={s.summaryList}>
              {summary.key_points.map((pt, i) => (
                <li key={i} style={s.summaryItem}>{pt}</li>
              ))}
            </ul>
          </div>
        )}

        {summary.entities.length > 0 && (
          <div style={s.summarySection}>
            <p style={s.summaryLabel}>Notable</p>
            <div style={s.entityGrid}>
              {summary.entities.map((e, i) => (
                <div key={i} style={s.entityCard}>
                  <span style={s.entityLabel}>{e.label}</span>
                  <span style={s.entityValue}>{e.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {summary.available_actions.length > 0 && (
          <div style={s.summarySection}>
            <p style={s.summaryLabel}>What you can do here</p>
            <div style={s.actionChips}>
              {summary.available_actions.map((a, i) => (
                <span key={i} style={s.actionChip}>{a}</span>
              ))}
            </div>
          </div>
        )}

        {message.suggestedFollowups.length > 0 && (
          <div style={s.summarySection}>
            <p style={s.summaryLabel}>Ask a follow-up</p>
            <div style={s.followupChips}>
              {message.suggestedFollowups.map(f => (
                <button key={f}
                  style={{ ...s.followupChip, ...(isLoading ? s.chipDisabled : {}) }}
                  onClick={() => !isLoading && onFollowup(f)}
                  disabled={isLoading}
                >{f}</button>
              ))}
            </div>
          </div>
        )}

        {message.meta && (
          <div style={s.summaryMeta}>
            <span style={s.metaText}>{message.meta.latency_ms}ms · {message.meta.context_chars} chars</span>
          </div>
        )}
      </div>
    )
  }

  return null
}

// ── Intelligence View (V4.0) ─────────────────────────────────────────────────

const APPROVAL_STYLES: Record<ApprovalLevel, { bg: string; color: string; border: string }> = {
  SAFE:               { bg: '#f0fdf4', color: '#166534', border: '#86efac' },
  REQUIRES_APPROVAL:  { bg: '#fffbeb', color: '#92400e', border: '#fde68a' },
  HIGH_RISK:          { bg: '#fef2f2', color: '#991b1b', border: '#fca5a5' },
}

const READINESS_LABEL: Record<string, string> = {
  READY: 'Ready', PARTIALLY_READY: 'Partial', BLOCKED: 'Blocked',
}

const APPROVAL_LABEL: Record<string, string> = {
  SAFE: 'Safe', REQUIRES_APPROVAL: 'Needs Approval', HIGH_RISK: 'High Risk',
}

interface IntelligenceViewProps {
  intelligence: IntelligenceLayer
  onHandoff: (q: string) => void
  sourceQuery?: string
  isLoading: boolean
}

function IntelligenceView({ intelligence, onHandoff, sourceQuery, isLoading }: IntelligenceViewProps) {
  const { opportunity, execution_plan, readiness, recommendations, bootstrap_facts } = intelligence
  if (!opportunity.detected || !execution_plan) return null

  const approval = execution_plan.approval_level
  const approvalStyle = APPROVAL_STYLES[approval] ?? APPROVAL_STYLES.REQUIRES_APPROVAL
  const isBlocked = readiness?.state === 'BLOCKED'

  return (
    <div style={s.intelBox}>
      {/* Opportunity header */}
      <div style={s.intelRow}>
        <span style={s.intelTag}>{execution_plan.workflow_type.replace(/_/g, ' ')}</span>
        <span style={{ ...s.intelApproval, background: approvalStyle.bg, color: approvalStyle.color, border: `1px solid ${approvalStyle.border}` }}>
          {APPROVAL_LABEL[approval]}
        </span>
        {readiness && (
          <span style={s.intelReadiness}>
            {READINESS_LABEL[readiness.state]}
            {` (${Math.round(readiness.readiness_score * 100)}%)`}
          </span>
        )}
        <span style={s.intelConf}>{Math.round(execution_plan.confidence * 100)}% conf</span>
      </div>

      {/* Next action advice */}
      <p style={s.intelNextAction}>{execution_plan.recommended_next_action}</p>

      {/* Missing inputs */}
      {execution_plan.missing_inputs.length > 0 && (
        <div style={s.intelMissingRow}>
          <span style={s.intelMissingLabel}>Missing: </span>
          {execution_plan.missing_inputs.map((m, i) => (
            <span key={i} style={s.intelMissingChip}>{m}</span>
          ))}
        </div>
      )}

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div style={s.intelRecsBox}>
          {recommendations.map((rec: WorkflowRecommendation) => (
            <div key={rec.recommendation_id} style={s.intelRecRow}>
              <span style={s.intelRecDot} />
              <span style={s.intelRecText}>{rec.action}</span>
            </div>
          ))}
        </div>
      )}

      {/* Prepare Workflow button — shown when not blocked and not high-risk, or even high-risk with explicit label */}
      {!isBlocked && bootstrap_facts && sourceQuery && (
        <button
          style={{
            ...s.prepareBtn,
            ...(isLoading ? s.chipDisabled : {}),
            ...(approval === 'HIGH_RISK' ? s.prepareBtnHighRisk : {}),
          }}
          onClick={() => !isLoading && onHandoff(sourceQuery)}
          disabled={isLoading}
          title={approval === 'HIGH_RISK' ? 'High-risk action — you will review before anything executes' : 'Prepare workflow for review'}
        >
          {approval === 'HIGH_RISK' ? 'Prepare Workflow (Review Required) →' : 'Prepare Workflow →'}
        </button>
      )}

      {/* Latency footer */}
      <p style={s.intelLatency}>{intelligence.latency_ms}ms intelligence</p>
    </div>
  )
}

// ── Research Report View ──────────────────────────────────────────────────────

interface ResearchReportViewProps {
  report: ResearchReport
  meta?: import('../types/assist').AssistMeta
  suggestedFollowups: string[]
  onFollowup: (q: string) => void
  onHandoff: (q: string) => void
  handoff?: { available: boolean; target: string | null }
  sourceQuery?: string
  isLoading: boolean
  intelligence?: IntelligenceLayer
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  web: 'Web',
  page_context: 'Page',
  ai_knowledge: 'AI',
}

function ResearchReportView({ report, meta, suggestedFollowups, onFollowup, onHandoff, handoff, sourceQuery, isLoading, intelligence }: ResearchReportViewProps) {
  const [showSources, setShowSources] = useState(false)
  const confidencePct = Math.round(report.confidence_score * 100)

  return (
    <div style={s.researchCard}>
      {/* Header */}
      <div style={s.researchHeader}>
        <span style={s.researchTag}>Research</span>
        <span style={s.researchTopic}>{report.topic}</span>
        <span style={{ ...s.researchConf, background: confidencePct >= 70 ? '#f0fdf4' : '#fffbeb', color: confidencePct >= 70 ? '#166534' : '#92400e', border: `1px solid ${confidencePct >= 70 ? '#86efac' : '#fde68a'}` }}>
          {confidencePct}% confidence
        </span>
      </div>

      {/* Executive summary */}
      <p style={s.researchSummary}>{report.executive_summary}</p>

      {/* Key findings */}
      {report.key_findings.length > 0 && (
        <div style={s.researchSection}>
          <p style={s.researchSectionLabel}>Key Findings</p>
          <ul style={s.researchList}>
            {report.key_findings.map((f, i) => <li key={i} style={s.researchItem}>{f}</li>)}
          </ul>
        </div>
      )}

      {/* Risks */}
      {report.risks.length > 0 && (
        <div style={s.researchSection}>
          <p style={s.researchSectionLabel}>Caveats & Risks</p>
          <ul style={s.researchList}>
            {report.risks.map((r, i) => <li key={i} style={{ ...s.researchItem, color: '#92400e' }}>{r}</li>)}
          </ul>
        </div>
      )}

      {/* Recommended actions */}
      {report.recommended_actions.length > 0 && (
        <div style={s.researchSection}>
          <p style={s.researchSectionLabel}>Recommended Actions</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            {report.recommended_actions.map((a, i) => (
              <span key={i} style={s.researchAction}>{a}</span>
            ))}
          </div>
        </div>
      )}

      {/* V4.0 Workflow Intelligence */}
      {intelligence?.opportunity.detected && intelligence.execution_plan && (
        <div style={s.researchSection}>
          <p style={s.researchSectionLabel}>Workflow Intelligence</p>
          <IntelligenceView
            intelligence={intelligence}
            onHandoff={onHandoff}
            sourceQuery={sourceQuery}
            isLoading={isLoading}
          />
        </div>
      )}

      {/* Sources toggle */}
      {report.sources.length > 0 && (
        <div style={s.researchSection}>
          <button
            style={s.sourcesToggle}
            onClick={() => setShowSources(v => !v)}
          >
            {showSources ? '▲' : '▼'} {report.sources.length} source{report.sources.length !== 1 ? 's' : ''}
          </button>
          {showSources && (
            <div style={{ marginTop: '6px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {report.sources.map(src => (
                <div key={src.source_id} style={s.sourceRow}>
                  <span style={{ ...s.sourceTypeBadge, background: src.source_type === 'page_context' ? '#eff6ff' : src.source_type === 'ai_knowledge' ? '#faf5ff' : '#f0fdf4', color: src.source_type === 'page_context' ? '#1d4ed8' : src.source_type === 'ai_knowledge' ? '#7e22ce' : '#166534' }}>
                    {SOURCE_TYPE_LABELS[src.source_type] ?? src.source_type}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {src.url
                      ? <a href={src.url} target="_blank" rel="noreferrer" style={s.sourceTitle}>{src.title}</a>
                      : <span style={s.sourceTitlePlain}>{src.title}</span>
                    }
                    <p style={s.sourceSnippet}>{src.snippet.slice(0, 120)}{src.snippet.length > 120 ? '…' : ''}</p>
                  </div>
                  <span style={s.sourceConf}>{Math.round(src.credibility_score * 100)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Handoff button */}
      {handoff?.available && sourceQuery && (
        <button
          style={{ ...s.handoffBtn, ...(isLoading ? s.chipDisabled : {}) }}
          onClick={() => !isLoading && onHandoff(sourceQuery)}
          disabled={isLoading}
        >
          Continue in Workflow →
        </button>
      )}

      {/* Follow-up chips */}
      {suggestedFollowups.length > 0 && (
        <div style={{ ...s.researchSection, display: 'flex', flexDirection: 'column', gap: '5px' }}>
          {suggestedFollowups.map(f => (
            <button key={f}
              style={{ ...s.followupChip, ...(isLoading ? s.chipDisabled : {}) }}
              onClick={() => !isLoading && onFollowup(f)}
              disabled={isLoading}
            >{f}</button>
          ))}
        </div>
      )}

      {meta && <p style={s.msgMeta}>{meta.latency_ms}ms</p>}
    </div>
  )
}

// ── Assist panel ─────────────────────────────────────────────────────────────

interface AssistPanelProps {
  onHandoffToWorkflow: (query: string) => void
}

function AssistPanel({ onHandoffToWorkflow }: AssistPanelProps) {
  const { state, summarize, ask, reset } = useAssist()
  const { phase, messages, error } = state
  const [question, setQuestion] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  const isLoading = phase === 'loading'
  const hasMessages = messages.length > 0

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, phase])

  const submitQuestion = () => {
    const q = question.trim()
    if (!q || isLoading) return
    setQuestion('')
    ask(q)
  }

  const handleQuestionKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); submitQuestion() }
  }

  return (
    <>
      {/* Tab-awareness bar */}
      <div style={s.assistBar}>
        <span style={s.assistBarDot} />
        <span style={s.assistBarLabel}>Reading current page</span>
        {hasMessages && (
          <button
            onClick={reset}
            style={{ ...s.newConvBtn, ...(isLoading ? s.chipDisabled : {}) }}
            disabled={isLoading}
          >
            New conversation
          </button>
        )}
      </div>

      {/* Network-level error banner */}
      {error && <p style={s.error}>{error}</p>}

      {/* Conversation thread */}
      {hasMessages && (
        <div style={s.thread}>
          {messages.map(msg => (
            <ChatMessageView key={msg.id} message={msg} onFollowup={ask}
              onHandoff={onHandoffToWorkflow} isLoading={isLoading} />
          ))}
          {isLoading && <p style={s.typingIndicator}>Working…</p>}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Quick actions */}
      <div style={s.chipRow}>
        <button
          style={{ ...s.chip, ...(isLoading ? s.chipDisabled : {}) }}
          onClick={() => summarize('page')}
          disabled={isLoading}
        >
          Summarize this page
        </button>
      </div>

      {/* Question input */}
      <div style={s.questionRow}>
        <input
          style={{ ...s.questionInput, ...(isLoading ? s.chipDisabled : {}) }}
          type="text"
          placeholder="Ask about this page…"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={handleQuestionKeyDown}
          disabled={isLoading}
        />
        <button
          style={{ ...s.askBtn, ...(isLoading || !question.trim() ? s.chipDisabled : {}) }}
          onClick={submitQuestion}
          disabled={isLoading || !question.trim()}
        >
          Ask
        </button>
      </div>
    </>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function truncate(s: string, max: number) { return s && s.length > max ? s.slice(0, max) + '…' : s }
function formatDate(iso: string) {
  try { return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }
  catch { return iso }
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s: Record<string, React.CSSProperties> = {
  container: { padding: '16px', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', fontSize: '13px', color: '#1a1a1a' },
  heading: { fontSize: '15px', fontWeight: 600, marginBottom: '10px' },
  tabBar: { display: 'flex', gap: '4px', marginBottom: '14px', borderBottom: '2px solid #e0e0e0' },
  tabBtn: { padding: '6px 14px', fontSize: '12px', fontWeight: 500, background: 'none', border: 'none', cursor: 'pointer', color: '#888', borderBottom: '2px solid transparent', marginBottom: '-2px' },
  tabActive: { color: '#2563eb', borderBottom: '2px solid #2563eb' },

  // Input & controls
  textarea: { width: '100%', padding: '8px', fontSize: '13px', border: '1px solid #ccc', borderRadius: '5px', resize: 'vertical', fontFamily: 'inherit', boxSizing: 'border-box' },
  controlRow: { display: 'flex', alignItems: 'center', gap: '6px', marginTop: '8px', marginBottom: '6px', flexWrap: 'wrap' as const },
  micBtn: { padding: '6px 10px', fontSize: '14px', background: '#f1f1f1', border: '1px solid #ccc', borderRadius: '5px', cursor: 'pointer', lineHeight: 1 },
  micActive: { background: '#fee2e2', border: '1px solid #fca5a5' },
  langSelect: { fontSize: '11px', padding: '4px 6px', border: '1px solid #ccc', borderRadius: '5px', background: '#fafafa', color: '#444', cursor: 'pointer', maxWidth: '130px' },
  primaryBtn: { padding: '7px 16px', fontSize: '13px', fontWeight: 500, background: '#2563eb', color: '#fff', border: 'none', borderRadius: '5px', cursor: 'pointer' },
  resetBtn: { padding: '7px 12px', fontSize: '13px', background: '#f1f1f1', border: '1px solid #ccc', borderRadius: '5px', cursor: 'pointer' },

  // Auto toggle
  autoLabel: { display: 'flex', alignItems: 'center', gap: '6px', marginLeft: 'auto', cursor: 'pointer', userSelect: 'none' as const },
  toggleTrack: { width: '32px', height: '18px', borderRadius: '9px', background: '#d1d5db', position: 'relative' as const, cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0 },
  toggleOn: { background: '#2563eb' },
  toggleThumb: { position: 'absolute' as const, top: '2px', left: '2px', width: '14px', height: '14px', borderRadius: '50%', background: '#fff', transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.2)' },
  toggleThumbOn: { left: '16px' },
  autoText: { fontSize: '12px', color: '#888', fontWeight: 500 },
  autoTextOn: { color: '#2563eb' },

  // Banners & errors
  autoBanner: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '5px', padding: '7px 10px', marginBottom: '6px', fontSize: '12px', color: '#1d4ed8' },
  stopInline: { padding: '3px 10px', fontSize: '11px', fontWeight: 600, background: '#e74c3c', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' },
  speechErr: { fontSize: '11px', color: '#c0392b', background: '#fdf0ee', padding: '6px 8px', borderRadius: '4px', border: '1px solid #f5c6c1', margin: '4px 0' },
  error: { marginTop: '6px', color: '#c0392b', fontSize: '12px', background: '#fdf0ee', padding: '8px 10px', borderRadius: '4px', border: '1px solid #f5c6c1' },

  // Results
  results: { marginTop: '10px' },
  analysisBox: { background: '#f0f7ff', border: '1px solid #bee3f8', borderRadius: '5px', padding: '10px', marginBottom: '10px' },
  analysisLabel: { fontSize: '10px', fontWeight: 600, textTransform: 'uppercase', color: '#2563eb', marginBottom: '4px' },
  analysisText: { fontSize: '12px', color: '#1e3a5f', lineHeight: 1.5, whiteSpace: 'pre-wrap', fontFamily: 'SFMono-Regular, Consolas, "Liberation Mono", Menlo, Courier, monospace' },
  convergenceBox: { background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '5px', padding: '8px 10px', marginBottom: '10px' },
  convergenceLabel: { fontSize: '10px', fontWeight: 700, color: '#92400e', textTransform: 'uppercase', marginBottom: '3px' },
  convergenceText: { fontSize: '12px', color: '#92400e', margin: 0 },

  // Live feed
  feed: { marginBottom: '10px', borderLeft: '3px solid #2563eb', paddingLeft: '10px' },
  feedRow: { display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '4px 0' },
  feedIcon: { fontSize: '12px', fontWeight: 700, marginTop: '1px', minWidth: '14px' },
  feedBody: { display: 'flex', flexWrap: 'wrap' as const, alignItems: 'center', gap: '4px', flex: 1 },
  feedStep: { fontSize: '9px', color: '#aaa', fontWeight: 600 },
  feedType: { fontSize: '9px', fontWeight: 700, background: '#1a1a1a', color: '#fff', padding: '1px 5px', borderRadius: '2px' },
  feedDesc: { fontSize: '11px', color: '#444', flex: 1 },
  feedErr: { fontSize: '10px', color: '#e74c3c', fontStyle: 'italic', width: '100%' },

  // Status cards
  statusCard: { display: 'flex', alignItems: 'center', gap: '8px', padding: '10px', background: '#f8f8f8', border: '1px solid #e0e0e0', borderRadius: '6px', marginBottom: '10px' },
  spinner: { fontSize: '14px' },
  statusMsg: { fontSize: '12px', color: '#555', fontStyle: 'italic' },

  // Clarification
  clarifyBox: { border: '1px solid #bfdbfe', borderRadius: '6px', padding: '10px', marginBottom: '10px', background: '#eff6ff' },
  clarifyLabel: { fontSize: '10px', fontWeight: 700, color: '#2563eb', textTransform: 'uppercase', marginBottom: '4px' },
  clarifyQuestion: { fontSize: '12px', color: '#1e3a5f', lineHeight: 1.4, marginBottom: '8px' },
  clarifyRow: { display: 'flex', gap: '6px', alignItems: 'center' },
  clarifyInput: { flex: 1, minWidth: 0, padding: '7px 8px', fontSize: '12px', border: '1px solid #93c5fd', borderRadius: '5px', fontFamily: 'inherit' },

  // Planner Contract V2 non-action outcomes
  reportBox: { border: '1px solid #86efac', borderRadius: '6px', padding: '10px', marginBottom: '10px', background: '#f0fdf4' },
  reportLabel: { fontSize: '10px', fontWeight: 700, color: '#166534', textTransform: 'uppercase', marginBottom: '4px' },
  reportAnswer: { fontSize: '14px', fontWeight: 700, color: '#14532d', lineHeight: 1.4, marginBottom: '5px' },
  reportClaim: { fontSize: '12px', color: '#166534', lineHeight: 1.5, marginBottom: '5px' },
  reportNote: { fontSize: '10px', color: '#4d7c0f', fontStyle: 'italic', margin: 0 },
  replanBox: { border: '1px solid #fed7aa', borderRadius: '6px', padding: '10px', marginBottom: '10px', background: '#fff7ed' },
  replanLabel: { fontSize: '10px', fontWeight: 700, color: '#c2410c', textTransform: 'uppercase', marginBottom: '4px' },
  replanReason: { fontSize: '12px', color: '#9a3412', lineHeight: 1.5, margin: 0 },

  // Action card
  card: { border: '2px solid #2563eb', borderRadius: '6px', padding: '10px', marginBottom: '10px', background: '#fff' },
  cardMeta: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' },
  cardStep: { fontSize: '10px', fontWeight: 600, color: '#2563eb', textTransform: 'uppercase', letterSpacing: '0.05em' },
  autoChip: { fontSize: '9px', fontWeight: 600, background: '#eff6ff', color: '#2563eb', padding: '2px 6px', borderRadius: '8px', border: '1px solid #bfdbfe' },
  dangerChip: { fontSize: '9px', fontWeight: 600, background: '#fff7ed', color: '#c2410c', padding: '2px 6px', borderRadius: '8px', border: '1px solid #fed7aa' },
  cardHeader: { display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' },
  actionType: { fontSize: '10px', fontWeight: 700, background: '#1a1a1a', color: '#fff', padding: '2px 6px', borderRadius: '3px', letterSpacing: '0.05em' },
  safetyBadge: { fontSize: '10px', fontWeight: 600, color: '#fff', padding: '2px 6px', borderRadius: '3px' },
  confidence: { fontSize: '11px', color: '#888', marginLeft: 'auto' },
  cardDescription: { fontSize: '12px', fontWeight: 500, marginBottom: '4px' },
  cardReasoning: { fontSize: '11px', color: '#555', marginBottom: '6px', lineHeight: 1.4 },
  selector: { display: 'block', fontSize: '11px', background: '#f5f5f5', padding: '3px 6px', borderRadius: '3px', marginBottom: '4px', wordBreak: 'break-all', color: '#444' },
  value: { fontSize: '11px', color: '#333', marginBottom: '4px' },
  actionButtons: { display: 'flex', gap: '6px', marginTop: '8px' },
  approveBtn: { padding: '5px 14px', fontSize: '12px', fontWeight: 500, background: '#27ae60', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' },
  rejectBtn: { padding: '5px 14px', fontSize: '12px', fontWeight: 500, background: '#e74c3c', color: '#fff', border: 'none', borderRadius: '4px', cursor: 'pointer' },

  // Queue
  queueBox: { background: '#fafafa', border: '1px solid #e0e0e0', borderRadius: '6px', padding: '8px 10px', marginBottom: '10px' },
  queueLabel: { fontSize: '10px', fontWeight: 600, color: '#888', textTransform: 'uppercase', marginBottom: '6px' },
  queueRow: { display: 'flex', alignItems: 'center', gap: '6px', padding: '3px 0', opacity: 0.6 },
  queueNum: { fontSize: '10px', fontWeight: 600, color: '#aaa', minWidth: '14px' },
  queueType: { fontSize: '9px', fontWeight: 700, background: '#ccc', color: '#fff', padding: '1px 5px', borderRadius: '2px' },
  queueDesc: { fontSize: '11px', color: '#888' },

  // Stop / complete
  stopBtn: { width: '100%', padding: '6px', fontSize: '12px', background: 'none', border: '1px solid #ddd', borderRadius: '4px', cursor: 'pointer', color: '#999', marginBottom: '8px' },
  completeBox: { padding: '10px', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: '6px', fontSize: '12px', fontWeight: 600, color: '#166534' },
  cancelledBox: { padding: '10px', background: '#fafafa', border: '1px solid #e0e0e0', borderRadius: '6px', fontSize: '12px', fontWeight: 600, color: '#555' },

  // Assist panel
  assistBar: { display: 'flex', alignItems: 'center', gap: '6px', background: '#f0f7ff', border: '1px solid #bfdbfe', borderRadius: '5px', padding: '6px 10px', marginBottom: '10px' },
  assistBarDot: { width: '6px', height: '6px', borderRadius: '50%', background: '#2563eb', flexShrink: 0 },
  assistBarLabel: { fontSize: '11px', color: '#1d4ed8', fontStyle: 'italic' },
  chipRow: { display: 'flex', gap: '6px', flexWrap: 'wrap' as const, marginBottom: '10px' },
  chip: { padding: '6px 14px', fontSize: '12px', fontWeight: 500, background: '#eff6ff', color: '#2563eb', border: '1px solid #bfdbfe', borderRadius: '16px', cursor: 'pointer' },
  chipDisabled: { opacity: 0.55, cursor: 'not-allowed' },
  assistInfo: { background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '5px', padding: '10px', marginBottom: '10px' },
  assistInfoText: { fontSize: '12px', color: '#92400e', marginBottom: '8px' },
  summaryBox: { background: '#fff', border: '1px solid #e0e0e0', borderRadius: '6px', overflow: 'hidden', marginTop: '4px' },
  summarySection: { padding: '10px 12px', borderBottom: '1px solid #f0f0f0' },
  summaryLabel: { fontSize: '9px', fontWeight: 700, textTransform: 'uppercase' as const, color: '#888', letterSpacing: '0.07em', marginBottom: '5px' },
  summaryTldr: { fontSize: '13px', color: '#1a1a1a', lineHeight: 1.5, fontWeight: 500 },
  summaryList: { margin: 0, paddingLeft: '16px' },
  summaryItem: { fontSize: '12px', color: '#333', lineHeight: 1.5, marginBottom: '3px' },
  entityGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' },
  entityCard: { background: '#f8f8f8', borderRadius: '4px', padding: '6px 8px', display: 'flex', flexDirection: 'column' as const, gap: '2px' },
  entityLabel: { fontSize: '9px', color: '#888', textTransform: 'uppercase' as const, fontWeight: 600 },
  entityValue: { fontSize: '12px', color: '#1a1a1a', fontWeight: 500 },
  actionChips: { display: 'flex', flexWrap: 'wrap' as const, gap: '5px' },
  actionChip: { fontSize: '11px', background: '#f0fdf4', color: '#166534', border: '1px solid #86efac', borderRadius: '12px', padding: '3px 10px' },
  summaryMeta: { padding: '8px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#fafafa' },
  metaText: { fontSize: '10px', color: '#aaa' },

  // Question input (Slice 2)
  questionRow: { display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '10px' },
  questionInput: { flex: 1, minWidth: 0, padding: '7px 10px', fontSize: '12px', border: '1px solid #bfdbfe', borderRadius: '16px', fontFamily: 'inherit', outline: 'none' },
  askBtn: { padding: '7px 14px', fontSize: '12px', fontWeight: 500, background: '#2563eb', color: '#fff', border: 'none', borderRadius: '16px', cursor: 'pointer', whiteSpace: 'nowrap' as const },

  // Answer card (Slice 2 — preserved for legacy; Slice 3 uses answerCard)
  answerBox: { background: '#fff', border: '1px solid #e0e0e0', borderRadius: '6px', overflow: 'hidden', marginTop: '4px' },
  answerQuestionBlock: { padding: '8px 12px 0', borderBottom: '1px solid #f0f0f0' },
  answerQuestionLabel: { fontSize: '9px', fontWeight: 700, textTransform: 'uppercase' as const, color: '#888', letterSpacing: '0.07em' },
  answerQuestionText: { fontSize: '12px', color: '#555', fontStyle: 'italic', margin: '3px 0 8px' },
  answerBody: { padding: '10px 12px' },
  answerText: { fontSize: '13px', color: '#1a1a1a', lineHeight: 1.6, whiteSpace: 'pre-wrap' as const },

  // Slice 3 — conversation thread
  thread: { marginTop: '8px', marginBottom: '8px', display: 'flex', flexDirection: 'column' as const, gap: '8px' },
  userBubble: { alignSelf: 'flex-end' as const, maxWidth: '85%', background: '#2563eb', borderRadius: '12px 12px 0 12px', padding: '8px 12px', alignItems: 'flex-end' as const },
  userBubbleText: { fontSize: '12px', color: '#fff', margin: 0, lineHeight: 1.5, wordBreak: 'break-word' as const },
  answerCard: { background: '#fff', border: '1px solid #e0e0e0', borderRadius: '6px', padding: '10px 12px' },
  msgMeta: { fontSize: '10px', color: '#aaa', margin: '6px 0 0' },
  assistError: { background: '#fdf0ee', border: '1px solid #f5c6c1', borderRadius: '6px', padding: '10px 12px' },
  assistErrorText: { fontSize: '12px', color: '#c0392b', margin: 0, lineHeight: 1.5 },
  typingIndicator: { fontSize: '12px', color: '#888', fontStyle: 'italic', margin: '2px 0 0', padding: '0 4px' },
  newConvBtn: { marginLeft: 'auto', fontSize: '11px', padding: '2px 8px', background: 'none', border: '1px solid #bfdbfe', borderRadius: '4px', cursor: 'pointer', color: '#2563eb', whiteSpace: 'nowrap' as const },
  followupChips: { display: 'flex', flexDirection: 'column' as const, gap: '5px' },
  followupChip: { padding: '6px 12px', fontSize: '11px', fontWeight: 500, background: '#fff', color: '#2563eb', border: '1px solid #bfdbfe', borderRadius: '6px', cursor: 'pointer', textAlign: 'left' as const, lineHeight: 1.4 },
  handoffBtn: { display: 'block', width: '100%', marginTop: '10px', marginBottom: '2px', padding: '8px 14px', fontSize: '12px', fontWeight: 600, background: '#2563eb', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer', textAlign: 'left' as const },

  // Research card (V3.5)
  researchCard: { background: '#fff', border: '1px solid #e0e0e0', borderRadius: '6px', overflow: 'hidden', marginTop: '4px' },
  researchHeader: { display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 12px', background: '#f0f7ff', borderBottom: '1px solid #bfdbfe' },
  researchTag: { fontSize: '9px', fontWeight: 700, textTransform: 'uppercase' as const, background: '#2563eb', color: '#fff', padding: '2px 6px', borderRadius: '3px', letterSpacing: '0.05em', flexShrink: 0 },
  researchTopic: { fontSize: '12px', fontWeight: 600, color: '#1e3a5f', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  researchConf: { fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: '10px', flexShrink: 0 },
  researchSummary: { fontSize: '12px', color: '#1a1a1a', lineHeight: 1.6, padding: '10px 12px', margin: 0, borderBottom: '1px solid #f0f0f0' },
  researchSection: { padding: '8px 12px', borderBottom: '1px solid #f0f0f0' },
  researchSectionLabel: { fontSize: '9px', fontWeight: 700, textTransform: 'uppercase' as const, color: '#888', letterSpacing: '0.07em', marginBottom: '5px' },
  researchList: { margin: 0, paddingLeft: '16px' },
  researchItem: { fontSize: '12px', color: '#333', lineHeight: 1.5, marginBottom: '3px' },
  researchAction: { fontSize: '11px', background: '#f0fdf4', color: '#166534', border: '1px solid #86efac', borderRadius: '4px', padding: '3px 8px' },
  sourcesToggle: { fontSize: '11px', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', padding: 0 },
  sourceRow: { display: 'flex', alignItems: 'flex-start', gap: '6px', padding: '4px 0', borderBottom: '1px solid #f8f8f8' },
  sourceTypeBadge: { fontSize: '9px', fontWeight: 700, padding: '2px 5px', borderRadius: '3px', flexShrink: 0, marginTop: '2px' },
  sourceTitle: { fontSize: '11px', fontWeight: 500, color: '#2563eb', textDecoration: 'none', display: 'block', marginBottom: '2px' },
  sourceTitlePlain: { fontSize: '11px', fontWeight: 500, color: '#333', display: 'block', marginBottom: '2px' },
  sourceSnippet: { fontSize: '10px', color: '#666', lineHeight: 1.4, margin: 0 },
  sourceConf: { fontSize: '10px', color: '#aaa', flexShrink: 0, minWidth: '28px', textAlign: 'right' as const },

  // V4.0 Intelligence
  intelBox: { marginTop: '6px', background: '#fafafa', border: '1px solid #e5e7eb', borderRadius: '5px', padding: '8px 10px', display: 'flex', flexDirection: 'column' as const, gap: '5px' },
  intelRow: { display: 'flex', alignItems: 'center', gap: '5px', flexWrap: 'wrap' as const },
  intelTag: { fontSize: '9px', fontWeight: 700, textTransform: 'uppercase' as const, background: '#1e3a5f', color: '#fff', padding: '2px 6px', borderRadius: '3px', letterSpacing: '0.04em' },
  intelApproval: { fontSize: '10px', fontWeight: 600, padding: '2px 7px', borderRadius: '10px' },
  intelReadiness: { fontSize: '10px', color: '#666' },
  intelConf: { fontSize: '10px', color: '#aaa', marginLeft: 'auto' },
  intelNextAction: { fontSize: '11px', color: '#374151', lineHeight: 1.4, margin: 0, fontStyle: 'italic' as const },
  intelMissingRow: { display: 'flex', alignItems: 'center', flexWrap: 'wrap' as const, gap: '4px' },
  intelMissingLabel: { fontSize: '10px', fontWeight: 600, color: '#92400e' },
  intelMissingChip: { fontSize: '10px', background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a', borderRadius: '3px', padding: '1px 6px' },
  intelRecsBox: { display: 'flex', flexDirection: 'column' as const, gap: '3px' },
  intelRecRow: { display: 'flex', alignItems: 'flex-start', gap: '5px' },
  intelRecDot: { width: '4px', height: '4px', borderRadius: '50%', background: '#6b7280', flexShrink: 0, marginTop: '5px' },
  intelRecText: { fontSize: '11px', color: '#374151', lineHeight: 1.4 },
  prepareBtn: { display: 'block', marginTop: '4px', padding: '7px 12px', fontSize: '12px', fontWeight: 600, background: '#1e3a5f', color: '#fff', border: 'none', borderRadius: '5px', cursor: 'pointer', textAlign: 'left' as const },
  prepareBtnHighRisk: { background: '#b91c1c' },
  intelLatency: { fontSize: '9px', color: '#d1d5db', margin: 0, textAlign: 'right' as const },

  // History
  histList: { marginTop: '4px' },
  histEmpty: { fontSize: '12px', color: '#888', textAlign: 'center', marginTop: '24px' },
  refreshBtn: { fontSize: '11px', padding: '3px 8px', background: '#f1f1f1', border: '1px solid #ddd', borderRadius: '4px', cursor: 'pointer', color: '#555' },
  sessionCard: { border: '1px solid #e0e0e0', borderRadius: '6px', marginBottom: '8px', background: '#fff', overflow: 'hidden' },
  sessionHeader: { width: '100%', textAlign: 'left', background: 'none', border: 'none', padding: '10px', cursor: 'pointer', display: 'block' },
  sessionMeta: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '2px' },
  sessionTitle: { fontSize: '12px', fontWeight: 600, color: '#1a1a1a', flex: 1, marginRight: '8px' },
  sessionDate: { fontSize: '10px', color: '#aaa', whiteSpace: 'nowrap' },
  sessionUrl: { fontSize: '10px', color: '#888', marginBottom: '6px', wordBreak: 'break-all' },
  sessionStats: { display: 'flex', alignItems: 'center', gap: '6px' },
  statChip: { fontSize: '10px', background: '#f0f7ff', color: '#2563eb', padding: '1px 6px', borderRadius: '10px', fontWeight: 500 },
  eventList: { borderTop: '1px solid #f0f0f0', padding: '6px 10px 8px' },
  eventRow: { display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '4px 0' },
  eventIcon: { fontSize: '11px', fontWeight: 700, marginTop: '1px', minWidth: '12px' },
  eventBody: { display: 'flex', flexDirection: 'column', gap: '1px', flex: 1 },
  eventType: { fontSize: '9px', fontWeight: 700, background: '#1a1a1a', color: '#fff', padding: '1px 5px', borderRadius: '2px', display: 'inline-block', width: 'fit-content' },
  eventDesc: { fontSize: '11px', color: '#444' },
  eventResult: { fontSize: '10px', color: '#e74c3c', fontStyle: 'italic' },
}
