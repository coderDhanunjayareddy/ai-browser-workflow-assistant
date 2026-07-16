export const PLANNER_SUPPLEMENTAL_CONTEXT_BUDGET = 3000

export type PlannerContextPriority = 1 | 2 | 3 | 4

export interface PlannerContextSection {
  heading: string
  content: string
  priority: PlannerContextPriority
}

interface PreparedSection extends PlannerContextSection {
  text: string
}

const SECTION_SEPARATOR = '\n\n'
const TRUNCATION_MARKER = '\n[trimmed]'

export function buildBudgetedPlannerContext(
  sections: PlannerContextSection[],
  budget = PLANNER_SUPPLEMENTAL_CONTEXT_BUDGET,
): string {
  const prepared = sections
    .map(prepareSection)
    .filter((section) => section.text.length > 0)

  const full = joinSections(prepared)
  if (full.length <= budget) return full

  const priority1 = prepared.filter((section) => section.priority === 1)
  const priority2 = prepared.filter((section) => section.priority === 2)
  const priority3 = prepared.filter((section) => section.priority === 3)

  const candidates = [
    prepared.filter((section) => section.priority !== 4),
    prepared.filter((section) => section.priority <= 2),
    [...priority1, ...priority2].sort((a, b) => prepared.indexOf(a) - prepared.indexOf(b)),
    priority1,
  ]

  for (const candidate of candidates) {
    const fitted = fitOrderedSections(candidate, budget)
    if (fitted.length > 0 && joinSections(fitted).length <= budget) return joinSections(fitted)
  }

  const fallback = fitOrderedSections([...priority1, ...priority3].sort((a, b) => prepared.indexOf(a) - prepared.indexOf(b)), budget)
  return joinSections(fallback).slice(0, budget)
}

function prepareSection(section: PlannerContextSection): PreparedSection {
  const heading = compactText(section.heading)
  const content = compactText(section.content)
  const text = [heading, content].filter(Boolean).join('\n')
  return { ...section, heading, content, text }
}

function fitSection(section: PreparedSection, available: number): PreparedSection | null {
  const minimum = section.heading.length
  if (available < minimum) return null
  if (section.text.length <= available) return section

  if (available <= section.heading.length + TRUNCATION_MARKER.length + 1) {
    return { ...section, content: '', text: section.heading.slice(0, available) }
  }

  const contentBudget = available - section.heading.length - 1
  const trimmedContent = trimText(section.content, contentBudget)
  return {
    ...section,
    content: trimmedContent,
    text: [section.heading, trimmedContent].filter(Boolean).join('\n'),
  }
}

function fitOrderedSections(sections: PreparedSection[], budget: number): PreparedSection[] {
  const selected: PreparedSection[] = []
  for (const section of sections) {
    const remaining = remainingBudget(selected, budget)
    if (remaining <= 0) continue
    const fitted = fitSection(section, remaining)
    if (fitted) selected.push(fitted)
  }
  return selected
}

function remainingBudget(selected: PreparedSection[], budget: number): number {
  const used = joinSections(selected).length
  if (selected.length === 0) return budget
  return budget - used - SECTION_SEPARATOR.length
}

function joinSections(sections: PreparedSection[]): string {
  return sections.map((section) => section.text).filter(Boolean).join(SECTION_SEPARATOR)
}

function trimText(text: string, maxChars: number): string {
  if (maxChars <= 0) return ''
  if (text.length <= maxChars) return text
  if (maxChars <= TRUNCATION_MARKER.length) return text.slice(0, maxChars)
  const available = maxChars - TRUNCATION_MARKER.length
  const boundary = Math.max(
    text.lastIndexOf('\n', available),
    text.lastIndexOf(' ', available),
  )
  const cut = boundary > 40 ? boundary : available
  return `${text.slice(0, cut).trimEnd()}${TRUNCATION_MARKER}`
}

function compactText(text: string | null | undefined): string {
  return (text || '').replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim()
}
