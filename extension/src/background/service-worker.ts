import { extractPageContext, mergeInteractiveElementLists, resolveObservedSelectorAliases } from '../content/extractor'
import { APP_VERSION, BACKEND_URL, BUILD_COMMIT, BUILD_ID } from '../config'
import { extractPageContextV2 } from '../content/extractor_v2'
import {
  captureVerificationState,
  createFallbackVerificationState,
  verifyActionEffect,
  type ActionVerificationState,
  type BasicExecutionResult,
  type VerifiedExecutionResult,
} from '../content/action_verification'
import {
  inspectContentInsertionSelection,
  prepareContentInsertionSelectionInspection,
} from '../content/content_insertion_evidence'
import {
  inspectConsequentialSubmission,
  verifyConsequentialDelivery,
  type SubmissionPageEvidence,
} from '../content/consequential_submission_evidence'
import { executeRichTextAction } from '../content/rich_text'
import { executeWave2CoreAction, isWave2CoreAction } from '../content/wave2_core'
import { executeWave3VisualAction, isWave3VisualAction } from '../content/wave3_visual'
import {
  verifyExactOpenedTarget,
  type ExactTargetVerificationResult,
} from '../content/exact_target_verification'
import {
  canCloseTab,
  findTabEntryByReference,
  isTabControlAction,
  normalizeOpenTabUrl,
  parseTabReference,
} from './tab_control'
import { isGroundedBrowserTarget, isSelectableBrowserTarget } from './target_tab'
import {
  validateServiceWorkerMessage,
  type ExecutableAction,
  type PolicyExecutionContext,
} from './service_worker_message_validation'
import type { CanonicalActionContract } from '../types'
import {
  attachCanonicalContractEvidence,
  requiresExactOpenedTargetVerification,
} from '../execution/canonical_action_contract'
import { enforceLivePolicy } from './live_policy_client'
import { CdpController } from './cdp_control'
import {
  activateTab,
  createMultiTabWorkspace,
  registerTab,
  removeClosedTab,
  tabSnapshotFromChromeTab,
  updateTab,
  type MultiTabWorkspace,
} from '../workspace/multiTabWorkspace'
import { ConsequentialSubmissionLedger } from './consequential_submission_ledger'
import { downloadMetadata } from './file_transfer_metadata'

const POLICY_BACKEND_URL = BACKEND_URL
const CONTENT_RESERVATIONS_KEY = 'content_insertion_reservations_v1'
const submissionLedger = new ConsequentialSubmissionLedger(chrome.storage.local)

type TrustedLocalFile = {
  absolute_path: string
  filename: string
  mime_type: string
  size_bytes: number
  source: 'chrome_downloads_exact_match' | 'local_downloads_broker_exact_match'
}

function leafName(path: string): string {
  return String(path || '').split(/[\\/]/).pop() || ''
}

async function waitForExpectedDownload(
  startedAt: number,
  expectedFilename: string,
  expectedUrl: string,
  observedDownloads: Map<number, chrome.downloads.DownloadItem>,
  timeoutMs = 30_000,
): Promise<BasicExecutionResult> {
  const cutoff = new Date(startedAt - 500).toISOString()
  const deadline = Date.now() + timeoutMs
  let detected: chrome.downloads.DownloadItem | null = null
  while (Date.now() < deadline) {
    const items = await chrome.downloads.search({ startedAfter: cutoff, orderBy: ['-startTime'], limit: 20 })
    const candidates = new Map<number, chrome.downloads.DownloadItem>()
    for (const item of [...observedDownloads.values(), ...items]) candidates.set(item.id, item)
    const matches = [...candidates.values()].filter((item) => {
      const nameMatches = !expectedFilename
        || leafName(item.filename || '').normalize('NFKC').toLocaleLowerCase()
          === expectedFilename.normalize('NFKC').toLocaleLowerCase()
      const urlMatches = !expectedUrl || item.url === expectedUrl || item.finalUrl === expectedUrl
      return nameMatches && urlMatches
    })
    if (matches.length > 1) {
      return {
        success: false,
        message: 'More than one download matched the exact requested resource; completion was not attributed.',
        action_id: '',
        download_detected: true,
        download_completed: false,
      }
    }
    detected = matches[0] ?? detected
    if (detected?.state === 'interrupted') {
      return {
        success: false,
        message: `The exact download was interrupted (${detected.error || 'unknown reason'}).`,
        action_id: '',
        ...downloadMetadata(detected, false),
      }
    }
    if (detected?.state === 'complete' && detected.exists !== false) {
      return {
        success: true,
        message: `Downloaded and verified the exact file: ${leafName(detected.filename)}`,
        action_id: '',
        ...downloadMetadata(detected, true),
      }
    }
    await sleep(100)
  }
  return {
    success: false,
    message: detected
      ? 'The exact download was detected but did not complete within the bounded verification window.'
      : 'No download matching the exact observed resource was detected within the bounded verification window.',
    action_id: '',
    ...(detected ? downloadMetadata(detected, false) : { download_detected: false, download_completed: false }),
  }
}

function armExpectedDownloadObservation(): {
  observedDownloads: Map<number, chrome.downloads.DownloadItem>
  dispose: () => void
} {
  const observedDownloads = new Map<number, chrome.downloads.DownloadItem>()
  const onCreated = (item: chrome.downloads.DownloadItem) => {
    observedDownloads.set(item.id, item)
  }
  const onChanged = (delta: chrome.downloads.DownloadDelta) => {
    const current = observedDownloads.get(delta.id)
    if (!current) return
    const apply = (
      key: keyof chrome.downloads.DownloadItem,
      change: { current?: unknown } | undefined,
    ) => {
      if (change && Object.prototype.hasOwnProperty.call(change, 'current')) {
        (current as unknown as Record<string, unknown>)[key] = change.current
      }
    }
    apply('filename', delta.filename)
    apply('url', delta.url)
    apply('finalUrl', delta.finalUrl)
    apply('mime', delta.mime)
    apply('state', delta.state)
    apply('error', delta.error)
    apply('exists', delta.exists)
    apply('totalBytes', delta.totalBytes)
    apply('fileSize', delta.fileSize)
  }
  chrome.downloads.onCreated.addListener(onCreated)
  chrome.downloads.onChanged.addListener(onChanged)
  return {
    observedDownloads,
    dispose: () => {
      chrome.downloads.onCreated.removeListener(onCreated)
      chrome.downloads.onChanged.removeListener(onChanged)
    },
  }
}

async function resolveTrustedLocalFile(action: ExecutableAction): Promise<
  { allowed: true; file: TrustedLocalFile } | { allowed: false; reason: string }
