import { useState, useEffect, useCallback } from 'react'
import { useWorkflow } from './hooks/useWorkflow'
import { useHistory } from './hooks/useHistory'
import { useSpeechInput } from './hooks/useSpeechInput'
import type { SuggestedAction, SessionHistory, EventHistory } from '../types'

type Tab = 'workflow' | 'history'

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
      </div>
      {activeTab === 'workflow'
        ? <WorkflowPanel {...workflow} />
        : <HistoryPanel sessions={history.sessions} loading={history.loading}
            error={history.error} onRefresh={history.fetchHistory} />}
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
    if (state.phase !== 'awaiting') return
    if (state.pendingActions.length === 0) return
    const timer = setTimeout(() => approveAction(), 800)
    return () => clearTimeout(timer)
  }, [autoMode, state.phase, state.pendingActions, approveAction])

  // ── Derived state ─────────────────────────────────────────────────────────
  const { phase, task, analysisText, pendingActions, activeAction, completedActions, error, clarificationQuestion } = state
  const isWorking   = phase === 'extracting' || phase === 'analyzing' || phase === 'executing' || phase === 'reanalyzing'
  const isAwaiting  = phase === 'awaiting'
  const needsInput  = phase === 'needs_input'
  const isComplete  = phase === 'complete'
  const isRunning   = isWorking || isAwaiting || needsInput

  const phaseLabel: Record<string, string> = {
    idle: 'Analyze', extracting: 'Reading page…', analyzing: 'Thinking…',
    awaiting: 'Analyze', executing: 'Executing…', reanalyzing: 'Re-analyzing…',
    needs_input: 'Waiting for info', complete: 'Analyze',
  }

  const showResults = analysisText || completedActions.length > 0 || pendingActions.length > 0 || activeAction || isComplete || needsInput

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
          {phase === 'reanalyzing' && (
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
