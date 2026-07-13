const MAX_TRACKED_TABS = 20
const MAX_TAB_SUMMARY_CHARS = 1200

export type TabStatus = 'active' | 'visited' | 'completed' | 'closed'

export interface BrowserTabLike {
  id?: number
  windowId?: number
  url?: string
  title?: string
  active?: boolean
  status?: string
}

export interface TabWorkspaceEntry {
  tab_id: number
  window_id: number | null
  url: string
  title: string
  purpose: string
  status: TabStatus
  last_visited: number
  is_active: boolean
  visited: boolean
  facts_count: number
}

export interface MultiTabWorkspace {
  tabs: TabWorkspaceEntry[]
  active_tab_id: number | null
  current_target: string | null
}

export function createMultiTabWorkspace(): MultiTabWorkspace {
  return {
    tabs: [],
    active_tab_id: null,
    current_target: null,
  }
}

export function registerTab(
  workspace: MultiTabWorkspace,
  tab: BrowserTabLike,
  now = Date.now(),
): MultiTabWorkspace {
  if (typeof tab.id !== 'number') return workspace
  const existing = workspace.tabs.find((entry) => entry.tab_id === tab.id)
  const title = compactText(tab.title || existing?.title || titleFromUrl(tab.url || existing?.url || ''))
  const url = normalizeUrl(tab.url || existing?.url || '')
  const isActive = Boolean(tab.active)
  const entry: TabWorkspaceEntry = {
    tab_id: tab.id,
    window_id: typeof tab.windowId === 'number' ? tab.windowId : existing?.window_id ?? null,
    url,
    title,
    purpose: existing?.purpose || derivePurpose(title, url),
    status: isActive ? 'active' : existing?.status === 'completed' ? 'completed' : 'visited',
    last_visited: isActive ? now : existing?.last_visited ?? now,
    is_active: isActive,
    visited: existing?.visited || isActive || Boolean(url),
    facts_count: existing?.facts_count ?? 0,
  }

  const tabs = workspace.tabs.filter((candidate) => candidate.tab_id !== tab.id)
  const next = normalizeActiveState({
    ...workspace,
    tabs: [...tabs, entry],
    active_tab_id: isActive ? tab.id : workspace.active_tab_id,
    current_target: workspace.current_target || entry.purpose,
  }, now)

  return pruneTabs(next)
}

export function updateTab(
  workspace: MultiTabWorkspace,
  tabId: number,
  patch: Partial<Omit<TabWorkspaceEntry, 'tab_id'>>,
  now = Date.now(),
): MultiTabWorkspace {
  const tabs = workspace.tabs.map((entry) => {
    if (entry.tab_id !== tabId) return entry
    const title = compactText(patch.title ?? entry.title)
    const url = normalizeUrl(patch.url ?? entry.url)
    return {
      ...entry,
      ...patch,
      title,
      url,
      purpose: patch.purpose ? compactText(patch.purpose) : entry.purpose || derivePurpose(title, url),
      last_visited: patch.is_active ? now : patch.last_visited ?? entry.last_visited,
      visited: patch.visited ?? entry.visited ?? Boolean(url),
    }
  })
  return pruneTabs(normalizeActiveState({ ...workspace, tabs }, now))
}

export function activateTab(
  workspace: MultiTabWorkspace,
  tabId: number,
  now = Date.now(),
): MultiTabWorkspace {
  const tabs = workspace.tabs.map((entry) => {
    if (entry.tab_id === tabId) {
      return {
        ...entry,
        status: 'active' as TabStatus,
        is_active: true,
        visited: true,
        last_visited: now,
      }
    }
    return {
      ...entry,
      status: entry.status === 'active' ? 'visited' : entry.status,
      is_active: false,
    }
  })
  return pruneTabs({
    ...workspace,
    tabs,
    active_tab_id: tabId,
  })
}

export function updateTabPurpose(
  workspace: MultiTabWorkspace,
  tabId: number,
  purpose: string,
): MultiTabWorkspace {
  return updateTab(workspace, tabId, { purpose: compactText(purpose) })
}

export function updateTabFactCount(
  workspace: MultiTabWorkspace,
  tabId: number | null | undefined,
  factsCount: number,
): MultiTabWorkspace {
  if (typeof tabId !== 'number') return workspace
  return updateTab(workspace, tabId, { facts_count: Math.max(0, Math.floor(factsCount)) })
}