> {
  const declaration = action.content_insertion
  if (!declaration?.opens_native_chooser || !declaration.requires_bound_file) {
    return { allowed: false, reason: 'approved_file_binding_not_required' }
  }
  const requested = String(declaration.requested_filename || '').trim()
  if (!requested || /[\\/]/.test(requested)) {
    return { allowed: false, reason: 'exact_filename_missing' }
  }
  const items = await chrome.downloads.search({ exists: true, limit: 200, orderBy: ['-startTime'] })
  const exact = items.filter((item) => (
    item.state === 'complete'
    && Boolean(item.filename)
    && leafName(item.filename).normalize('NFKC').toLocaleLowerCase() === requested.normalize('NFKC').toLocaleLowerCase()
  ))
  const unique = new Map(exact.map((item) => [String(item.filename).toLocaleLowerCase(), item]))
  if (unique.size === 0) {
    try {
      const response = await fetch(`${POLICY_BACKEND_URL}/local-files/resolve-download`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-AI-Browser-Assist-Extension': 'service-worker',
        },
        body: JSON.stringify({ filename: requested }),
      })
      if (!response.ok) {
        return { allowed: false, reason: `exact_download_not_found:${requested}` }
      }
      const resolved = await response.json() as Partial<TrustedLocalFile>
      if (
        typeof resolved.absolute_path !== 'string'
        || !resolved.absolute_path
        || leafName(resolved.absolute_path).normalize('NFKC').toLocaleLowerCase() !== requested.normalize('NFKC').toLocaleLowerCase()
        || typeof resolved.filename !== 'string'
        || resolved.filename.normalize('NFKC').toLocaleLowerCase() !== requested.normalize('NFKC').toLocaleLowerCase()
        || typeof resolved.mime_type !== 'string'
        || !Number.isFinite(resolved.size_bytes)
        || Number(resolved.size_bytes) <= 0
        || resolved.source !== 'local_downloads_broker_exact_match'
      ) {
        return { allowed: false, reason: `local_download_broker_invalid:${requested}` }
      }
      return { allowed: true, file: resolved as TrustedLocalFile }
    } catch {
      return { allowed: false, reason: `local_download_broker_unavailable:${requested}` }
    }
  }
  if (unique.size > 1) {
    return { allowed: false, reason: `ambiguous_exact_download:${requested}` }
  }
  const item = [...unique.values()][0]
  const size = Number(item.fileSize || item.totalBytes || 0)
  if (!Number.isFinite(size) || size <= 0) {
    return { allowed: false, reason: `download_metadata_incomplete:${requested}` }
  }
  return {
    allowed: true,
    file: {
      absolute_path: item.filename,
      filename: leafName(item.filename),
      mime_type: String(item.mime || 'application/octet-stream'),
      size_bytes: size,
      source: 'chrome_downloads_exact_match',
    },
  }
}

async function reserveConsequentialSubmission(
  contract: CanonicalActionContract,
  action: ExecutableAction,
): Promise<{ allowed: true } | { allowed: false; reason: string }> {
  const declaration = action.consequential_submission
  if (!declaration) return { allowed: true }
  return submissionLedger.reserve(contract, declaration)
}

async function settleConsequentialSubmission(
  action: ExecutableAction,
  state: 'reserved' | 'dispatching' | 'delivered' | 'uncertain',
): Promise<void> {
  const id = action.consequential_submission?.submission_id
  if (!id) return
  await submissionLedger.settle(id, state)
}

type ContentInsertionReservation = {
  request_id: string
  chooser_count: number
  state: 'chooser_opened' | 'selected' | 'cancelled' | 'uncertain'
  origin: string
  destination_entity: string
  kind: string
  effect: string
  updated_at_ms: number
}

async function reserveContentChooser(
  contract: CanonicalActionContract,
  action: ExecutableAction,
): Promise<{ allowed: true } | { allowed: false; reason: string }> {
  const declaration = action.content_insertion
  if (!declaration?.opens_native_chooser) return { allowed: true }
  const stored = await chrome.storage.local.get(CONTENT_RESERVATIONS_KEY)
  const reservations = (stored[CONTENT_RESERVATIONS_KEY] || {}) as Record<string, ContentInsertionReservation>
  const existing = reservations[declaration.request_id]
  if (existing && existing.chooser_count > 0) {
    return { allowed: false, reason: 'second_chooser_blocked' }
  }
  reservations[declaration.request_id] = {
    request_id: declaration.request_id,
    chooser_count: 1,
    state: 'chooser_opened',
    origin: contract.origin.origin,
    destination_entity: declaration.destination_entity,
    kind: declaration.kind,
    effect: declaration.expected_effect,
    updated_at_ms: Date.now(),
  }
  await chrome.storage.local.set({ [CONTENT_RESERVATIONS_KEY]: reservations })
  return { allowed: true }
}

async function settleContentChooser(
  action: ExecutableAction,
  state: ContentInsertionReservation['state'],
): Promise<void> {
  const requestId = action.content_insertion?.request_id
  if (!requestId) return
  const stored = await chrome.storage.local.get(CONTENT_RESERVATIONS_KEY)
  const reservations = (stored[CONTENT_RESERVATIONS_KEY] || {}) as Record<string, ContentInsertionReservation>
  const existing = reservations[requestId]
  if (!existing) return
  reservations[requestId] = { ...existing, state, updated_at_ms: Date.now() }
  await chrome.storage.local.set({ [CONTENT_RESERVATIONS_KEY]: reservations })
}

type TabControlMetadata = {
  opened_tab_id?: number | null
  previous_tab_id?: number | null
  active_tab_id?: number | null
  closed_tab_id?: number | null
  tab_switch_verified?: boolean
}

let tabWorkspace: MultiTabWorkspace = createMultiTabWorkspace()
const cdpController = new CdpController()

async function getTargetTab(): Promise<chrome.tabs.Tab | undefined> {
  try {
    const tabs = await chrome.tabs.query({ active: true })
    if (tabs && tabs.length > 0) {
      const targetTab = tabs.find(t => isSelectableBrowserTarget(t.url))
      if (targetTab) return targetTab
    }
  } catch (e) {
    console.error('Error querying active tabs:', e)
  }
  try {
    const tabs = await chrome.tabs.query({})
    const targetTab = tabs
      .filter(t => {
        const url = t.url ?? ''
        return isSelectableBrowserTarget(url)
      })
      .sort((a, b) => (b.lastAccessed ?? 0) - (a.lastAccessed ?? 0))[0]
    if (targetTab) return targetTab
  } catch (e) {
    console.error('Error querying fallback target tab:', e)
  }
  try {
    const [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true })
    return isSelectableBrowserTarget(currentTab?.url) ? currentTab : undefined
  } catch (e) {
    console.error('Error querying current window active tab:', e)
  }
  return undefined
}


// On install, configure the side panel to open when the user clicks the toolbar icon.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch(console.error)
})

chrome.tabs.onCreated.addListener((tab) => {
  tabWorkspace = registerTab(tabWorkspace, tabSnapshotFromChromeTab(tab))
})

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  tabWorkspace = registerTab(tabWorkspace, tabSnapshotFromChromeTab(tab))
  tabWorkspace = updateTab(tabWorkspace, tabId, {
    url: changeInfo.url ?? tab.url ?? '',
    title: changeInfo.title ?? tab.title ?? '',
    is_active: tab.active,
    visited: Boolean(tab.url || changeInfo.url),
  })
})

