// Shared types across the extension.
// Populated incrementally as phases are implemented.

export type ActionType = string
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
  href?: string
  semantic_kind?: string
  selector_id?: string
}

export interface ContentBlock {
  text: string
  selector: string
  href?: string
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
  intent_id?: string | null
  mission_id?: string | null
  action_type: ActionType
  target_selector: string
  value: string | null
  description: string
  reasoning: string
  confidence: number
  safety_level: SafetyLevel
  grounding?: ActionGrounding
  content_insertion?: ContentInsertionDeclaration | null
  consequential_submission?: ConsequentialSubmissionDeclaration | null
}

export interface ContentInsertionDeclaration {
  schema_version: 'content_insertion_request.v1'
  request_id: string
  kind: 'local_file' | 'document' | 'image' | 'video' | 'audio' | 'camera' | 'contact' | 'poll' | 'event' | 'sticker' | 'gif' | 'emoji'
  expected_effect: 'preview_then_send' | 'selection_sends_immediately' | 'inserts_into_composer' | 'structured_draft' | 'device_capture'
  requires_bound_file: boolean
  destination_entity: string
  stage: 'open_insertion_menu' | 'select_bound_content'
  opens_native_chooser: boolean
  reveal_selector?: string | null
}

export interface ConsequentialSubmissionDeclaration {
  schema_version: 'consequential_submission.v1'
  submission_id: string
  operation: 'send' | 'share' | 'submit' | 'post' | 'publish'
  destination_entity: string
  content_identity: string
  preview_required: boolean
  verification_mode: 'delivered_content_and_destination'
}

export interface ActionGrounding {
  source: 'dom_snapshot' | 'accessibility_snapshot' | 'vision_region'
  selector_id?: string | null
  frame_id?: string | null
  accessibility_name?: string | null
  role?: string | null
  semantic_kind?: string | null
  expected_url_path?: string | null
  screenshot_verified?: boolean
  screenshot_hash?: string | null
  bounding_box?: { x: number; y: number; width: number; height: number } | null
}

export type ExpectedEffectKind =
  | 'url_change'
  | 'target_state_change'
  | 'value_change'
  | 'selection_change'
  | 'viewport_change'
  | 'tab_state_change'
  | 'page_state_change'
  | 'no_mutation'

export interface CanonicalActionContract {
  schema_version: '1.0'
  dispatch_id: string
  action: SuggestedAction
  target_identity: {
    kind: 'element' | 'url' | 'tab' | 'page'
    selector: string | null
    selector_id: string | null
    exact_name: string | null
    role: string | null
    semantic_kind: string | null
  }
  grounding_policy: {
    ordered_sources: ['stable_selector', 'accessibility_name', 'verified_screenshot']
    accessibility_requires_exact_name: true
    screenshot_coordinates_verified: boolean
    screenshot_hash: string | null
  }
  origin: {
    origin: string
    observed_url: string
    target_url: string | null
  }
  browser_binding: {
    tab_id: number
    window_id: number | null
    frame_id: string
  }
  resource_identity: {
    url: string
    title: string
  }
  expected_effect: {
    kind: ExpectedEffectKind
    description: string
    url_path?: string | null
  }
  safety_class: SafetyLevel
  idempotency_key: string
}

export interface PolicyProvenanceLabel {
  source_type: 'user' | 'planner' | 'page' | 'tool' | 'system'
  source_id: string
  trust: 'trusted' | 'untrusted'
  labels: string[]
}

export interface PolicyExecutionContext {
  session_id: string
  provenance: PolicyProvenanceLabel[]
  origin_grant_id?: string | null
  confirmation_receipt_id?: string | null
}

export type PlannerOutcomeKind = 'act' | 'wait' | 'ask' | 'report' | 'replan'

export interface ReportOutcome {
  answer?: string | null
  claim: string
}

export interface ReplanOutcome {
  reason: string
}

export interface IntentExecutionEvidence {
  evidence_id: string
  source: string
  kind: string
  summary: string
  references?: string[]
  payload?: Record<string, unknown>
}

export interface IntentExecutionResult {
  schema_version?: string
  intent_id: string
  intent: string
  owner: string
  capability: string
  dispatch_target: string
  status:
    | 'succeeded'
    | 'waiting_browser'
    | 'browser_action_required'
    | 'user_interaction_required'
    | 'waiting_external'
    | 'mission_completed'
    | 'failed'
    | 'blocked'
  reason: string
  evidence?: IntentExecutionEvidence[]
  next_intents?: unknown[]
  blocking_reason?: string | null
  browser_action?: Record<string, unknown> | null
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
  execution_orchestrator?: PhaseExecutionDirective | null
  intent_execution?: IntentExecutionResult | null
}

