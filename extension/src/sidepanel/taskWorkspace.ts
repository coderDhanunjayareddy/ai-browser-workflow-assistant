import type { CompletedAction, PageContext } from '../types'

const MAX_FACTS = 25
const MAX_VISITED_URLS = 25
const MAX_COMPLETED_OBJECTIVES = 20
const MAX_PENDING_OBJECTIVES = 20
const MAX_ENTITIES = 25
const MAX_NOTES = 12
const MAX_SUMMARY_CHARS = 1600

export interface WorkspaceFact {
  subject: string
  label: string
  value: string
}

export interface TaskWorkspace {
  goal: string
  completedObjectives: string[]
  pendingObjectives: string[]
  visitedUrls: string[]
  extractedFacts: WorkspaceFact[]
  namedEntities: string[]
  currentTarget: string | null
  notes: string[]
}

export function createTaskWorkspace(goal: string): TaskWorkspace {
  const cleanGoal = compactText(goal)
  return {
    goal: cleanGoal,
    completedObjectives: [],
    pendingObjectives: boundUnique(deriveInitialObjectives(cleanGoal), MAX_PENDING_OBJECTIVES),
    visitedUrls: [],
    extractedFacts: [],
    namedEntities: extractNamedEntities(cleanGoal),
    currentTarget: cleanGoal || null,
    notes: [],
  }
}

export function updateTaskWorkspace(
  workspace: TaskWorkspace,
  pageContext: PageContext,
  completedActions: CompletedAction[] = [],
): TaskWorkspace {
  const successfulActions = completedActions.filter(({ result }) => result.success)
  const completedObjectives = boundUnique([
    ...workspace.completedObjectives,
    ...successfulActions.map(({ action }) => action.description).filter(Boolean),
  ], MAX_COMPLETED_OBJECTIVES)

  const pendingObjectives = boundUnique(
    workspace.pendingObjectives.filter((objective) =>
      !completedObjectives.some((completed) => sameObjective(objective, completed))
    ),
    MAX_PENDING_OBJECTIVES,
  )

  const url = normalizeUrl(pageContext.url)
  const visitedUrls = url
    ? boundUnique([...workspace.visitedUrls, url], MAX_VISITED_URLS)
    : workspace.visitedUrls.slice(-MAX_VISITED_URLS)

  const extractedFacts = boundFacts([
    ...workspace.extractedFacts,
    ...extractFacts(pageContext),
  ])

  const namedEntities = boundUnique([
    ...workspace.namedEntities,
    ...extractNamedEntities(pageContext.title),
    ...pageContext.headings.flatMap(extractNamedEntities),
  ], MAX_ENTITIES)

  const latestAction = completedActions[completedActions.length - 1]?.action.description
  const currentTarget = pendingObjectives[0] ?? latestAction ?? pageContext.title ?? workspace.currentTarget
  const notes = boundUnique([
    ...workspace.notes,
    pageContext.title ? `Observed page: ${compactText(pageContext.title)}` : '',
  ].filter(Boolean), MAX_NOTES)

  return {
    goal: workspace.goal,
    completedObjectives,
    pendingObjectives,
    visitedUrls,
    extractedFacts,
    namedEntities,
    currentTarget: currentTarget ? compactText(currentTarget) : null,
    notes,
  }
}

export function summarizeTaskWorkspace(workspace: TaskWorkspace | null | undefined): string {
  if (!workspace) return ''

  const lines = [
    'Workspace Summary',
    `Goal: ${workspace.goal || 'Not specified'}`,
  ]

  if (workspace.completedObjectives.length > 0) {
    lines.push('Completed:')
    lines.push(...workspace.completedObjectives.slice(-5).map((objective) => `- ${objective}`))
  }

  if (workspace.pendingObjectives.length > 0) {
    lines.push('Pending:')
    lines.push(...workspace.pendingObjectives.slice(0, 5).map((objective) => `- ${objective}`))
  }

  lines.push(`Visited: ${workspace.visitedUrls.length} pages`)

  if (workspace.extractedFacts.length > 0) {
    lines.push('Facts:')
    lines.push(...workspace.extractedFacts.slice(-8).map((fact) =>
      `- ${fact.subject}: ${fact.label} = ${fact.value}`
    ))
  }

  if (workspace.namedEntities.length > 0) {
    lines.push(`Named Entities: ${workspace.namedEntities.slice(-8).join(', ')}`)
  }

  if (workspace.currentTarget) {
    lines.push(`Current Target: ${workspace.currentTarget}`)
  }

  return lines.join('\n').slice(0, MAX_SUMMARY_CHARS)
}

