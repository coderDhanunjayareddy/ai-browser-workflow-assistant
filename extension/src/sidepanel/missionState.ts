import type { CompletedAction, PriorStep } from '../types'
import type { TaskWorkspace } from './taskWorkspace'
import type { MultiTabWorkspace } from '../workspace/multiTabWorkspace'

const MAX_OBJECTIVES = 8
const MAX_EVIDENCE = 10
const MAX_BLOCKERS = 6
const MAX_SNAPSHOT_CHARS = 1800

export type MissionStatus = 'not_started' | 'in_progress' | 'blocked' | 'ready_to_report' | 'completed'
export type MissionConfidence = 'low' | 'medium' | 'high'

export interface MissionSnapshot {
  goal: string
  missionStatus: MissionStatus
  completedObjectives: string[]
  remainingObjectives: string[]
  evidenceCollected: string[]
  currentFocus: string | null
  knownBlockers: string[]
  confidence: MissionConfidence
  progressEstimate: number
}

export interface MissionUpdateInput {
  goal: string
  workspace?: TaskWorkspace | null
  tabWorkspace?: MultiTabWorkspace | null
  completedActions?: CompletedAction[]
  validationPriorSteps?: PriorStep[]
  verifiedReport?: boolean
  goalConvergence?: boolean
}

export function createMissionSnapshot(goal: string): MissionSnapshot {
  const cleanGoal = compactText(goal)
  return {
    goal: cleanGoal,
    missionStatus: 'not_started',
    completedObjectives: [],
    remainingObjectives: cleanGoal ? [cleanGoal] : [],
    evidenceCollected: [],
    currentFocus: cleanGoal || null,
    knownBlockers: [],
    confidence: 'low',
    progressEstimate: 0,
  }
}

export function updateMissionSnapshot(input: MissionUpdateInput): MissionSnapshot {
  const goal = compactText(input.goal)
  const workspace = input.workspace
  const completedActions = input.completedActions ?? []
  const validationPriorSteps = input.validationPriorSteps ?? []

  const completedObjectives = boundUnique([
    ...(workspace?.completedObjectives ?? []),
    ...completedActions
      .filter(({ result }) => result.success)
      .map(({ action }) => action.description),
  ], MAX_OBJECTIVES)

  const remainingObjectives = boundUnique(
    (workspace?.pendingObjectives?.length ? workspace.pendingObjectives : goal ? [goal] : [])
      .filter((objective) => !completedObjectives.some((completed) => sameObjective(objective, completed))),
    MAX_OBJECTIVES,
  )

  const evidenceCollected = boundUnique([
    ...(workspace?.extractedFacts ?? []).map((fact) =>
      `${fact.subject}: ${fact.label} = ${fact.value}`
    ),
    ...(input.tabWorkspace?.tabs ?? [])
      .filter((tab) => tab.facts_count > 0)
      .map((tab) => `${tab.title || 'Tab'}: ${tab.facts_count} facts`),
  ], MAX_EVIDENCE)

  const knownBlockers = boundUnique([
    ...completedActions.flatMap(({ result }) => {
      const blockers: string[] = []
      if (!result.success) blockers.push('Previous browser action did not complete successfully.')
      if (result.verification && !result.verification.verified) {
        blockers.push('Previous browser action did not produce the intended browser effect.')
      }
      if (result.semantic_mismatch) {
        blockers.push('Previous selector reached a page state unrelated to the intended goal.')
      }
      return blockers
    }),
    ...repeatedActionBlockers(completedActions),
    ...validationPriorSteps
      .filter((step) => /Report Validation/i.test(step.description) || /Result:\s*Rejected/i.test(step.execution_result))
      .map(() => 'Previous report was rejected by validation.'),
    input.goalConvergence ? 'Semantic progress has stalled.' : '',
  ], MAX_BLOCKERS)

  const currentFocus = compactText(
    workspace?.currentTarget ||
    remainingObjectives[0] ||
    input.tabWorkspace?.current_target ||
    goal,
  ) || null

  const missionStatus = determineStatus({
    verifiedReport: Boolean(input.verifiedReport),
    blockers: knownBlockers.length,
    completed: completedObjectives.length,
    remaining: remainingObjectives.length,
    evidence: evidenceCollected.length,
  })
  const progressEstimate = estimateProgress(completedObjectives.length, remainingObjectives.length, missionStatus)
  const confidence = determineConfidence(evidenceCollected.length, knownBlockers.length, progressEstimate, missionStatus)

  return {
    goal,
    missionStatus,
    completedObjectives,
    remainingObjectives,
    evidenceCollected,
    currentFocus,
    knownBlockers,
    confidence,
    progressEstimate,
  }
}

