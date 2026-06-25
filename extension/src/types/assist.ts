export interface ReadView {
  url: string
  title: string
  favicon: string
  headings: string[]
  content_blocks: Array<{ selector: string; text: string }>
  visible_text: string
  selected_text: string
  metadata: Record<string, string>
}

export interface AssistHandoff {
  available: boolean
  target: string | null
}

export interface AssistMeta {
  tokens: number
  latency_ms: number
  cache_hit: boolean
  context_chars: number
}

export interface StructuredSummary {
  tldr: string
  key_points: string[]
  entities: Array<{ label: string; value: string }>
  available_actions: string[]
}

export interface AssistRequest {
  conversation_id: string
  message: string
  read_view: ReadView
  context_fingerprint: string
  selection_scope: 'page' | 'selection'
}

// V2.6 Cognitive Core types

export interface CognitiveEntity {
  id: string
  type: string
  name: string
  aliases: string[]
  metadata: Record<string, unknown>
  confidence: number
  source_turn: number
}

export interface WorkflowHandoffPayload {
  query: string
  goal_text: string | null
  goal_status: string | null
  entities: CognitiveEntity[]
  conversation_summary: string
  turn_count: number
}

// V3.5 Research Engine types

export interface ResearchSource {
  source_id: string
  title: string
  url: string
  source_type: 'web' | 'page_context' | 'ai_knowledge'
  snippet: string
  credibility_score: number
}

export interface ResearchReport {
  executive_summary: string
  key_findings: string[]
  supporting_evidence: Array<{
    finding: string
    source_title: string
    source_url: string
    is_conclusion: boolean
  }>
  risks: string[]
  open_questions: string[]
  recommended_actions: string[]
  confidence_score: number
  sources: ResearchSource[]
  session_id: string
  topic: string
}

// V4.0 Intelligence Layer types

export type IntelligenceActionType =
  | 'book' | 'purchase' | 'register' | 'download' | 'schedule'
  | 'communicate' | 'navigate' | 'rent' | 'apply' | 'search' | 'unknown'

export type ReadinessState = 'READY' | 'PARTIALLY_READY' | 'BLOCKED'
export type ApprovalLevel = 'SAFE' | 'REQUIRES_APPROVAL' | 'HIGH_RISK'

export interface ExecutionOpportunity {
  detected: boolean
  confidence: number
  action_type: IntelligenceActionType
  required_entities: string[]
  missing_information: string[]
  workflow_candidate: boolean
}

export interface WorkflowReadiness {
  state: ReadinessState
  ready_entities: string[]
  missing_entities: string[]
  blocking_reason: string | null
  readiness_score: number
}

export interface GoalNode {
  node_id: string
  text: string
  parent_id: string | null
  children: string[]
  is_leaf: boolean
}

export interface GoalTree {
  root_id: string
  nodes: Record<string, GoalNode>
  depth: number
  leaf_count: number
}

export interface ExecutionPlan {
  plan_id: string
  goal: string
  workflow_type: string
  required_inputs: string[]
  inferred_inputs: Record<string, string>
  missing_inputs: string[]
  confidence: number
  recommended_next_action: string
  approval_level: ApprovalLevel
  goal_tree?: GoalTree | null
}

export interface WorkflowRecommendation {
  recommendation_id: string
  action: string
  readiness: ReadinessState
  confidence: number
  approval_level: ApprovalLevel
  plan_id: string
}

export interface BootstrapFacts {
  query: string
  goal_text: string | null
  workflow_type: string
  goal_tree_summary: string[]
  pre_filled_entities: Record<string, string>
  research_topic: string
  research_summary: string
  confidence: number
  approval_level: ApprovalLevel
}

export interface IntelligenceLayer {
  opportunity: ExecutionOpportunity
  readiness: WorkflowReadiness | null
  execution_plan: ExecutionPlan | null
  goal_tree: GoalTree | null
  recommendations: WorkflowRecommendation[]
  bootstrap_facts: BootstrapFacts | null
  latency_ms: number
}

export interface AssistResponse {
  conversation_id: string
  intent: string
  routed_to: 'light' | 'fallback' | 'research'
  type: 'summary' | 'not_implemented' | 'answer' | 'handoff' | 'research_report'
  content: StructuredSummary | string
  citations: unknown[]
  suggested_followups: string[]
  available_actions: string[]
  handoff: AssistHandoff
  meta: AssistMeta
  handoff_payload?: WorkflowHandoffPayload | null  // V2.6 Cognitive Core
  research_report?: ResearchReport | null           // V3.5 Research Engine
  intelligence?: IntelligenceLayer | null           // V4.0 Intelligence Layer
  task_id?: string | null                           // V4.5 Unified Task Graph
  task_state?: string | null                        // V4.5 Unified Task Graph
}

export type AssistPhase = 'idle' | 'loading' | 'complete' | 'error'

export type ChatMessageType = 'user_text' | 'summary' | 'answer' | 'not_implemented' | 'research_report' | 'error'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  type: ChatMessageType
  content: StructuredSummary | string
  suggestedFollowups: string[]
  availableActions: string[]
  handoff?: { available: boolean; target: string | null }
  sourceQuery?: string
  meta?: AssistMeta
  researchReport?: ResearchReport     // V3.5
  intelligence?: IntelligenceLayer    // V4.0
  taskId?: string                     // V4.5
  taskState?: string                  // V4.5
  timestamp: number
}

export interface AssistState {
  conversationId: string
  phase: AssistPhase
  messages: ChatMessage[]
  error: string | null
}
