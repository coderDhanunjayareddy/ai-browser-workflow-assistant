import { extractPageContext } from '../content/extractor'
import { executeAction } from '../content/executor'

// On install, configure the side panel to open when the user clicks the toolbar icon.
chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch(console.error)
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
})

// ── Context extraction ────────────────────────────────────────────────────────

async function handleExtractContext(sendResponse: (response: unknown) => void) {
  try {
    const context = await extractContextWithRetry()
    if (!context) {
      sendResponse({ error: 'Extraction returned empty. Try reloading the page.' })
      return
    }
    sendResponse({ context })
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

async function extractContextWithRetry() {
  let lastError = ''

  for (let attempt = 0; attempt < 4; attempt++) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id) {
      throw new Error('No active tab found. Click the extension icon while a webpage is open.')
    }

    try {
      await waitForActiveTabComplete(tab.id)
      if (attempt > 0) await sleep(600 * attempt)

      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: extractPageContext,
      })
      const context = results[0]?.result
      if (context) return context
    } catch (err) {
      lastError = String(err)
      if (!isTransientExtractionError(lastError)) throw err
    }
  }

  throw new Error(lastError || 'Extraction failed while the page was changing.')
}

// ── Action execution ──────────────────────────────────────────────────────────

async function handleExecuteAction(
  action: { action_id: string; action_type: string; target_selector: string | null; value: string | null; description?: string },
  sendResponse: (response: unknown) => void,
) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id) { sendResponse({ error: 'No active tab found.' }); return }
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: executeAction,
      args: [action],
    })
    const result = results[0]?.result
    if (!result) { sendResponse({ error: 'Executor returned empty result.' }); return }
    sendResponse({ result })
  } catch (err) {
    const msg = String(err)
    if (msg.includes('Cannot access') || msg.includes('not allowed')) {
      sendResponse({ error: 'Cannot execute on this page. Navigate to a regular webpage.' })
    } else {
      sendResponse({ error: `Execution failed: ${msg}` })
    }
  }
}

// ── Wait for tab load ─────────────────────────────────────────────────────────
// Called after a navigate action. Waits until the active tab status is
// 'complete' before responding, so re-analysis always sees the new page.

async function handleWaitForTabLoad(sendResponse: (response: unknown) => void) {
  const TIMEOUT_MS = 10_000

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab?.id) { sendResponse({ ready: true }); return }

  // Already loaded.
  if (tab.status === 'complete') { sendResponse({ ready: true }); return }

  // Wait for the tab to finish loading (or time out).
  await new Promise<void>((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener)
      resolve()
    }, TIMEOUT_MS)

    function listener(tabId: number, changeInfo: chrome.tabs.TabChangeInfo) {
      if (tabId === tab.id && changeInfo.status === 'complete') {
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
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
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
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
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
