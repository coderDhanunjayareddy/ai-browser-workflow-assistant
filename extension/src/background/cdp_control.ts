import type { ExecutableAction } from './service_worker_message_validation'

type CdpPoint = { x: number; y: number; source: 'dom' | 'accessibility' | 'vision' }
type ProtocolResult = Record<string, any>

export type CdpInventory = {
  targetCount: number
  frameCount: number
  frameIds: string[]
  navigationSignals: string[]
}

export type CdpExecutionResult = {
  success: boolean
  message: string
  action_id: string
  execution_adapter: 'cdp'
  cdp_grounding_source: string | null
  cdp_frame_count: number
  cdp_target_count: number
  cdp_screenshot_hash: string | null
  adapter_trace: Record<string, string | number | boolean | null>
}

const CDP_ACTIONS = new Set([
  'click', 'fill', 'select_option', 'choose_date', 'hover', 'scroll',
  'keyboard_shortcut', 'visual_region', 'canvas_action', 'svg_action',
])

const DUPLICATE_SIDE_EFFECT_TERMS = /\b(delete|remove|purchase|payment|pay|place order|checkout|submit|send|publish|post|confirm|logout|sign out|transfer|book|reserve)\b/i

export function shouldAttemptCdpFallback(
  action: ExecutableAction,
  result: { success: boolean; verification?: { verified?: boolean; reason?: string } },
): boolean {
  if (action.safety_level !== 'safe' || !CDP_ACTIONS.has(action.action_type)) return false
  if (DUPLICATE_SIDE_EFFECT_TERMS.test(`${action.description || ''} ${action.reasoning || ''}`)) return false
  return !result.success || result.verification?.reason === 'no_effect'
}

export function countFrames(frameTree: any): { count: number; ids: string[] } {
  const ids: string[] = []
  const visit = (node: any) => {
    if (!node) return
    if (typeof node.frame?.id === 'string') ids.push(node.frame.id)
    for (const child of Array.isArray(node.childFrames) ? node.childFrames : []) visit(child)
  }
  visit(frameTree)
  return { count: ids.length, ids }
}

export function chooseAccessibilityBackendNode(nodes: any[], action: ExecutableAction): number | null {
  const goal = `${action.grounding?.accessibility_name || ''} ${action.description || ''}`.toLowerCase()
  const goalTokens = new Set(goal.split(/[^a-z0-9]+/).filter((token) => token.length >= 2))
  const expectedRoles = action.action_type === 'fill'
    ? new Set(['textbox', 'searchbox', 'combobox'])
    : action.action_type === 'select_option'
      ? new Set(['combobox', 'listbox'])
      : new Set(['button', 'link', 'checkbox', 'radio', 'menuitem', 'tab'])
  const ranked = nodes
    .filter((node) => Number.isInteger(node?.backendDOMNodeId))
    .map((node) => {
      const name = String(node?.name?.value || '').toLowerCase()
      const role = String(node?.role?.value || '').toLowerCase()
      const tokens = name.split(/[^a-z0-9]+/).filter((token) => token.length >= 2)
      const matches = tokens.filter((token) => goalTokens.has(token)).length
      return { node, score: matches * 10 + (expectedRoles.has(role) ? 4 : 0) + (name && goal.includes(name) ? 8 : 0) }
    })
    .filter((item) => item.score >= 4)
    .sort((a, b) => b.score - a.score)
  return ranked.length > 0 ? Number(ranked[0].node.backendDOMNodeId) : null
}

export function centerFromBoxModel(model: any, pageX = 0, pageY = 0): { x: number; y: number } | null {
  const quad = model?.content || model?.border
  if (!Array.isArray(quad) || quad.length < 8 || !quad.every((item: unknown) => typeof item === 'number')) return null
  const xs = [quad[0], quad[2], quad[4], quad[6]]
  const ys = [quad[1], quad[3], quad[5], quad[7]]
  return {
    x: xs.reduce((total, item) => total + item, 0) / 4 - pageX,
    y: ys.reduce((total, item) => total + item, 0) / 4 - pageY,
  }
}

function debuggee(tabId: number): chrome.debugger.Debuggee {
  return { tabId }
}

async function send(target: chrome.debugger.Debuggee, method: string, params: Record<string, unknown> = {}): Promise<ProtocolResult> {
  return await chrome.debugger.sendCommand(target, method, params) as ProtocolResult
}

