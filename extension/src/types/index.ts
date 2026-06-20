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

export interface AnalyzeResponse {
  session_id: string
  analysis: string
  clarification_question?: string | null
  suggested_actions: SuggestedAction[]
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

export interface ExecutionResult {
  success: boolean
  message: string
  action_id: string
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
  | { type: 'EXECUTION_RESULT'; action_id: string; result: 'success' | 'failure' | 'element_not_found'; error: string | null }
