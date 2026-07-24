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
  kind: 'id' | 'title' | 'purpose' | 'url'
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
  const prefixed = raw.match(/^(tab|id|title|purpose|url)\s*:\s*(.+)$/i)
  if (prefixed) {
    const prefix = prefixed[1].toLowerCase()
    const value = compactText(prefixed[2])
    if (!value) return null
    if (prefix === 'tab' || prefix === 'id') return { kind: 'id', value }
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
    return workspace.tabs.find((tab) => tab.tab_id === id) ?? null
  }
  if (reference.kind === 'title') {
    return workspace.tabs.find((tab) => tab.title.toLowerCase() === value) ?? null
  }
  if (reference.kind === 'purpose') {
    return workspace.tabs.find((tab) => tab.purpose.toLowerCase() === value) ?? null
  }
  if (reference.kind === 'url') {
    return workspace.tabs.find((tab) => urlsMatch(tab.url, value)) ?? null
  }
  return null
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
  } catch {
    return false
  }
  return false
}

function isGoogleSearchUrl(url: URL): boolean {
  return url.hostname.toLowerCase().endsWith('google.com') && url.pathname.startsWith('/search')
}