export function markTabCompleted(workspace: MultiTabWorkspace, tabId: number): MultiTabWorkspace {
  return updateTab(workspace, tabId, { status: 'completed', is_active: workspace.active_tab_id === tabId })
}

export function removeClosedTab(workspace: MultiTabWorkspace, tabId: number): MultiTabWorkspace {
  const tabs = workspace.tabs.filter((entry) => entry.tab_id !== tabId)
  const activeTabId = workspace.active_tab_id === tabId ? null : workspace.active_tab_id
  return {
    ...workspace,
    tabs,
    active_tab_id: activeTabId,
  }
}

export function summarizeMultiTabWorkspace(workspace: MultiTabWorkspace | null | undefined): string {
  if (!workspace || workspace.tabs.length === 0) return ''

  const active = workspace.tabs.find((entry) => entry.is_active || entry.tab_id === workspace.active_tab_id)
  const lines = ['Tab Workspace']
  if (active) lines.push(`Active: ${active.title || 'Untitled Tab'}`)
  lines.push('Open Tabs:')

  const ordered = [...workspace.tabs].sort((a, b) => {
    if (a.is_active !== b.is_active) return a.is_active ? -1 : 1
    return b.last_visited - a.last_visited
  })

  lines.push(...ordered.slice(0, MAX_TRACKED_TABS).map((entry, index) => {
    const facts = entry.facts_count > 0 ? `, Facts: ${entry.facts_count}` : ''
    return `${index + 1}. ${entry.title || 'Untitled Tab'} - ${entry.status}${facts}`
  }))

  if (workspace.current_target) {
    lines.push(`Current Target: ${workspace.current_target}`)
  }

  return lines.join('\n').slice(0, MAX_TAB_SUMMARY_CHARS)
}

export function tabSnapshotFromChromeTab(tab: BrowserTabLike): BrowserTabLike {
  return {
    id: tab.id,
    windowId: tab.windowId,
    url: tab.url,
    title: tab.title,
    active: tab.active,
    status: tab.status,
  }
}

function normalizeActiveState(workspace: MultiTabWorkspace, now: number): MultiTabWorkspace {
  const active = workspace.tabs.find((entry) => entry.is_active)
  if (!active) return workspace

  return {
    ...workspace,
    active_tab_id: active.tab_id,
    tabs: workspace.tabs.map((entry) => {
      if (entry.tab_id === active.tab_id) {
        return { ...entry, status: 'active', is_active: true, visited: true, last_visited: Math.max(entry.last_visited, now) }
      }
      return { ...entry, status: entry.status === 'active' ? 'visited' : entry.status, is_active: false }
    }),
  }
}

function pruneTabs(workspace: MultiTabWorkspace): MultiTabWorkspace {
  if (workspace.tabs.length <= MAX_TRACKED_TABS) return workspace
  const activeTabId = workspace.active_tab_id
  const sorted = [...workspace.tabs].sort((a, b) => {
    if (a.tab_id === activeTabId) return 1
    if (b.tab_id === activeTabId) return -1
    if (a.status === 'closed' && b.status !== 'closed') return -1
    if (b.status === 'closed' && a.status !== 'closed') return 1
    return a.last_visited - b.last_visited
  })
  const removeCount = workspace.tabs.length - MAX_TRACKED_TABS
  const removeIds = new Set(sorted.slice(0, removeCount).map((entry) => entry.tab_id))
  return {
    ...workspace,
    tabs: workspace.tabs.filter((entry) => !removeIds.has(entry.tab_id)),
  }
}

function derivePurpose(title: string, url: string): string {
  const text = `${title} ${url}`.toLowerCase()
  if (/\b(search|google|bing|duckduckgo)\b/.test(text)) return 'Search'
  if (/\b(pricing|plans|billing)\b/.test(text)) return 'Collect pricing'
  if (/\b(github|repository|repo)\b/.test(text)) return 'Repository research'
  if (/\b(docs|documentation|api reference)\b/.test(text)) return 'Documentation research'
  if (title) return `Review ${title}`
  return 'Review page'
}

function titleFromUrl(url: string): string {
  try {
    const parsed = new URL(url)
    return parsed.hostname || 'Untitled Tab'
  } catch {
    return 'Untitled Tab'
  }
}

function normalizeUrl(url: string): string {
  if (!url) return ''
  try {
    const parsed = new URL(url)
    parsed.hash = ''
    return parsed.toString()
  } catch {
    return compactText(url)
  }
}

function compactText(text: string | null | undefined): string {
  return (text || '').replace(/\s+/g, ' ').trim()
}
