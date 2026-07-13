import { extractPageContext } from '../content/extractor'
import { executeAction } from '../content/executor'
import { extractPageContextV2 } from '../content/extractor_v2'
import { executeActionV2 } from '../content/executor_v2'
import {
  captureVerificationState,
  createFallbackVerificationState,
  verifyActionEffect,
  type ActionVerificationState,
  type BasicExecutionResult,
  type VerifiedExecutionResult,
} from '../content/action_verification'
import {
  findRecoverySelector,
  shouldAttemptSelectorRecovery,
} from '../content/selector_recovery'
import {
  activateTab,
  createMultiTabWorkspace,
  registerTab,
  removeClosedTab,
  tabSnapshotFromChromeTab,
  updateTab,
  type MultiTabWorkspace,
} from '../workspace/multiTabWorkspace'

type ExecutableAction = {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
}

let tabWorkspace: MultiTabWorkspace = createMultiTabWorkspace()

async function getTargetTab(): Promise<chrome.tabs.Tab | undefined> {
  try {
    const tabs = await chrome.tabs.query({ active: true })
    if (tabs && tabs.length > 0) {
      const targetTab = tabs.find(t => t.url && !t.url.startsWith('chrome-extension://'))
      if (targetTab) return targetTab
    }
  } catch (e) {
    console.error('Error querying active tabs:', e)
  }
  try {
    const [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true })
    return currentTab
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
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'EXTRACT_CONTEXT') {
    handleExtractContext(sendResponse)
    return true
  }
  if (message.type === 'EXECUTE_ACTION') {
    handleExecuteAction(message.action, sendResponse)
    return true
  }
  if (message.type === 'START_VOICE_CAPTURE') {
    handleStartVoiceCapture(message.language ?? '', sendResponse)
    return true
  }
  if (message.type === 'WAIT_FOR_TAB_LOAD') {
    handleWaitForTabLoad(sendResponse)
    return true
  }
  if (message.type === 'WAIT_FOR_DOM_SETTLE') {
    handleWaitForDomSettle(sendResponse)
    return true
  }
  if (message.type === 'GET_TAB_WORKSPACE') {
    handleGetTabWorkspace(sendResponse)
    return true
  }
})

// ── Context extraction ────────────────────────────────────────────────────────

async function handleExtractContext(sendResponse: (response: unknown) => void) {
  try {
    const tab = await getTargetTab()
    const context = await extractContextWithRetry()
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

async function extractContextWithRetry() {
  let lastError = ''

  const tab = await getTargetTab()
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
            target: { tabId: tab.id },
            func: extractPageContext,
          }),
        ])
        const v2Context = v2Results[0]?.result
        const v1Context = v1Results[0]?.result
        if (v2Context && v1Context) {
          return {
            ...v1Context,
            ...v2Context,
            metadata: v1Context.metadata,
            content_blocks: v1Context.content_blocks,
            images: v1Context.images,
            visible_text: v1Context.visible_text || v2Context.visible_text,
          }
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
      if (context) return context
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

function clickOnceAndReuseTab(action: {
  action_id: string
  target_selector: string | null
  description?: string
}): { success: boolean; message: string; action_id: string } {
  const selector = action.target_selector
  if (!selector) return { success: false, message: 'No selector provided for click.', action_id: action.action_id }

  let element: Element | null = null
  try {
    element = document.querySelector(selector)
  } catch {
    return { success: false, message: `Invalid click selector: ${selector}`, action_id: action.action_id }
  }
  if (!(element instanceof HTMLElement)) {
    return { success: false, message: `Click target not found: ${selector}`, action_id: action.action_id }
  }

  const normalize = (text: string) => text.replace(/\s+/g, ' ').trim().toLowerCase()
  const labelOf = (candidate: Element) => normalize(
    candidate.getAttribute('aria-label') ||
    candidate.getAttribute('title') ||
    (candidate instanceof HTMLInputElement ? candidate.value : '') ||
    candidate.textContent ||
    '',
  )
  const isVisible = (candidate: Element) => {
    const box = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
  }
  const requestedText = normalize(action.description || '')
  const namedCandidates = Array.from(document.querySelectorAll(
    'button, a[href], [role="button"], input[type="submit"], input[type="button"]',
  ))
    .filter(isVisible)
    .map((candidate) => ({ candidate, label: labelOf(candidate) }))
    .filter(({ label }) => label.length >= 2 && requestedText.includes(label))
    .sort((a, b) => b.label.length - a.label.length)

  if (namedCandidates.length > 0) {
    const requested = namedCandidates[0]
    const targetLabel = labelOf(element)
    if (targetLabel && !targetLabel.includes(requested.label) && !requested.label.includes(targetLabel)) {
      element = requested.candidate as HTMLElement
    }
  } else {
    const targetLabel = labelOf(element)
    const isCompactLabeledControl = targetLabel.length >= 2 && targetLabel.length <= 60 && (
      element.matches('button, input[type="submit"], input[type="button"], [role="button"]')
    )
    if (requestedText && isCompactLabeledControl && !requestedText.includes(targetLabel)) {
      return {
        success: false,
        message: `Refused contradictory click: action requested "${action.description}", selector resolved to "${targetLabel}".`,
        action_id: action.action_id,
      }
    }
  }

  const clickTarget = element as HTMLElement
  const rect = clickTarget.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) {
    return { success: false, message: `Click target is not visible: ${selector}`, action_id: action.action_id }
  }

  clickTarget.scrollIntoView({ block: 'center', inline: 'center' })
  const link = clickTarget.closest('a')
  if (link?.getAttribute('target') === '_blank') link.setAttribute('target', '_self')

  const originalOpen = window.open
  window.open = ((url?: string | URL) => {
    if (url) window.location.assign(String(url))
    return window
  }) as typeof window.open
  try {
    clickTarget.click()
  } finally {
    window.setTimeout(() => { window.open = originalOpen }, 1000)
  }

  return { success: true, message: `Clicked once: ${labelOf(clickTarget) || selector}`, action_id: action.action_id }
}