chrome.tabs.onActivated.addListener((activeInfo) => {
  tabWorkspace = activateTab(tabWorkspace, activeInfo.tabId)
  chrome.tabs.get(activeInfo.tabId)
    .then((tab) => {
      tabWorkspace = registerTab(tabWorkspace, { ...tabSnapshotFromChromeTab(tab), active: true })
      tabWorkspace = activateTab(tabWorkspace, activeInfo.tabId)
    })
    .catch(() => {})
})

chrome.tabs.onRemoved.addListener((tabId) => {
  tabWorkspace = removeClosedTab(tabWorkspace, tabId)
})

/**
 * Message router. Runs async work in a separate function so we can use
 * async/await cleanly while returning `true` from the listener to keep
 * the message channel open.
 */
chrome.runtime.onMessage.addListener((message: unknown, sender, sendResponse) => {
  const validationError = validateServiceWorkerMessage(message, {
    id: sender.id,
    url: sender.url,
    hasTab: Boolean(sender.tab),
  }, chrome.runtime.id)
  if (validationError) {
    sendResponse({ error: validationError })
    return false
  }
  const validMessage = message as Record<string, any>
  if (validMessage.type === 'EXTRACT_CONTEXT') {
    handleExtractContext(sendResponse, typeof validMessage.tab_id === 'number' ? validMessage.tab_id : undefined)
    return true
  }
  if (validMessage.type === 'EXECUTE_ACTION') {
    handleExecuteAction(validMessage.contract, validMessage.policy_context, sendResponse)
    return true
  }
  if (validMessage.type === 'START_VOICE_CAPTURE') {
    handleStartVoiceCapture(validMessage.language ?? '', sendResponse)
    return true
  }
  if (validMessage.type === 'WAIT_FOR_TAB_LOAD') {
    handleWaitForTabLoad(sendResponse)
    return true
  }
  if (validMessage.type === 'WAIT_FOR_DOM_SETTLE') {
    handleWaitForDomSettle(sendResponse)
    return true
  }
  if (validMessage.type === 'GET_TAB_WORKSPACE') {
    handleGetTabWorkspace(sendResponse)
    return true
  }
  if (validMessage.type === 'GET_RUNTIME_IDENTITY') {
    sendResponse({
      runtime: {
        app_version: APP_VERSION,
        build_commit: BUILD_COMMIT,
        build_id: BUILD_ID,
      },
    })
    return false
  }
})

// ── Context extraction ────────────────────────────────────────────────────────

async function handleExtractContext(sendResponse: (response: unknown) => void, tabId?: number) {
  try {
    const requestedTab = typeof tabId === 'number'
      ? await chrome.tabs.get(tabId).catch(() => undefined)
      : undefined
    const tab = requestedTab ?? await getTargetTab()
    const context = await extractContextWithRetry(tab?.id)
    if (!context) {
      sendResponse({ error: 'Extraction returned empty. Try reloading the page.' })
      return
    }
    sendResponse({
      context: {
        ...context,
        tab_id: tab?.id,
        window_id: tab?.windowId,
      },
    })
  } catch (err) {
    const msg = String(err)
    if (msg.includes('Cannot access') || msg.includes('chrome://') || msg.includes('chrome-extension://') || msg.includes('not allowed')) {
      sendResponse({ error: 'This page cannot be accessed by the extension. Navigate to a regular webpage (http/https).' })
    } else {
      sendResponse({ error: `Extraction failed: ${msg}` })
    }
  }
}

function isTransientExtractionError(message: string): boolean {
  return (
    message.includes('Frame with ID') ||
    message.includes('frame was removed') ||
    message.includes('No frame with id') ||
    message.includes('The tab was closed') ||
    message.includes('Receiving end does not exist') ||
    message.includes('Extension context invalidated')
  )
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitForActiveTabComplete(tabId: number): Promise<void> {
  const tab = await chrome.tabs.get(tabId).catch(() => null)
  if (!tab || tab.status === 'complete') return

  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener)
      resolve()
    }, 5_000)

    function listener(updatedTabId: number, changeInfo: chrome.tabs.TabChangeInfo) {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        clearTimeout(timer)
        chrome.tabs.onUpdated.removeListener(listener)
        resolve()
      }
    }

    chrome.tabs.onUpdated.addListener(listener)
  })
}

async function waitForTabNavigationSettle(
  tabId: number,
  previousUrl: string,
  timeoutMs = 12_000,
): Promise<chrome.tabs.Tab | null> {
  const deadline = Date.now() + timeoutMs
  let lastSignature = ''
  let stableSamples = 0
  let latest: chrome.tabs.Tab | null = null
  while (Date.now() < deadline) {
    latest = await chrome.tabs.get(tabId).catch(() => null)
    const currentUrl = latest?.url || ''
    const signature = `${currentUrl}|${latest?.status || ''}`
    if (currentUrl && currentUrl !== previousUrl && latest?.status === 'complete') {
      stableSamples = signature === lastSignature ? stableSamples + 1 : 1
      if (stableSamples >= 6) return latest
    } else {
      stableSamples = 0
    }
    lastSignature = signature
    await sleep(250)
  }
  return latest
}

function isRestrictedUrl(url: string | undefined): boolean {
  if (!url) return true
  return (
    url.startsWith('chrome://') ||
    url.startsWith('chrome-extension://') ||
    url.startsWith('about:') ||
    url.startsWith('edge://') ||
    url.startsWith('file:///')
  )
}

function getMockContext(url: string | undefined, title: string | undefined) {
  return {
    url: url || 'about:blank',
    title: title || 'New Tab',
    metadata: {},
    interactive_elements: [],
    content_blocks: [],
    headings: [],
    selected_text: '',
    visible_text: 'This is a blank browser tab or restricted browser settings page. No webpage is loaded yet. Use the "navigate" action to open a website.',
    images: []
  }
}

function logExtractionDiagnostics(boundary: string, context: any) {
  const semanticKeys = Object.keys(context || {}).filter((key) => /semantic|entity|browser_intelligence|page_model/i.test(key))
  const interactive = Array.isArray(context?.interactive_elements) ? context.interactive_elements : []
  const blocks = Array.isArray(context?.content_blocks) ? context.content_blocks : []
  const semanticInteractive = interactive.filter((item: any) => item?.semantic_kind || item?.selector_id)
  const hrefBlocks = blocks.filter((item: any) => item?.href)
  console.info(`[V4.5.1 live-path] ${boundary}`, {
    url: context?.url,
    title: context?.title,
    topLevelKeys: Object.keys(context || {}),
    semanticKeys,
    interactiveCount: interactive.length,
    contentBlockCount: blocks.length,
    semanticInteractiveCount: semanticInteractive.length,
    hrefContentBlockCount: hrefBlocks.length,
    firstInteractive: interactive.slice(0, 6).map((item: any) => ({
      text: item?.text,
      href: item?.href,
      semantic_kind: item?.semantic_kind,
      selector_id: item?.selector_id,
    })),
    firstContentBlocks: blocks.slice(0, 6).map((item: any) => ({
      text: String(item?.text || '').slice(0, 120),
      href: item?.href,
      selector: item?.selector,
    })),
  })
}

