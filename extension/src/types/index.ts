// Shared types across the extension.
// Populated incrementally as phases are implemented.

export type ActionType =
  | 'click'
  | 'fill'
  | 'scroll'
  | 'navigate'
  | 'wait'
  | 'select_option'
  | 'choose_date'
  | 'hover'
  | 'keyboard_shortcut'
  | 'rich_text'
  | 'insert_rich_text'
  | 'edit_rich_text'
  | 'monaco_edit'
  | 'codemirror_edit'
  | 'drag_drop'
  | 'virtual_list_find'
  | 'shadow_click'
  | 'shadow_fill'
  | 'infinite_scroll'
  | 'advanced_keyboard'
  | 'clipboard'
  | 'canvas_action'
  | 'svg_action'
  | 'pdf_viewer'
  | 'chart_action'
  | 'map_action'
  | 'media_control'
  | 'file_preview'
  | 'visual_region'
  | 'open_new_tab'
  | 'switch_tab'
  | 'close_tab'
  | 'focus_existing_tab'
export type SafetyLevel = 'safe' | 'caution' | 'danger'

export interface InteractiveElement {
  element_id?: string
  type: string
  text: string
  selector: string
  visible: boolean
  input_type?: string
  placeholder?: string
  role?: string
  aria_label?: string
  accessibility_name?: string
  state?: Record<string, string | boolean>
  bounding_box?: {
    x: number
    y: number
    width: number
    height: number
  }
}

export interface ContentBlock {
  text: string
  selector: string
}

export interface PageContext {
  tab_id?: number
  window_id?: number
  url: string
  title: string
  metadata: Record<string, string>
  interactive_elements: InteractiveElement[]
  content_blocks: ContentBlock[]
  headings: string[]
  selected_text: string
  /** Visible page text, truncated to 2000 chars. Used by AI for context. */
  visible_text: string
  images: string[]
}

export interface SuggestedAction {
  action_id: string
  action_type: ActionType
  target_selector: string
  value: string | null
  description: string
  reasoning: string
  confidence: number
  safety_level: SafetyLevel
}

export type PlannerOutcomeKind = 'act' | 'wait' | 'ask' | 'report' | 'replan'

export interface ReportOutcome {
  answer?: string | null
  claim: string
}

export interface ReplanOutcome {
  reason: string
}

export interface AnalyzeResponse {
  session_id: string
  analysis: string
  /** Planner Contract V2 outcome. Optional for backward compatibility. */
  outcome_kind?: PlannerOutcomeKind
  clarification_question?: string | null
  report?: ReportOutcome | null
  replan?: ReplanOutcome | null
  suggested_actions: SuggestedAction[]
  /**
   * Production SGV Phase 1: true when the backend verified the report claim
   * against live page evidence.  Absent or false means unverified.
   */
  sgv_verified?: boolean
  /**
   * Production Goal Convergence GC-1: passive semantic stagnation signal.
   * Presentation-only in the extension; it does not change execution.
   */
  goal_convergence?: boolean
}

export interface PriorStep {
  action_type: string
  description: string
  target_selector: string | null
  value: string | null
  execution_result: string
  page_analysis?: string
  page_url?: string
  page_title?: string
  page_metadata?: Record<string, string>
}

export interface CompletedAction {
  action: SuggestedAction
  result: ExecutionResult
  analysis_snapshot?: string
  page_snapshot?: {
    url: string
    title: string
    metadata: Record<string, string>
  }
}

export type VerificationReason = 'verified' | 'no_effect' | 'execution_failed' | 'not_applicable'

export interface ActionVerificationTargetState {
  exists: boolean
  selector: string | null
  tagName?: string
  inputType?: string | null
  value?: string | null
  filled?: boolean
  checked?: boolean | null
  selectedValue?: string | null
  selectedText?: string | null
  ariaExpanded?: string | null
  visible?: boolean
}

export interface ActionVerificationState {
  url: string
  title: string
  domSignature: string
  visibleTextLength: number
  interactiveCount: number
  activeElementSignature: string | null
  modalCount: number
  dialogCount: number
  expandedStates: string[]
  checkboxStates: string[]
  scrollX: number
  scrollY: number
  target?: ActionVerificationTargetState
}

export interface ActionVerification {
  verified: boolean
  reason: VerificationReason
  before_state: ActionVerificationState
  after_state: ActionVerificationState
  signals: Record<string, boolean | number | string | null>
}

export interface ExecutionResult {
  success: boolean
  message: string
  action_id: string
  verification?: ActionVerification
  execution_duration_ms?: number
  recovery_attempted?: boolean
  recovery_selector?: string | null
  recovery_source?: string | null
  recovery_verified?: boolean
  recovery_reason?: string | null
  upload_attempted?: boolean
  upload_completed?: boolean
  download_detected?: boolean
  download_completed?: boolean
  filename?: string | null
  mime_type?: string | null
  size_bytes?: number | null
  download_path_ref?: string | null
  opened_tab_id?: number | null
  previous_tab_id?: number | null
  active_tab_id?: number | null
  closed_tab_id?: number | null
  tab_switch_verified?: boolean
  rich_text_editor?: string
  rich_text_mode?: string
  rich_text_validated?: boolean
  inserted_length?: number
  shortcuts_applied?: string[]
  wave2_capability?: string
  wave2_validated?: boolean
  wave2_details?: Record<string, string | number | boolean | null>
  wave3_capability?: string
  wave3_validated?: boolean
  wave3_details?: Record<string, string | number | boolean | null>
  semantic_mismatch?: boolean
  semantic_mismatch_reason?: string | null
  semantic_mismatch_observed_result?: string | null
  semantic_mismatch_assessment?: string | null
}

export interface EventHistory {
  id: string
  event_type: string
  action_type: string | null
  description: string | null
  target_selector: string | null
  value: string | null
  execution_result: string | null
  safety_level: string | null
  confidence: number | null
  created_at: string
}

export interface SessionHistory {
  id: string
  tab_url: string
  tab_title: string
  status: string
  created_at: string
  events: EventHistory[]
}

// Internal extension message types
export type ExtensionMessage =
  | { type: 'EXTRACT_CONTEXT'; tabId: number }
  | { type: 'CONTEXT_RESULT'; context: PageContext }
  | { type: 'EXECUTE_ACTION'; action: SuggestedAction }
  | { type: 'GET_TAB_WORKSPACE' }
  | { type: 'EXECUTION_RESULT'; action_id: string; result: 'success' | 'failure' | 'element_not_found'; error: string | null }