async function handleExecuteAction(
  action: ExecutableAction,
  sendResponse: (response: unknown) => void,
) {
  try {
    const tab = await getTargetTab()
    if (!tab?.id) { sendResponse({ error: 'No active tab found.' }); return }
    const startedAt = performance.now()
    const beforeState = await captureActionVerificationState(tab.id, action, tab)

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
      const verifiedResult = await createVerifiedExecutionResult(tab.id, action, beforeState, {
        success: true,
        message: `Navigating to: ${url}`,
        action_id: action.action_id,
      }, startedAt)
      sendResponse({ result: verifiedResult })
      return
    }

    const result = await executeBrowserActionOnce(tab.id, action)
    if (!result) { sendResponse({ error: 'Executor returned empty result.' }); return }
    const verifiedResult = await createVerifiedExecutionResult(tab.id, action, beforeState, result, startedAt)
    const finalResult = await recoverSelectorOnceIfEligible(tab.id, action, verifiedResult)
    sendResponse({ result: finalResult })
  } catch (err) {
    const msg = String(err)
    if (msg.includes('Cannot access') || msg.includes('not allowed')) {
      sendResponse({ error: 'Cannot execute on this page. Navigate to a regular webpage.' })
    } else {
      sendResponse({ error: `Execution failed: ${msg}` })
    }
  }
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
): Promise<BasicExecutionResult | null> {
  if (action.action_type === 'click') {
    const popupSafeResult = await chrome.scripting.executeScript({
      target: { tabId },
      world: 'MAIN',
      func: clickOnceAndReuseTab,
      args: [action],
    })
    const result = popupSafeResult[0]?.result
    if (result?.success) return result
  }

  const v2OnlyActions = new Set(['select_option', 'choose_date', 'hover', 'keyboard_shortcut'])
  const primaryExecutor = v2OnlyActions.has(action.action_type) ? executeActionV2 : executeAction
  const fallbackExecutor = v2OnlyActions.has(action.action_type) ? executeAction : executeActionV2

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: primaryExecutor,
      args: [action],
    })
    return results[0]?.result ?? null
  } catch (primaryError) {
    console.warn('Primary execution failed, trying fallback executor:', primaryError)
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: fallbackExecutor,
      args: [action],
    })
    return results[0]?.result ?? null
  }
}

async function captureActionVerificationState(
  tabId: number,
  action: ExecutableAction,
  fallbackTab?: chrome.tabs.Tab,
): Promise<ActionVerificationState> {
  try {
    const [state] = await chrome.scripting.executeScript({
      target: { tabId },
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
  action: ExecutableAction,
  beforeState: ActionVerificationState,
  result: BasicExecutionResult,
  startedAt: number,
): Promise<VerifiedExecutionResult> {
  const tab = await chrome.tabs.get(tabId).catch(() => undefined)
  const afterState = await captureActionVerificationState(tabId, action, tab)
  const executionDurationMs = performance.now() - startedAt
  const verification = verifyActionEffect(action, result, beforeState, afterState, executionDurationMs)
  return {
    ...result,
    verification,
    execution_duration_ms: Math.max(0, Math.round(executionDurationMs)),
  }
}

async function recoverSelectorOnceIfEligible(
  tabId: number,
  action: ExecutableAction,
  initialResult: VerifiedExecutionResult,
): Promise<VerifiedExecutionResult> {
  if (!shouldAttemptSelectorRecovery(action, initialResult, initialResult.verification, Boolean(initialResult.recovery_attempted))) {
    return initialResult
  }

  const [choiceResult] = await chrome.scripting.executeScript({
    target: { tabId },
    func: findRecoverySelector,
    args: [action],
  })
  const choice = choiceResult?.result
  if (!choice?.selector) {
    return {
      ...initialResult,
      recovery_attempted: false,
      recovery_selector: null,
      recovery_source: null,
      recovery_verified: false,
      recovery_reason: 'no_recovery_selector',
    }
  }

  const recoveredAction: ExecutableAction = {
    ...action,
    target_selector: choice.selector,
  }
  const recoveryStartedAt = performance.now()
  const recoveryBeforeState = await captureActionVerificationState(tabId, recoveredAction)
  const recoveryExecutionResult = await executeBrowserActionOnce(tabId, recoveredAction) ?? {
    success: false,
    message: 'Recovered selector executor returned empty result.',
    action_id: action.action_id,
  }
  const recoveredResult = await createVerifiedExecutionResult(
    tabId,
    recoveredAction,
    recoveryBeforeState,
    recoveryExecutionResult,
    recoveryStartedAt,
  )

  return {
    ...recoveredResult,
    recovery_attempted: true,
    recovery_selector: choice.selector,
    recovery_source: choice.source,
    recovery_verified: recoveredResult.verification?.verified ?? false,
    recovery_reason: recoveredResult.verification?.reason ?? choice.reason,
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
    // 1500ms quiet period — long enough for debounced search results (WhatsApp,
    // Gmail, etc.) to arrive over the network and render before we re-analyze.
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