async function extractContextWithRetry(tabId?: number) {
  let lastError = ''

  const tab = typeof tabId === 'number'
    ? await chrome.tabs.get(tabId).catch(() => undefined)
    : await getTargetTab()
  if (!tab?.id) {
    throw new Error('No active tab found. Click the extension icon while a webpage is open.')
  }

  if (isRestrictedUrl(tab.url)) {
    return getMockContext(tab.url, tab.title)
  }

  for (let attempt = 0; attempt < 4; attempt++) {
    try {
      await waitForActiveTabComplete(tab.id)
      if (attempt > 0) await sleep(600 * attempt)

      let results
      try {
        const [v2Results, v1Results] = await Promise.all([
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: extractPageContextV2,
          }),
          chrome.scripting.executeScript({
            target: { tabId: tab.id, allFrames: true },
            func: extractPageContext,
          }),
        ])
        const v2Context = v2Results[0]?.result
        const topFrameResult = v1Results.find((entry) => entry.frameId === 0) || v1Results[0]
        const v1Context = topFrameResult?.result
        if (v2Context && v1Context) {
          const aliases = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: resolveObservedSelectorAliases,
            args: [[...v1Context.interactive_elements, ...v2Context.interactive_elements].map(item => item.selector)],
          })
          logExtractionDiagnostics('EXTRACT_CONTEXT_V1', v1Context)
          logExtractionDiagnostics('EXTRACT_CONTEXT_V2', v2Context)
          const topOrigin = (() => {
            try { return new URL(v1Context.url).origin } catch { return '' }
          })()
          const childFrameResults = v1Results.filter((entry) => entry.frameId !== 0 && entry.result)
          const childContexts = childFrameResults
            .filter((entry) => {
              try { return new URL(entry.result!.url).origin === topOrigin } catch { return false }
            })
          const crossOriginChildFrameCount = childFrameResults.length - childContexts.length
          const childInteractive = childContexts.flatMap((entry) =>
            (entry.result!.interactive_elements || []).map((item: any) => ({
              ...item,
              frame_id: `chrome-frame:${entry.frameId}`,
            })),
          )
          const mergedTopInteractive = mergeInteractiveElementLists(
            v1Context.interactive_elements,
            v2Context.interactive_elements,
            150,
            aliases[0]?.result || {},
          ).map((item) => ({ ...item, frame_id: 'top' }))
          const uniqueInteractive = new Map<string, any>()
          for (const item of [...mergedTopInteractive, ...childInteractive]) {
            const key = `${item.frame_id || 'top'}|${item.selector || ''}`
            if (!uniqueInteractive.has(key)) uniqueInteractive.set(key, item)
          }
          const childVisibleText = childContexts
            .map((entry) => String(entry.result!.visible_text || '').trim())
            .filter(Boolean)
            .join('\n')
          const merged = {
            ...v1Context,
            ...v2Context,
            frame_id: 'top',
            metadata: {
              ...v1Context.metadata,
              same_origin_child_frame_count: String(childContexts.length),
              cross_origin_child_frame_count: String(Math.max(0, crossOriginChildFrameCount)),
            },
            interactive_elements: [...uniqueInteractive.values()].slice(0, 150),
            content_blocks: v1Context.content_blocks,
            images: v1Context.images,
            visible_text: [v1Context.visible_text || v2Context.visible_text, childVisibleText]
              .filter(Boolean)
              .join('\n')
              .slice(0, 2000),
          }
          logExtractionDiagnostics('EXTRACT_CONTEXT_MERGED_RETURNED_TO_SIDEPANEL', merged)
          return merged
        }
        results = v2Results
      } catch (e2) {
        console.warn('V2 merged extraction failed, falling back to V1:', e2)
        results = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: extractPageContext,
        })
      }
      const context = results[0]?.result
      if (context) {
        logExtractionDiagnostics('EXTRACT_CONTEXT_RETURNED_TO_SIDEPANEL', context)
        return context
      }
    } catch (err) {
      lastError = String(err)
      if (lastError.includes('Cannot access') || lastError.includes('not allowed')) {
        return getMockContext(tab.url, tab.title)
      }
      if (!isTransientExtractionError(lastError)) throw err
    }
  }

  throw new Error(lastError || 'Extraction failed while the page was changing.')
}

// ── Action execution ──────────────────────────────────────────────────────────

type CanonicalExecutorStrategy =
  | 'navigation'
  | 'trusted_cdp'
  | 'tab_control'
  | 'wait'
  | 'rich_text'
  | 'wave2'
  | 'wave3'
  | 'unsupported'

const TRUSTED_CDP_ACTIONS = new Set([
  'click',
  'fill',
  'select_option',
  'choose_date',
  'hover',
  'scroll',
  'keyboard_shortcut',
  'navigate_next_page',
  'visual_region',
  'canvas_action',
  'svg_action',
])

const RICH_TEXT_ACTIONS = new Set(['rich_text', 'insert_rich_text', 'edit_rich_text'])

function canonicalExecutorStrategy(actionType: string): CanonicalExecutorStrategy {
  if (actionType === 'navigate') return 'navigation'
  if (TRUSTED_CDP_ACTIONS.has(actionType)) return 'trusted_cdp'
  if (['open_new_tab', 'switch_tab', 'focus_existing_tab', 'close_tab'].includes(actionType)) return 'tab_control'
  if (actionType === 'wait') return 'wait'
  if (RICH_TEXT_ACTIONS.has(actionType)) return 'rich_text'
  if (isWave2CoreAction(actionType)) return 'wave2'
  if (isWave3VisualAction(actionType)) return 'wave3'
  return 'unsupported'
}