function runtimeGroundingExpression(selector: string): string {
  return `(() => {
    const selector = ${JSON.stringify(selector)};
    let visited = 0;
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    };
    const walk = (root, offsetX, offsetY, depth) => {
      if (!root || depth > 12 || visited > 8000) return null;
      let direct = null;
      try { direct = root.querySelector(selector); } catch { return null; }
      if (direct && visible(direct)) {
        const r = direct.getBoundingClientRect();
        return { x: offsetX + r.left + r.width / 2, y: offsetY + r.top + r.height / 2 };
      }
      const elements = root.querySelectorAll ? Array.from(root.querySelectorAll('*')) : [];
      for (const el of elements) {
        visited += 1;
        if (el.shadowRoot) {
          const hit = walk(el.shadowRoot, offsetX, offsetY, depth + 1);
          if (hit) return hit;
        }
        if (el.tagName === 'IFRAME') {
          try {
            const frameRect = el.getBoundingClientRect();
            const hit = walk(el.contentDocument, offsetX + frameRect.left, offsetY + frameRect.top, depth + 1);
            if (hit) return hit;
          } catch {}
        }
      }
      return null;
    };
    return walk(document, 0, 0, 0);
  })()`
}

async function sha256Text(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest)).map((item) => item.toString(16).padStart(2, '0')).join('')
}