export function summarizeMissionSnapshot(snapshot: MissionSnapshot | null | undefined): string {
  if (!snapshot) return ''

  const lines = [
    'Mission Snapshot',
    `Goal: ${snapshot.goal || 'Not specified'}`,
    `Mission Status: ${snapshot.missionStatus}`,
    `Progress: ${snapshot.progressEstimate}%`,
  ]

  if (snapshot.completedObjectives.length > 0) {
    lines.push('Completed:')
    lines.push(...snapshot.completedObjectives.map((objective) => `- ${objective}`))
  }

  if (snapshot.remainingObjectives.length > 0) {
    lines.push('Remaining:')
    lines.push(...snapshot.remainingObjectives.map((objective) => `- ${objective}`))
  }

  if (snapshot.evidenceCollected.length > 0) {
    lines.push('Evidence Collected:')
    lines.push(...snapshot.evidenceCollected.map((evidence) => `- ${evidence}`))
  }

  if (snapshot.knownBlockers.length > 0) {
    lines.push('Known Blockers:')
    lines.push(...snapshot.knownBlockers.map((blocker) => `- ${blocker}`))
  }

  if (snapshot.currentFocus) lines.push(`Current Focus: ${snapshot.currentFocus}`)
  lines.push(`Confidence: ${snapshot.confidence}`)

  return lines.join('\n').slice(0, MAX_SNAPSHOT_CHARS)
}

function determineStatus(input: {
  verifiedReport: boolean
  blockers: number
  completed: number
  remaining: number
  evidence: number
}): MissionStatus {
  if (input.verifiedReport) return 'completed'
  if (input.blockers > 0) return 'blocked'
  if (input.remaining === 0 && input.evidence > 0) return 'ready_to_report'
  if (input.completed > 0 || input.evidence > 0) return 'in_progress'
  return 'not_started'
}

function estimateProgress(completed: number, remaining: number, status: MissionStatus): number {
  if (status === 'completed') return 100
  if (completed === 0 && remaining === 0) return 0
  const total = Math.max(1, completed + remaining)
  const estimate = Math.round((completed / total) * 100)
  if (status === 'ready_to_report') return Math.max(80, estimate)
  if (status === 'blocked') return Math.min(estimate, 75)
  return Math.max(0, Math.min(95, estimate))
}

function determineConfidence(
  evidenceCount: number,
  blockerCount: number,
  progressEstimate: number,
  status: MissionStatus,
): MissionConfidence {
  if (status === 'completed') return 'high'
  if (blockerCount > 0) return evidenceCount > 0 ? 'medium' : 'low'
  if (evidenceCount >= 3 && progressEstimate >= 60) return 'high'
  if (evidenceCount > 0 || progressEstimate > 0) return 'medium'
  return 'low'
}

function repeatedActionBlockers(completedActions: CompletedAction[]): string[] {
  const counts = new Map<string, number>()
  for (const { action } of completedActions) {
    const key = [
      action.action_type,
      action.target_selector || '',
      action.value || '',
    ].join('|').toLowerCase()
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  return [...counts.values()].some((count) => count >= 2)
    ? ['Repeated browser action observed.']
    : []
}

function boundUnique(values: string[], limit: number): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    const clean = compactText(value)
    const key = clean.toLowerCase()
    if (!clean || seen.has(key)) continue
    seen.add(key)
    result.push(clean)
  }
  return result.slice(-limit)
}

function sameObjective(a: string, b: string): boolean {
  const left = compactText(a).toLowerCase()
  const right = compactText(b).toLowerCase()
  return left === right || left.includes(right) || right.includes(left)
}

function compactText(text: string | null | undefined): string {
  return (text || '').replace(/\s+/g, ' ').trim()
}