async function handleExecuteAction(
  contract: CanonicalActionContract,
  policyContext: PolicyExecutionContext,
  sendResponse: (response: unknown) => void,
) {
  try {
    const action = contract.action
    const executorStrategy = canonicalExecutorStrategy(action.action_type)
    if (executorStrategy === 'unsupported') {
      sendResponse({ error: `Browser action rejected: no canonical executor is registered for ${action.action_type}.` })
      return
    }
    const observedTabId = contract.browser_binding.tab_id
    if (!Number.isInteger(observedTabId)) {
      sendResponse({ error: 'Browser action rejected: no observed tab binding was provided.' })
      return
    }
    const tab = await chrome.tabs.get(observedTabId).catch(() => undefined)
    const tabUrl = tab?.url ?? ''
    const bootstrapNavigation = ['navigate', 'open_new_tab'].includes(action.action_type)
      && ['chrome://newtab/', 'about:blank'].includes(tabUrl)
      && contract.origin.observed_url === tabUrl
      && Boolean(contract.origin.target_url)
    if (!tab?.id || (!isGroundedBrowserTarget(tabUrl) && !bootstrapNavigation)) {
      sendResponse({ error: 'Browser action rejected: the observed tab is unavailable or is not an http/https page.' })
      return
    }
    if (
      tabUrl !== contract.origin.observed_url ||
      (!bootstrapNavigation && !['navigate', 'open_new_tab'].includes(action.action_type) && new URL(tabUrl).origin !== contract.origin.origin) ||
      (contract.browser_binding.window_id !== null && tab.windowId !== contract.browser_binding.window_id)
    ) {
      sendResponse({ error: 'Browser action rejected: canonical origin, URL, tab, or window identity changed before dispatch.' })
      return
    }
    const startedAt = performance.now()
    const beforeState = await captureActionVerificationState(tab.id, action, tab)
    const policyTab = await chrome.tabs.get(tab.id).catch(() => undefined)
    if (!policyTab?.url || policyTab.url !== tabUrl) {
      sendResponse({ error: 'Browser action rejected: the observed page changed before policy evaluation.' })
      return
    }
    const policyDecision = await enforceLivePolicy(POLICY_BACKEND_URL, contract, contract.origin.target_url || policyTab.url, policyContext)
    if (!policyDecision.allowed) {
      sendResponse({
        error: `Browser action rejected by policy: ${policyDecision.decision_reason}`,
        policy_decision: policyDecision,
      })
      return
    }
    const executionTab = await chrome.tabs.get(tab.id).catch(() => undefined)
    if (!executionTab?.url || executionTab.url !== policyTab.url) {
      sendResponse({ error: 'Browser action rejected: the page changed after policy evaluation.' })
      return
    }

    // Intercept navigate action and handle directly from background
    if (action.action_type === 'navigate') {
      const url = action.value
      if (!url) {
        sendResponse({ error: 'No URL provided for navigate.' })
        return
      }
      if (!url.startsWith('https://') && !url.startsWith('http://')) {
        sendResponse({ error: `Unsafe URL rejected (must be http/https): ${url}` })
        return
      }
      await chrome.tabs.update(tab.id, { url })
      await waitForTabNavigationSettle(tab.id, tabUrl)
       const verifiedResult = await createVerifiedExecutionResult(tab.id, contract, beforeState, {
        success: true,
        message: `Navigating to: ${url}`,
        action_id: action.action_id,
      }, startedAt)
      sendResponse({ result: attachCanonicalContractEvidence(verifiedResult, contract, 'service_worker>policy>chrome.tabs.update') })
      return
    }

    if (action.action_type === 'click') {
      let submissionBefore: SubmissionPageEvidence | null = null
      if (action.consequential_submission) {
        const inspection = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: inspectConsequentialSubmission,
          args: [action.consequential_submission],
        }).catch(() => null)
        submissionBefore = inspection?.[0]?.result ?? null
        if (
          !submissionBefore?.destination_observed
          || !submissionBefore.content_observed
          || (action.consequential_submission.preview_required && !submissionBefore.preview_observed)
        ) {
          sendResponse({ error: 'Consequential action rejected: its exact destination, exact content or change, and review state were not all observable immediately before dispatch.' })
          return
        }
        const reservation = await reserveConsequentialSubmission(contract, action)
        if (!reservation.allowed) {
          sendResponse({
            result: {
              success: false,
              message: `Submission was not repeated: ${reservation.reason}.`,
              action_id: action.action_id,
              submission_id: action.consequential_submission.submission_id,
              submission_operation: action.consequential_submission.operation,
              submission_attempted: false,
              submission_duplicate_prevented: true,
              delivery_verified: reservation.reason === 'already_delivered',
              dispatch_uncertain: reservation.reason !== 'already_delivered',
            },
          })
          return
        }
        await settleConsequentialSubmission(action, 'dispatching')
      }
      let trustedLocalFile: TrustedLocalFile | undefined
      if (action.content_insertion?.opens_native_chooser) {
        const trustedFile = await resolveTrustedLocalFile(action)
        if (!trustedFile.allowed) {
          sendResponse({
            error: `Content insertion needs one exact, locally approved Downloads file (${trustedFile.reason}). No chooser was opened and no file was selected.`,
          })
          return
        }
        trustedLocalFile = trustedFile.file
      }
      const chooserReservation = await reserveContentChooser(contract, action)
      if (!chooserReservation.allowed) {
        sendResponse({ error: `Content insertion rejected: ${chooserReservation.reason}` })
        return
      }
      if (action.content_insertion?.opens_native_chooser) {
        const prepared = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: prepareContentInsertionSelectionInspection,
          args: [action.content_insertion],
        }).catch(() => null)
        if (prepared?.[0]?.result !== true) {
          await settleContentChooser(action, 'uncertain')
          sendResponse({ error: 'Content insertion rejected because exact selection evidence could not be prepared.' })
          return
        }
      }
      const downloadObservation = contract.expected_effect.kind === 'download_complete'
        ? armExpectedDownloadObservation()
        : null
      const cdpExecution = await cdpController.execute(
        tab.id,
        action,
        trustedLocalFile,
      )
      let executionWithContentEvidence: BasicExecutionResult = cdpExecution
      if (downloadObservation) {
        try {
          if (cdpExecution.success && cdpExecution.download_completed === true) {
            executionWithContentEvidence = cdpExecution
          } else if (cdpExecution.success) {
            const download = await waitForExpectedDownload(
              Date.now() - Math.max(0, performance.now() - startedAt),
              String(action.grounding?.expected_download_filename || ''),
              String(action.grounding?.expected_download_url || ''),
              downloadObservation.observedDownloads,
            )
            executionWithContentEvidence = {
              ...cdpExecution,
              ...download,
              action_id: action.action_id,
              success: cdpExecution.success && download.success,
            }
          }
        } finally {
          downloadObservation.dispose()
        }
      }
      if (action.consequential_submission && submissionBefore) {
        let after: SubmissionPageEvidence | null = null
        let delivered = false
        if (cdpExecution.success) {
          for (let attempt = 0; attempt < 20; attempt += 1) {
            if (attempt > 0) await sleep(250)
            const inspection = await chrome.scripting.executeScript({
              target: { tabId: tab.id },
              func: inspectConsequentialSubmission,
              args: [action.consequential_submission],
            }).catch(() => null)
            after = inspection?.[0]?.result ?? null
            if (after && verifyConsequentialDelivery(submissionBefore, after)) {
              delivered = true
              break
            }
          }
        }
        await settleConsequentialSubmission(action, delivered ? 'delivered' : 'uncertain')
        executionWithContentEvidence = {
          ...cdpExecution,
          success: cdpExecution.success && delivered,
          message: delivered
            ? 'The consequential action was dispatched once and its exact destination/content effect was verified.'
            : 'Dispatch may have occurred, but delivery could not be verified. It will not be retried automatically.',
          submission_id: action.consequential_submission.submission_id,
          submission_operation: action.consequential_submission.operation,
          submission_attempted: true,
          submission_duplicate_prevented: false,
          delivery_verified: delivered,
          delivered_content_identity: delivered ? action.consequential_submission.content_identity : null,
          delivered_destination_entity: delivered ? action.consequential_submission.destination_entity : null,
          dispatch_uncertain: !delivered,
        }
      }
      if (action.content_insertion?.opens_native_chooser) {
        if (!cdpExecution.success) {
          await settleContentChooser(action, 'uncertain')
        } else {
          const inspection = await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: inspectContentInsertionSelection,
            args: [action.content_insertion, 30_000],
          }).catch(() => null)
          const evidence = inspection?.[0]?.result
          if (evidence?.success) {
            const exactOrigin = evidence.destination_origin === contract.origin.origin
            await settleContentChooser(action, exactOrigin ? 'selected' : 'uncertain')
            executionWithContentEvidence = {
              ...cdpExecution,
              ...evidence,
              success: cdpExecution.success && exactOrigin,
              message: exactOrigin
                ? evidence.message
                : 'Content selection origin changed before verification.',
            }
          } else {
            await settleContentChooser(action, evidence?.chooser_cancelled ? 'cancelled' : 'uncertain')
            executionWithContentEvidence = {
              ...cdpExecution,
              ...(evidence || {}),
              success: false,
              message: evidence?.message || 'Content selection could not be verified.',
            }
          }
        }
      }
       const verifiedResult = await createVerifiedExecutionResult(tab.id, contract, beforeState, executionWithContentEvidence, startedAt)
      const exactPostcondition = requiresExactOpenedTargetVerification(contract)
        ? await verifyExactPostconditionWithRetry(tab.id, contract)
        : null
      const postconditionResult = applyExactPostcondition(verifiedResult, exactPostcondition)
      const completed = attachCanonicalContractEvidence(
        postconditionResult,
        contract,
        'service_worker>policy>canonical_cdp_click',
      )
      await persistAdapterTrace(action, completed)
      sendResponse({ result: completed })
      return
    }

    if (action.action_type === 'keyboard_shortcut') {
      const cdpExecution = await cdpController.execute(tab.id, action)
      const verifiedResult = await createVerifiedExecutionResult(tab.id, contract, beforeState, cdpExecution, startedAt)
      const exactPostcondition = requiresExactOpenedTargetVerification(contract)
        ? await verifyExactPostconditionWithRetry(tab.id, contract)
        : null
      const postconditionResult = applyExactPostcondition(verifiedResult, exactPostcondition)
      const completed = attachCanonicalContractEvidence(
        postconditionResult,
        contract,
        'service_worker>policy>canonical_cdp_keyboard',
      )
      await persistAdapterTrace(action, completed)
      sendResponse({ result: completed })
      return
    }

    if (executorStrategy === 'trusted_cdp') {
      const cdpExecution = await cdpController.execute(tab.id, action)
      const verifiedResult = await createVerifiedExecutionResult(tab.id, contract, beforeState, cdpExecution, startedAt)
      const completed = attachCanonicalContractEvidence(
        verifiedResult,
        contract,
        `service_worker>policy>canonical_${executorStrategy}`,
      )
      await persistAdapterTrace(action, completed)
      sendResponse({ result: completed })
      return
    }

    const result = await executeBrowserActionOnce(tab.id, action, executorStrategy)
    if (!result) { sendResponse({ error: 'Executor returned empty result.' }); return }
    const verifiedResult = await createVerifiedExecutionResult(tab.id, contract, beforeState, {
      ...result,
    }, startedAt)
    const completed = attachCanonicalContractEvidence(
      verifiedResult,
      contract,
      `service_worker>policy>canonical_${executorStrategy}`,
    )
    await persistAdapterTrace(action, completed)
    sendResponse({ result: completed })
  } catch (err) {
    const msg = String(err)
    if (msg.includes('Cannot access') || msg.includes('not allowed')) {
      sendResponse({ error: 'Cannot execute on this page. Navigate to a regular webpage.' })
    } else {
      sendResponse({ error: `Execution failed: ${msg}` })
    }
  }
}