function deriveInitialObjectives(goal: string): string[] {
  const cleaned = compactText(goal)
  if (!cleaned) return []

  const parts = cleaned
    .split(/\b(?:and then|then|and|,|;)\b/i)
    .map(compactText)
    .filter((part) => part.length >= 4)

  return parts.length > 1 ? parts : [cleaned]
}

function extractFacts(pageContext: PageContext): WorkspaceFact[] {
  const facts: WorkspaceFact[] = []
  const subject = compactText(pageContext.title || hostFromUrl(pageContext.url) || 'Current page')

  if (pageContext.title) {
    facts.push({ subject, label: 'Title', value: compactText(pageContext.title).slice(0, 160) })
  }

  for (const [key, value] of Object.entries(pageContext.metadata || {}).slice(0, 8)) {
    const cleanValue = compactText(String(value))
    if (cleanValue) facts.push({ subject, label: compactText(key).slice(0, 60), value: cleanValue.slice(0, 180) })
  }

  for (const heading of pageContext.headings.slice(0, 5)) {
    const cleanHeading = compactText(heading)
    if (cleanHeading) facts.push({ subject, label: 'Heading', value: cleanHeading.slice(0, 160) })
  }

  const visibleLines = pageContext.visible_text
    .split(/\n+/)
    .map(compactText)
    .filter(Boolean)
    .slice(0, 40)

  for (const line of visibleLines) {
    const keyValue = line.match(/^([A-Za-z][A-Za-z0-9 ._/-]{1,50})\s*[:\-]\s*(.{2,120})$/)
    if (keyValue) {
      facts.push({
        subject,
        label: compactText(keyValue[1]).slice(0, 60),
        value: compactText(keyValue[2]).slice(0, 160),
      })
    }

    const price = line.match(/(?:[$€£₹]|INR|USD|EUR|GBP)\s?[0-9][0-9,]*(?:\.[0-9]{2})?/i)
    if (price) {
      facts.push({ subject, label: 'Price', value: price[0].slice(0, 80) })
    }
  }

  return facts
}

function extractNamedEntities(text: string): string[] {
  return Array.from(text.matchAll(/\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,3}\b/g))
    .map((match) => compactText(match[0]))
    .filter((entity) => entity.length >= 3 && !/^(The|This|That|And|For|With)$/i.test(entity))
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

function boundFacts(facts: WorkspaceFact[]): WorkspaceFact[] {
  const seen = new Set<string>()
  const result: WorkspaceFact[] = []
  for (const fact of facts) {
    const cleanFact = {
      subject: compactText(fact.subject).slice(0, 80),
      label: compactText(fact.label).slice(0, 60),
      value: compactText(fact.value).slice(0, 180),
    }
    const key = `${cleanFact.subject}|${cleanFact.label}|${cleanFact.value}`.toLowerCase()
    if (!cleanFact.subject || !cleanFact.label || !cleanFact.value || seen.has(key)) continue
    seen.add(key)
    result.push(cleanFact)
  }
  return result.slice(-MAX_FACTS)
}

function normalizeUrl(url: string): string {
  try {
    const parsed = new URL(url)
    parsed.hash = ''
    return parsed.toString().replace(/\/$/, '')
  } catch {
    return compactText(url)
  }
}

function hostFromUrl(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return ''
  }
}

function sameObjective(a: string, b: string): boolean {
  const left = compactText(a).toLowerCase()
  const right = compactText(b).toLowerCase()
  return left === right || left.includes(right) || right.includes(left)
}

function compactText(text: string | null | undefined): string {
  return (text || '').replace(/\s+/g, ' ').trim()
}