export interface IntentDTO {
  intent_id: string
  mission_id: string
  parent_intent_id?: string | null
  intent: string
  provider: string
  capability: string
  status: string
  payload: Record<string, unknown>
  evidence: Record<string, unknown>[]
}

export interface IntentUpdateResponse {
  updated: boolean
  intent: IntentDTO
  next_intent?: IntentDTO | null
  status: string
  reason: string
}

export interface IntentNextResponse {
  intent?: IntentDTO | null
  status: string
  reason: string
}

export interface MissionResultArtifact {
  artifact_id: string
  mission_result_id: string
  mission_id: string
  kind: string
  title: string
  content_type: string
  content: string
  structured: Record<string, unknown>
  metadata: Record<string, unknown>
  created_at: string
}

export interface MissionResult {
  mission_result_id: string
  mission_id: string
  outcome: string
  final_answer: string
  report_format: string
  report_artifact_id?: string | null
  knowledge_artifact_id?: string | null
  completion_reason: string
  confidence: number
  metadata: Record<string, unknown>
  artifacts: MissionResultArtifact[]
  created_at: string
  updated_at: string
}

export interface PhaseExecutionDirective {
  schema_version?: string
  active_phase: string
  should_replan?: boolean
  reason: string
  continuation_actions: SuggestedAction[]
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
  browser_evidence?: Record<string, string | number | boolean | null>
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
  page_context?: PageContext
  browser_timeline?: Record<string, number | string | boolean | null>
  form_field_name?: string | null
  form_field_label?: string | null
  form_field_type?: string | null
  form_id?: string | null
  field_valid?: boolean
  validation_message?: string | null
  form_valid?: boolean
  invalid_field_count?: number
  filled_field_count?: number
  submit_control_detected?: boolean
  next_page_url?: string | null
  pagination_mode?: string | null
  pagination_control_label?: string | null
  pagination_used_fallback_click?: boolean
  verification?: ActionVerification
  execution_duration_ms?: number
  recovery_attempted?: boolean
  recovery_selector?: string | null
  recovery_source?: string | null
  recovery_verified?: boolean
  recovery_reason?: string | null
  upload_attempted?: boolean
  upload_completed?: boolean
  upload_target_selector?: string | null
  upload_input_hidden?: boolean
  upload_files_count?: number
  upload_backed_by_file_input?: boolean
  upload_requires_user_file_selection?: boolean
  upload_accepted?: boolean
  content_request_id?: string
  content_kind?: string
  insertion_effect?: string
  destination_origin?: string
  destination_entity?: string
  content_sha256?: string | null
  preview_identity_observed?: boolean
  chooser_cancelled?: boolean
  submission_id?: string
  submission_operation?: string
  submission_attempted?: boolean
  submission_duplicate_prevented?: boolean
  delivery_verified?: boolean
  delivered_content_identity?: string | null
  delivered_destination_entity?: string | null
  dispatch_uncertain?: boolean
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
  wave4_capability?: string
  wave4_validated?: boolean
  wave4_details?: Record<string, string | number | boolean | null>
  semantic_mismatch?: boolean
  semantic_mismatch_reason?: string | null
  semantic_mismatch_observed_result?: string | null
  semantic_mismatch_assessment?: string | null
  execution_adapter?: 'dom' | 'cdp'
  adapter_trace?: Record<string, string | number | boolean | null>
  cdp_grounding_source?: string | null
  cdp_frame_count?: number
  cdp_target_count?: number
  cdp_screenshot_hash?: string | null
  dispatch_id?: string
  dispatch_path?: string
  contract_schema_version?: string
  contract_idempotency_key?: string
  contract_target_name?: string | null
  contract_resource_url?: string
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
  | { type: 'EXTRACT_CONTEXT'; tab_id?: number }
  | { type: 'CONTEXT_RESULT'; context: PageContext }
  | { type: 'EXECUTE_ACTION'; contract: CanonicalActionContract; policy_context: PolicyExecutionContext }
  | { type: 'GET_TAB_WORKSPACE' }
  | { type: 'GET_RUNTIME_IDENTITY' }
  | { type: 'EXECUTION_RESULT'; action_id: string; result: 'success' | 'failure' | 'element_not_found'; error: string | null }