async function verifyExactPostconditionWithRetry(
  tabId: number,
  contract: CanonicalActionContract,
): Promise<ExactTargetVerificationResult | null> {
  const expectedName = contract.target_identity.exact_name?.trim()
  if (!expectedName) return null
  let latest: ExactTargetVerificationResult | null = null
  for (let attempt = 0; attempt < 10; attempt += 1) {
    if (attempt > 0) await sleep(300)
    const result = await chrome.scripting.executeScript({
      target: { tabId },
      func: verifyExactOpenedTarget,
      args: [{
        expected_name: expectedName,
        semantic_kind: contract.target_identity.semantic_kind,
        observed_origin: contract.origin.origin,
      }],
    }).catch(() => null)
    latest = result?.[0]?.result ?? null
    if (latest?.verified || latest?.required === false) return latest
  }
  return latest
}

function applyExactPostcondition(
  result: VerifiedExecutionResult,
  exact: ExactTargetVerificationResult | null,
): VerifiedExecutionResult {
  if (!exact || exact.required === false) return result
  const verification = result.verification
  return {
    ...result,
    success: result.success && exact.verified,
    message: exact.verified
      ? `${result.message} Exact ${exact.target_kind} identity verified: ${exact.observed_name}.`
      : `${result.message} Exact ${exact.target_kind} identity was not verified; expected "${exact.expected_name}" but observed "${exact.observed_name || 'none'}".`,
    verification: verification ? {
      ...verification,
      verified: result.success && exact.verified,
      reason: result.success && exact.verified ? 'verified' : (result.success ? 'no_effect' : 'execution_failed'),
      signals: {
        ...verification.signals,
        exact_identity_required: true,
        exact_identity_verified: exact.verified,
        exact_target_kind: exact.target_kind,
        exact_expected_name: exact.expected_name,
        exact_observed_name: exact.observed_name,
        exact_evidence_selector: exact.evidence_selector,
        exact_verification_reason: exact.reason,
      },
    } : verification,
    adapter_trace: {
      ...(result.adapter_trace || {}),
      exact_identity_required: true,
      exact_identity_verified: exact.verified,
      exact_target_kind: exact.target_kind,
      exact_expected_name: exact.expected_name,
      exact_observed_name: exact.observed_name,
      exact_verification_reason: exact.reason,
    },
  }
}

async function persistAdapterTrace(action: ExecutableAction, result: VerifiedExecutionResult): Promise<void> {
  const stored: Record<string, any> = await chrome.storage.local.get('phase2_adapter_traces').catch(() => ({}))
  const existing = Array.isArray(stored.phase2_adapter_traces) ? stored.phase2_adapter_traces : []
  const trace = {
    timestamp: new Date().toISOString(),
    action_id: action.action_id,
    action_type: action.action_type,
    execution_adapter: result.execution_adapter ?? 'dom',
    verified: result.verification?.verified ?? false,
    reason: result.verification?.reason ?? null,
    ...(result.adapter_trace || {}),
  }
  await chrome.storage.local.set({ phase2_adapter_traces: [...existing.slice(-199), trace] }).catch(() => undefined)
}