export class CdpController {
  async execute(tabId: number, action: ExecutableAction): Promise<CdpExecutionResult> {
    const target = debuggee(tabId)
    const startedAt = performance.now()
    const navigationSignals: string[] = []
    const onEvent = (source: chrome.debugger.Debuggee, method: string) => {
      if (source.tabId === tabId && /^(Page\.(frameNavigated|lifecycleEvent|navigatedWithinDocument)|Target\.(targetCreated|attachedToTarget))$/.test(method)) {
        if (navigationSignals.length < 30) navigationSignals.push(method)
      }
    }
    let attached = false
    try {
      await chrome.debugger.attach(target, '1.3')
      attached = true
      chrome.debugger.onEvent.addListener(onEvent)
      await Promise.allSettled([
        send(target, 'Page.enable'),
        send(target, 'DOM.enable'),
        send(target, 'Runtime.enable'),
        send(target, 'Accessibility.enable'),
        send(target, 'Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: false, flatten: true }),
        send(target, 'Page.setLifecycleEventsEnabled', { enabled: true }),
      ])

      const inventory = await this.inventory(target, navigationSignals)
      const point = await this.resolvePoint(target, action)
      if (!point) return this.result(action, false, 'CDP could not ground the requested target.', inventory, null, null, startedAt)

      let screenshotHash: string | null = null
      if (point.source === 'vision') {
        const screenshot = await send(target, 'Page.captureScreenshot', { format: 'jpeg', quality: 55, fromSurface: true })
        screenshotHash = typeof screenshot.data === 'string' ? await sha256Text(screenshot.data) : null
      }
      await this.dispatch(target, action, point)
      await new Promise((resolve) => setTimeout(resolve, 180))
      return this.result(action, true, `CDP ${action.action_type} dispatched via ${point.source} grounding.`, inventory, point.source, screenshotHash, startedAt)
    } catch (error) {
      return this.result(action, false, `CDP execution failed: ${String(error)}`, { targetCount: 0, frameCount: 0, frameIds: [], navigationSignals }, null, null, startedAt)
    } finally {
      if (attached) {
        chrome.debugger.onEvent.removeListener(onEvent)
        await chrome.debugger.detach(target).catch(() => undefined)
      }
    }
  }

  private async inventory(target: chrome.debugger.Debuggee, navigationSignals: string[]): Promise<CdpInventory> {
    const [targets, frames] = await Promise.all([
      send(target, 'Target.getTargets').catch(() => ({ targetInfos: [] })),
      send(target, 'Page.getFrameTree').catch(() => ({ frameTree: null })),
    ])
    const frameInventory = countFrames(frames.frameTree)
    return {
      targetCount: Array.isArray(targets.targetInfos) ? targets.targetInfos.length : 0,
      frameCount: frameInventory.count,
      frameIds: frameInventory.ids.slice(0, 100),
      navigationSignals,
    }
  }

  private async resolvePoint(target: chrome.debugger.Debuggee, action: ExecutableAction): Promise<CdpPoint | null> {
    if (action.action_type === 'keyboard_shortcut' && !action.target_selector) {
      return { x: 0, y: 0, source: 'dom' }
    }
    if (action.target_selector) {
      const evaluated = await send(target, 'Runtime.evaluate', {
        expression: runtimeGroundingExpression(action.target_selector),
        returnByValue: true,
        awaitPromise: false,
      }).catch(() => ({} as ProtocolResult))
      const value = evaluated?.result?.value
      if (Number.isFinite(value?.x) && Number.isFinite(value?.y)) return { x: value.x, y: value.y, source: 'dom' }
    }

    const ax = await send(target, 'Accessibility.getFullAXTree').catch(() => ({ nodes: [] }))
    const backendNodeId = chooseAccessibilityBackendNode(Array.isArray(ax.nodes) ? ax.nodes : [], action)
    if (backendNodeId !== null) {
      const [box, metrics] = await Promise.all([
        send(target, 'DOM.getBoxModel', { backendNodeId }).catch(() => ({} as ProtocolResult)),
        send(target, 'Page.getLayoutMetrics').catch(() => ({} as ProtocolResult)),
      ])
      const viewport = metrics.visualViewport || metrics.layoutViewport || {}
      const center = centerFromBoxModel(box.model, Number(viewport.pageX || 0), Number(viewport.pageY || 0))
      if (center) return { ...center, source: 'accessibility' }
    }

    const box = action.grounding?.bounding_box
    if (box && [box.x, box.y, box.width, box.height].every(Number.isFinite) && box.width > 0 && box.height > 0) {
      return { x: box.x + box.width / 2, y: box.y + box.height / 2, source: 'vision' }
    }
    return null
  }

  private async dispatch(target: chrome.debugger.Debuggee, action: ExecutableAction, point: CdpPoint): Promise<void> {
    const mouse = (type: string, extra: Record<string, unknown> = {}) => send(target, 'Input.dispatchMouseEvent', {
      type, x: point.x, y: point.y, ...extra,
    })
    if (action.action_type === 'keyboard_shortcut') {
      const parts = String(action.value || '').split('+').map((item) => item.trim()).filter(Boolean)
      const key = parts.pop() || ''
      const modifiers = parts.reduce((mask, part) => mask | ({ alt: 1, ctrl: 2, control: 2, meta: 4, command: 4, shift: 8 }[part.toLowerCase()] || 0), 0)
      if (!key) throw new Error('keyboard shortcut has no key')
      await send(target, 'Input.dispatchKeyEvent', { type: 'keyDown', key, modifiers })
      await send(target, 'Input.dispatchKeyEvent', { type: 'keyUp', key, modifiers })
      return
    }
    if (action.action_type === 'hover') {
      await mouse('mouseMoved')
      return
    }
    if (action.action_type === 'scroll') {
      const deltaY = Number.parseFloat(String(action.value || '')) || 600
      await mouse('mouseWheel', { deltaX: 0, deltaY })
      return
    }
    await mouse('mouseMoved')
    await mouse('mousePressed', { button: 'left', clickCount: 1 })
    await mouse('mouseReleased', { button: 'left', clickCount: 1 })
    if (['fill', 'choose_date', 'select_option'].includes(action.action_type)) {
      await send(target, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'Control', code: 'ControlLeft', modifiers: 2 })
      await send(target, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'a', code: 'KeyA', modifiers: 2 })
      await send(target, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'a', code: 'KeyA', modifiers: 2 })
      await send(target, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'Control', code: 'ControlLeft' })
      await send(target, 'Input.insertText', { text: String(action.value || '') })
      if (action.action_type === 'select_option') {
        await send(target, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter' })
        await send(target, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter' })
      }
    }
  }

  private result(
    action: ExecutableAction,
    success: boolean,
    message: string,
    inventory: CdpInventory,
    source: string | null,
    screenshotHash: string | null,
    startedAt: number,
  ): CdpExecutionResult {
    return {
      success,
      message,
      action_id: action.action_id,
      execution_adapter: 'cdp',
      cdp_grounding_source: source,
      cdp_frame_count: inventory.frameCount,
      cdp_target_count: inventory.targetCount,
      cdp_screenshot_hash: screenshotHash,
      adapter_trace: {
        cdp_duration_ms: Math.max(0, Math.round(performance.now() - startedAt)),
        cdp_frame_count: inventory.frameCount,
        cdp_target_count: inventory.targetCount,
        cdp_navigation_signal_count: inventory.navigationSignals.length,
        cdp_grounding_source: source,
      },
    }
  }
}

export async function advancedControlEnabled(): Promise<boolean> {
  const [stored, permitted] = await Promise.all([
    chrome.storage.local.get('advanced_control_enabled'),
    chrome.permissions.contains({ permissions: ['debugger'] }),
  ])
  return stored.advanced_control_enabled === true && permitted
}
