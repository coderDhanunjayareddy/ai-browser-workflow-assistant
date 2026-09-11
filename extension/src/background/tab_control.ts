import type { MultiTabWorkspace, TabWorkspaceEntry } from '../workspace/multiTabWorkspace'

export type TabControlActionType = 'open_new_tab' | 'switch_tab' | 'close_tab' | 'focus_existing_tab'

export interface TabControlAction {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
}

export interface TabReference {
  kind: 'id' | 'ordinal' | 'title' | 'purpose' | 'url'
  value: string
}

export interface ClosableTabLike {
  id?: number
  url?: string
  pinned?: boolean
}

export function isTabControlAction(action: TabControlAction): action is TabControlAction & { action_type: TabControlActionType } {
  return action.action_type === 'open_new_tab' ||
    action.action_type === 'switch_tab' ||
    action.action_type === 'close_tab' ||
    action.action_type === 'focus_existing_tab'
}

export function parseTabReference(action: TabControlAction): TabReference | null {
  const raw = compactText(action.value || action.target_selector || '')
  if (!raw) return null
  const prefixed = raw.match(/^(tab|id|ordinal|title|purpose|url)\s*:\s*(.+)$/i)
  if (prefixed) {
    const prefix = prefixed[1].toLowerCase()
    const value = compactText(prefixed[2])
    if (!value) return null
    if (prefix === 'tab' || prefix === 'id') return { kind: 'id', value }
    if (prefix === 'ordinal') return { kind: 'ordinal', value }
    if (prefix === 'title') return { kind: 'title', value }
    if (prefix === 'purpose') return { kind: 'purpose', value }
    if (prefix === 'url') return { kind: 'url', value }
  }
  if (/^\d+$/.test(raw)) return { kind: 'id', value: raw }
  if (/^https?:\/\//i.test(raw)) return { kind: 'url', value: raw }
  return { kind: 'title', value: raw }
}

export function normalizeOpenTabUrl(value: string | null): string | null {
  const raw = compactText(value)
  const direct = raw.match(/^https?:\/\/\S+$/i)
  if (direct) return stripTrailingPunctuation(direct[0])

  const embedded = raw.match(/https?:\/\/[^\s<>"']+/i)
  if (!embedded) return null
  return stripTrailingPunctuation(embedded[0])
}

export function findTabEntryByReference(
  workspace: MultiTabWorkspace,
  reference: TabReference,
): TabWorkspaceEntry | null {
  const value = compactText(reference.value).toLowerCase()
  if (!value) return null
  if (reference.kind === 'id') {
    const id = Number(value)
    return workspace.tabs.find((tab) => tab.tab_id === id) ?? tabByOrdinal(workspace, id)
  }
  if (reference.kind === 'ordinal') {
    return tabByOrdinal(workspace, Number(value))
  }
  if (reference.kind === 'title') {
    return workspace.tabs.find((tab) => tab.title.toLowerCase() === value) ?? null
  }
  if (reference.kind === 'purpose') {
    return workspace.tabs.find((tab) => tab.purpose.toLowerCase() === value) ?? null
  }
  if (reference.kind === 'url') {
    const matches = workspace.tabs.filter((tab) => tab.status !== 'closed' && urlsMatch(tab.url, value))
    // URL normalization can intentionally omit an SPA fragment. Never turn
    // that lossy identity into an arbitrary tab choice when two live tabs
    // share the same document URL.
    return matches.length === 1 ? matches[0] : null
  }
  return null
}

function tabByOrdinal(workspace: MultiTabWorkspace, ordinal: number): TabWorkspaceEntry | null {
  if (!Number.isInteger(ordinal) || ordinal < 1) return null
  const candidates = workspace.tabs
    .filter((tab) => tab.status !== 'closed' && !isRestrictedTabUrl(tab.url))
    .filter((tab) => !isSearchResultsUrl(tab.url))
    .sort((a, b) => a.last_visited - b.last_visited)
  const pool = candidates.length > 0
    ? candidates
    : workspace.tabs.filter((tab) => tab.status !== 'closed' && !isRestrictedTabUrl(tab.url)).sort((a, b) => a.last_visited - b.last_visited)
  return pool[ordinal - 1] ?? null
}

export function canCloseTab(tab: ClosableTabLike | null | undefined, openTabCount: number): { allowed: boolean; reason: string } {
  if (!tab?.id) return { allowed: false, reason: 'tab_not_found' }
  if (openTabCount <= 1) return { allowed: false, reason: 'refused_last_tab' }
  if (tab.pinned) return { allowed: false, reason: 'refused_pinned_tab' }
  if (isRestrictedTabUrl(tab.url)) return { allowed: false, reason: 'refused_restricted_tab' }
  return { allowed: true, reason: 'allowed' }
}

export function isRestrictedTabUrl(url: string | undefined): boolean {
  if (!url) return false
  return url.startsWith('chrome://') ||
    url.startsWith('chrome-extension://') ||
    url.startsWith('edge://') ||
    url.startsWith('about:')
}

function compactText(text: string | null | undefined): string {
  return (text || '').replace(/\s+/g, ' ').trim()
}

function stripTrailingPunctuation(url: string): string {
  return url.replace(/[),.;\]]+$/g, '')
}

function urlsMatch(tabUrl: string, referenceUrl: string): boolean {
  const normalizedTabUrl = compactText(tabUrl).replace(/\/$/, '').toLowerCase()
  const normalizedReferenceUrl = compactText(referenceUrl).replace(/\/$/, '').toLowerCase()
  if (normalizedTabUrl === normalizedReferenceUrl) return true
  try {
    const tab = new URL(tabUrl)
    const reference = new URL(referenceUrl)
    if (isGoogleSearchUrl(tab) && isGoogleSearchUrl(reference)) {
      return compactText(tab.searchParams.get('q')).toLowerCase() === compactText(reference.searchParams.get('q')).toLowerCase()
    }
    if (
      tab.protocol.toLowerCase() === reference.protocol.toLowerCase() &&
      tab.hostname.toLowerCase() === reference.hostname.toLowerCase() &&
      effectivePort(tab) === effectivePort(reference) &&
      normalizePath(tab.pathname) === normalizePath(reference.pathname) &&
      tab.search === reference.search
    ) {
      // Workspace entries may omit a client-side route fragment even though
      // the live tab reference retains it. A unique base-document match is
      // safe; conflicting explicit fragments are not.
      return !tab.hash || !reference.hash || tab.hash === reference.hash
    }
  } catch {
    return false
  }
  return false
}

function effectivePort(url: URL): string {
  if (url.port) return url.port
  if (url.protocol.toLowerCase() === 'https:') return '443'
  if (url.protocol.toLowerCase() === 'http:') return '80'
  return ''
}

function normalizePath(pathname: string): string {
  const value = pathname || '/'
  return value.length > 1 ? value.replace(/\/+$/, '') : value
}

function isGoogleSearchUrl(url: URL): boolean {
  return url.hostname.toLowerCase().endsWith('google.com') && url.pathname.startsWith('/search')
}

function isSearchResultsUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return parsed.pathname.startsWith('/search') || parsed.searchParams.has('q')
  } catch {
    return false
  }
}