async function handleGetTabWorkspace(sendResponse: (response: unknown) => void) {
  try {
    await syncTabWorkspaceSnapshot()
    sendResponse({ tab_workspace: tabWorkspace })
  } catch (err) {
    sendResponse({ error: `Tab workspace unavailable: ${String(err)}` })
  }
}

async function syncTabWorkspaceSnapshot() {
  const tabs = await chrome.tabs.query({})
  let next = tabWorkspace
  for (const tab of tabs) {
    next = registerTab(next, tabSnapshotFromChromeTab(tab))
    if (tab.active && typeof tab.id === 'number') {
      next = activateTab(next, tab.id)
    }
  }
  tabWorkspace = next
}

async function executeBrowserActionOnce(
  tabId: number,
  action: ExecutableAction,
  strategy: CanonicalExecutorStrategy,
): Promise<BasicExecutionResult | null> {
  if (strategy === 'tab_control') return await executeTabControlAction(action)
  if (strategy === 'wait') {
    return { success: true, message: 'Canonical no-mutation wait completed.', action_id: action.action_id }
  }

  const leaf = strategy === 'rich_text'
    ? executeRichTextAction
    : strategy === 'wave2'
      ? executeWave2CoreAction
      : strategy === 'wave3'
        ? executeWave3VisualAction
        : null
  if (!leaf) {
    return {
      success: false,
      message: `No canonical leaf strategy was selected for ${action.action_type}.`,
      action_id: action.action_id,
    }
  }

  const attempt = await chrome.scripting.executeScript({
    target: { tabId },
    func: leaf,
    args: [action],
  }).catch(() => null)
  return attempt?.[0]?.result ?? {
    success: false,
    message: `Canonical ${strategy} strategy did not accept ${action.action_type}.`,
    action_id: action.action_id,
  }
}

async function executeTabControlAction(action: ExecutableAction): Promise<(BasicExecutionResult & TabControlMetadata) | null> {
  if (!isTabControlAction(action)) return null
  await syncTabWorkspaceSnapshot()
  const previousTab = await getTargetTab()
  const previousTabId = previousTab?.id ?? null

  if (action.action_type === 'open_new_tab') {
    const url = normalizeOpenTabUrl(action.value)
    if (!url) {
      return { success: false, message: 'No safe http/https URL provided for new tab.', action_id: action.action_id }
    }
    const timeline: Record<string, number | string | boolean | null> = {
      requested_url: url,
      tab_create_started_ms: Date.now(),
    }
    const opened = await chrome.tabs.create({ url, active: true })
    timeline.tab_created_ms = Date.now()
    timeline.opened_tab_id = opened.id ?? null
    timeline.opened_window_id = opened.windowId ?? null
    let loaded: chrome.tabs.Tab = opened
    if (typeof opened.id === 'number') {
      timeline.navigation_wait_started_ms = Date.now()
      loaded = await waitForTabNavigationSettle(opened.id, 'about:blank') || opened
      timeline.navigation_complete_ms = Date.now()
    }
    tabWorkspace = registerTab(tabWorkspace, tabSnapshotFromChromeTab(opened))
    if (typeof loaded.id === 'number') {
      tabWorkspace = registerTab(tabWorkspace, tabSnapshotFromChromeTab(loaded))
      tabWorkspace = activateTab(tabWorkspace, loaded.id)
    }
    let pageContext: unknown = undefined
    if (typeof loaded.id === 'number') {
      timeline.capture_started_ms = Date.now()
      pageContext = await extractContextWithRetry(loaded.id).catch((err) => {
        timeline.capture_error = String(err)
        return undefined
      })
      timeline.capture_completed_ms = Date.now()
    }
    return {
      success: true,
      message: `Opened new tab: ${url}`,
      action_id: action.action_id,
      page_context: pageContext,
      browser_timeline: timeline,
      opened_tab_id: loaded.id ?? opened.id ?? null,
      previous_tab_id: previousTabId,
      active_tab_id: loaded.id ?? opened.id ?? null,
      tab_switch_verified: Boolean(loaded.active),
    }
  }

  const reference = parseTabReference(action)
  if (!reference) {
    return { success: false, message: 'No explicit tab reference provided.', action_id: action.action_id }
  }
  const entry = findTabEntryByReference(tabWorkspace, reference)
  if (!entry) {
    return { success: false, message: `No tab matched explicit ${reference.kind}: ${reference.value}`, action_id: action.action_id }
  }

  if (action.action_type === 'switch_tab' || action.action_type === 'focus_existing_tab') {
    await chrome.tabs.update(entry.tab_id, { active: true })
    if (entry.window_id !== null) await chrome.windows.update(entry.window_id, { focused: true }).catch(() => undefined)
    const active = await chrome.tabs.get(entry.tab_id).catch(() => null)
    tabWorkspace = activateTab(tabWorkspace, entry.tab_id)
    return {
      success: true,
      message: `Focused tab: ${entry.title}`,
      action_id: action.action_id,
      previous_tab_id: previousTabId,
      active_tab_id: entry.tab_id,
      tab_switch_verified: Boolean(active?.active),
    }
  }

  if (action.action_type === 'close_tab') {
    const allTabs = await chrome.tabs.query({})
    const tab = await chrome.tabs.get(entry.tab_id).catch(() => null)
    const closeDecision = canCloseTab(tab ?? { id: entry.tab_id, url: entry.url }, allTabs.length)
    if (!closeDecision.allowed) {
      return { success: false, message: `Refused to close tab: ${closeDecision.reason}`, action_id: action.action_id }
    }
    await chrome.tabs.remove(entry.tab_id)
    tabWorkspace = removeClosedTab(tabWorkspace, entry.tab_id)
    return {
      success: true,
      message: `Closed tab: ${entry.title}`,
      action_id: action.action_id,
      previous_tab_id: previousTabId,
      closed_tab_id: entry.tab_id,
      active_tab_id: previousTabId === entry.tab_id ? null : previousTabId,
    }
  }

  return null
}

async function captureActionVerificationState(
  tabId: number,
  action: ExecutableAction,
  fallbackTab?: chrome.tabs.Tab,
): Promise<ActionVerificationState> {
  try {
    const frameMatch = /^chrome-frame:(\d+)$/.exec(String(action.grounding?.frame_id || ''))
    const frameId = frameMatch ? Number(frameMatch[1]) : null
    const [state] = await chrome.scripting.executeScript({
      target: frameId === null ? { tabId } : { tabId, frameIds: [frameId] },
      func: captureVerificationState,
      args: [action],
    })
    if (state?.result) return state.result
  } catch {
    // Restricted or navigating pages still get tab-level verification metadata.
  }

  const tab = fallbackTab ?? await chrome.tabs.get(tabId).catch(() => undefined)
  return createFallbackVerificationState(tab?.url, tab?.title, action)
}

async function createVerifiedExecutionResult(
  tabId: number,
  contract: CanonicalActionContract,
  beforeState: ActionVerificationState,
  result: BasicExecutionResult,
  startedAt: number,
): Promise<VerifiedExecutionResult> {
  const action = contract.action
  const tab = await chrome.tabs.get(tabId).catch(() => undefined)
  const afterState = await captureActionVerificationState(tabId, action, tab)
  const executionDurationMs = performance.now() - startedAt
  const verification = verifyActionEffect(
    action,
    result,
    beforeState,
    afterState,
    executionDurationMs,
    contract.expected_effect,
  )
  const canonicalSuccess = result.success && verification.verified
  return {
    ...result,
    success: canonicalSuccess,
    message: canonicalSuccess
      ? result.message
      : result.success
        ? `${result.message} Canonical effect verification reported ${verification.reason}.`
        : result.message,
    verification,
    execution_duration_ms: Math.max(0, Math.round(executionDurationMs)),
  }
}

// ── Wait for tab load ─────────────────────────────────────────────────────────
// Called after a navigate action. Waits until the active tab status is
// 'complete' before responding, so re-analysis always sees the new page.

async function handleWaitForTabLoad(sendResponse: (response: unknown) => void) {
  const TIMEOUT_MS = 10_000

  const tab = await getTargetTab()
  if (!tab?.id) { sendResponse({ ready: true }); return }
  const targetTabId = tab.id

  // Already loaded.
  if (tab.status === 'complete') { sendResponse({ ready: true }); return }

  // Wait for the tab to finish loading (or time out).
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener)
      resolve()
    }, TIMEOUT_MS)

    function listener(tabId: number, changeInfo: chrome.tabs.TabChangeInfo) {
      if (tabId === targetTabId && changeInfo.status === 'complete') {
        clearTimeout(timer)
        chrome.tabs.onUpdated.removeListener(listener)
        resolve()
      }
    }
    chrome.tabs.onUpdated.addListener(listener)
  })

  sendResponse({ ready: true })
}

// ── DOM-settle wait ───────────────────────────────────────────────────────────
// Called after fill/click actions before re-analyzing.
// Injects a MutationObserver into the page that resolves once the DOM has been
// quiet for QUIET_MS milliseconds — meaning React/Vue/etc. has finished rendering.
// This is speed-adaptive: fast connections settle in <200ms, slow ones in 1-2s.

async function handleWaitForDomSettle(sendResponse: (response: unknown) => void) {
  try {
    const tab = await getTargetTab()
    if (!tab?.id) { sendResponse({ ready: true }); return }
    const timeoutPromise = new Promise((resolve) => setTimeout(resolve, 4000))
    const executePromise = chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: waitForDomSettle,
    })
    await Promise.race([executePromise, timeoutPromise])
  } catch {
    // If injection fails (e.g. page is a chrome:// URL) just continue.
  }
  sendResponse({ ready: true })
}

/**
 * Injected into the page. Returns a Promise that resolves when the DOM has
 * not mutated for QUIET_MS in a row, or after MAX_MS regardless.
 * Self-contained — no imports.
 */
function waitForDomSettle(): Promise<void> {
  return new Promise((resolve) => {
    // 1500ms quiet period — long enough for debounced remote results to arrive
    // over the network and render before we re-analyze.
    const QUIET_MS = 2000
    const MAX_MS   = 12_000 // Never wait more than 12s regardless
    const HIGH_ACTIVITY_MS = 4000
    const HIGH_ACTIVITY_MUTATIONS = 35

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let quietTimer: any
    let mutationCount = 0

    const done = () => {
      observer.disconnect()
      clearTimeout(quietTimer)
      clearTimeout(highActivityDeadline)
      clearTimeout(hardDeadline)
      resolve()
    }

    const hardDeadline = setTimeout(done, MAX_MS)
    const highActivityDeadline = setTimeout(() => {
      if (mutationCount >= HIGH_ACTIVITY_MUTATIONS) done()
    }, HIGH_ACTIVITY_MS)

    const observer = new MutationObserver(() => {
      mutationCount += 1
      // Each mutation resets the quiet timer.
      clearTimeout(quietTimer)
      quietTimer = setTimeout(done, QUIET_MS)
    })

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      characterData: true,
    })

    // If the DOM is already quiet, resolve after one quiet period.
    quietTimer = setTimeout(done, QUIET_MS)
  })
}

// ── Voice capture ─────────────────────────────────────────────────────────────
//
// SpeechRecognition cannot access the microphone from the chrome-extension://
// origin (Chrome blocks it). Instead we inject a self-contained voice capture
// function into the active tab's page (https://) using the ISOLATED world so
// it has access to both the Web Speech API AND chrome.runtime.sendMessage.
// The transcript is sent back as a VOICE_RESULT runtime message which the
// side panel listens for directly.

async function handleStartVoiceCapture(language: string, sendResponse: (response: unknown) => void) {
  try {
    const tab = await getTargetTab()
    if (!tab?.id) {
      sendResponse({ error: 'No active tab. Navigate to a webpage first.' })
      return
    }
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      world: 'ISOLATED',  // Has access to chrome.runtime + Web Speech API
      func: startVoiceCapture,
      args: [language],   // Pass chosen language code into the page context
    })
    sendResponse({ started: true })
  } catch (err) {
    const msg = String(err)
    if (msg.includes('Cannot access') || msg.includes('chrome://')) {
      sendResponse({ error: 'Navigate to a regular webpage (not chrome://) to use voice input.' })
    } else {
      sendResponse({ error: `Could not start voice capture: ${msg}` })
    }
  }
}

/**
 * Runs inside the active tab's ISOLATED content-script world.
 * All code must be self-contained — no module imports available.
 * Sends { type: 'VOICE_RESULT', transcript } or { type: 'VOICE_RESULT', error }
 * back to the extension runtime (side panel receives it via onMessage).
 */
function startVoiceCapture(language: string) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
  if (!SR) {
    chrome.runtime.sendMessage({ type: 'VOICE_RESULT', error: 'not-supported' })
    return
  }

  const recognition = new SR()
  recognition.continuous = false
  recognition.interimResults = false
  // Use the chosen language, fall back to browser language, then English.
  recognition.lang = language || navigator.language || 'en-US'
  recognition.maxAlternatives = 1

  type MinimalSpeechRecognitionEvent = Event & {
    results: { [index: number]: { [index: number]: { transcript: string } } }
  }
  type MinimalSpeechRecognitionErrorEvent = Event & { error: string }

  recognition.onresult = (event: MinimalSpeechRecognitionEvent) => {
    const transcript = event.results[0][0].transcript.trim()
    if (transcript) chrome.runtime.sendMessage({ type: 'VOICE_RESULT', transcript })
  }

  recognition.onerror = (event: MinimalSpeechRecognitionErrorEvent) => {
    chrome.runtime.sendMessage({ type: 'VOICE_RESULT', error: event.error })
  }

  recognition.start()
}
