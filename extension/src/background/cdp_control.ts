import type { ExecutableAction } from './service_worker_message_validation'

type CdpPoint = { x: number; y: number; source: 'stable_selector' | 'accessibility_name' | 'verified_screenshot' }
type CdpGroundingResolution = {
  point: CdpPoint | null
  attempts: string[]
  fallbackReason: string | null
  screenshotHash: string | null
}
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

export type TrustedLocalFile = {
  absolute_path: string
  filename: string
  mime_type: string
  size_bytes: number
  source: 'chrome_downloads_exact_match' | 'local_downloads_broker_exact_match'
}

const CDP_ACTIONS = new Set([
  'fill', 'select_option', 'choose_date', 'hover', 'scroll',
  'keyboard_shortcut', 'visual_region', 'canvas_action', 'svg_action',
])

const DUPLICATE_SIDE_EFFECT_TERMS = /\b(delete|remove|purchase|payment|pay|place order|checkout|submit|send|publish|post|confirm|logout|sign out|transfer|book|reserve)\b/i

export function keyboardDispatchParameters(key: string, modifiers = 0): Record<string, unknown> {
  const normalized = String(key || '').trim()
  const special: Record<string, { key: string; code: string; virtualKeyCode: number; text?: string }> = {
    enter: { key: 'Enter', code: 'Enter', virtualKeyCode: 13, text: '\r' },
    tab: { key: 'Tab', code: 'Tab', virtualKeyCode: 9 },
    escape: { key: 'Escape', code: 'Escape', virtualKeyCode: 27 },
    backspace: { key: 'Backspace', code: 'Backspace', virtualKeyCode: 8 },
    delete: { key: 'Delete', code: 'Delete', virtualKeyCode: 46 },
    arrowup: { key: 'ArrowUp', code: 'ArrowUp', virtualKeyCode: 38 },
    arrowdown: { key: 'ArrowDown', code: 'ArrowDown', virtualKeyCode: 40 },
    arrowleft: { key: 'ArrowLeft', code: 'ArrowLeft', virtualKeyCode: 37 },
    arrowright: { key: 'ArrowRight', code: 'ArrowRight', virtualKeyCode: 39 },
    space: { key: ' ', code: 'Space', virtualKeyCode: 32, text: ' ' },
  }
  const matched = special[normalized.toLowerCase()]
  if (matched) {
    return {
      key: matched.key,
      code: matched.code,
      windowsVirtualKeyCode: matched.virtualKeyCode,
      nativeVirtualKeyCode: matched.virtualKeyCode,
      modifiers,
      ...(matched.text ? { text: matched.text, unmodifiedText: matched.text } : {}),
    }
  }
  const character = normalized.slice(0, 1)
  const upper = character.toUpperCase()
  const virtualKeyCode = upper ? upper.charCodeAt(0) : 0
  return {
    key: character,
    code: /^[a-z]$/i.test(character) ? `Key${upper}` : character,
    windowsVirtualKeyCode: virtualKeyCode,
    nativeVirtualKeyCode: virtualKeyCode,
    modifiers,
  }
}

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

export function chooseExactAccessibilityBackendNode(nodes: any[], action: ExecutableAction): number | null {
  const expectedName = String(action.grounding?.accessibility_name || '').replace(/\s+/g, ' ').trim().toLowerCase()
  if (!expectedName) return null
  const expectedRole = String(action.grounding?.role || '').replace(/\s+/g, ' ').trim().toLowerCase()
  const exact = nodes.filter((node) => {
    if (!Number.isInteger(node?.backendDOMNodeId)) return false
    const name = String(node?.name?.value || '').replace(/\s+/g, ' ').trim().toLowerCase()
    const role = String(node?.role?.value || '').replace(/\s+/g, ' ').trim().toLowerCase()
    return name === expectedName && (!expectedRole || role === expectedRole)
  })
  const ids = [...new Set(exact.map((node) => Number(node.backendDOMNodeId)))]
  return ids.length === 1 ? ids[0] : null
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

export function visionHitCompatible(
  hit: { tag?: string; role?: string; name?: string; selectorMatched?: boolean } | null,
  action: ExecutableAction,
): boolean {
  if (!hit) return false
  if (hit.selectorMatched) return true
  if (action.action_type === 'click') {
    const expectedName = String(action.grounding?.accessibility_name || '').replace(/\s+/g, ' ').trim().toLowerCase()
    const observedName = String(hit.name || '').replace(/\s+/g, ' ').trim().toLowerCase()
    const expectedRole = String(action.grounding?.role || '').trim().toLowerCase()
    const observedRole = String(hit.role || '').trim().toLowerCase()
    return Boolean(expectedName && observedName === expectedName && (!expectedRole || observedRole === expectedRole))
  }
  const visualActions = new Set(['visual_region', 'canvas_action', 'svg_action', 'chart_action', 'map_action'])
  if (visualActions.has(action.action_type)) {
    return ['canvas', 'svg'].includes(String(hit.tag || '').toLowerCase()) ||
      ['img', 'application', 'graphics-document', 'graphics-symbol'].includes(String(hit.role || '').toLowerCase())
  }
  const expected = `${action.grounding?.accessibility_name || ''} ${action.description || ''}`.toLowerCase()
  const observed = String(hit.name || '').toLowerCase()
  const tokens = observed.split(/[^a-z0-9]+/).filter((token) => token.length >= 3)
  return tokens.some((token) => expected.includes(token))
}

function debuggee(tabId: number): chrome.debugger.Debuggee {
  return { tabId }
}

async function send(target: chrome.debugger.Debuggee, method: string, params: Record<string, unknown> = {}): Promise<ProtocolResult> {
  return await chrome.debugger.sendCommand(target, method, params) as ProtocolResult
}

export function runtimeGroundingExpression(selector: string, exactName: string | null, objective: string | null = null): string {
  return `(() => {
    const selector = ${JSON.stringify(selector)};
    const exactName = ${JSON.stringify(exactName)};
    const objective = ${JSON.stringify(objective)};
    let visited = 0;
    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    const label = (el) => normalize(el.getAttribute('aria-label') || el.getAttribute('title') || el.value || el.textContent || '');
    const primaryLine = (el) => String(el.innerText || el.textContent || '')
      .split(/\\r?\\n/)
      .map(normalize)
      .find(Boolean) || '';
    const resultContainer = (el) => {
      if (!el.closest) return null;
      return el.closest('[role="row"], [role="listitem"], [role="option"]')
        || el.closest('button, a[href], [role="button"], [role="link"], [role="menuitem"], [tabindex="0"]');
    };
    const sectionLabel = (container) => {
      let cursor = container;
      for (let checked = 0; cursor && checked < 200; checked += 1, cursor = cursor.previousElementSibling) {
        const heading = cursor.matches && cursor.matches('h1, h2, h3, [role="heading"]')
          ? cursor
          : cursor.querySelector && cursor.querySelector('h1, h2, h3, [role="heading"]');
        const text = heading && normalize(heading.innerText || heading.textContent || heading.getAttribute('aria-label'));
        if (text) return text;
      }
      return '';
    };
    const tokenKey = (token) => token.length > 3 && token.endsWith('s') ? token.slice(0, -1) : token;
    const objectiveTokens = new Set(normalize(objective).split(/[^a-z0-9]+/).filter(Boolean).map(tokenKey));
    const sectionAffinity = (container) => normalize(sectionLabel(container))
      .split(/[^a-z0-9]+/)
      .filter(Boolean)
      .map(tokenKey)
      .filter((token) => objectiveTokens.has(token)).length;
    const exactActionableAncestor = (el) => {
      if (!exactName || label(el) !== normalize(exactName)) return null;
      const actionable = resultContainer(el);
      return actionable && visible(actionable) ? actionable : null;
    };
    const containsUniqueExactIdentity = (el) => {
      if (!exactName || !el.querySelectorAll) return false;
      const exact = Array.from(el.querySelectorAll('[aria-label], [title]'))
        .filter(visible)
        .filter((candidate) => label(candidate) === normalize(exactName));
      return exact.length === 1;
    };
    const visible = (el) => {
      const r = el.getBoundingClientRect();
      const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    };
    const walk = (root, offsetX, offsetY, depth) => {
      if (!root || depth > 12 || visited > 8000) return { ok: false, reason: 'selector_search_limit' };
      let matches = [];
      try { matches = Array.from(root.querySelectorAll(selector)).filter(visible); } catch { return { ok: false, reason: 'selector_invalid' }; }
      if (matches.length > 1) {
        const exactAncestors = [...new Set(matches.map(exactActionableAncestor).filter(Boolean))];
        const ranked = exactAncestors
          .map((element) => ({ element, affinity: sectionAffinity(element), primaryExact: primaryLine(element) === normalize(exactName) }))
          .sort((a, b) => b.affinity - a.affinity || Number(b.primaryExact) - Number(a.primaryExact));
        const winner = ranked[0] || null;
        const runnerUp = ranked[1] || null;
        const uniquelyGrounded = winner && (
          (winner.affinity > 0 && (!runnerUp || winner.affinity > runnerUp.affinity))
          || (winner.primaryExact && (!runnerUp || !runnerUp.primaryExact))
        );
        if (uniquelyGrounded) {
          const actionable = winner.element;
          actionable.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
          const r = actionable.getBoundingClientRect();
          return {
            ok: true,
            x: offsetX + r.left + r.width / 2,
            y: offsetY + r.top + r.height / 2,
            observedName: normalize(exactName),
            resultSection: sectionLabel(actionable),
            disambiguatedBy: winner.affinity > 0 ? 'objective_result_section' : 'exact_actionable_primary_line',
          };
        }
        return { ok: false, reason: 'selector_ambiguous', matchCount: matches.length, exactActionableCount: exactAncestors.length };
      }
      const direct = matches[0] || null;
      if (direct && (!exactName || label(direct) === normalize(exactName) || containsUniqueExactIdentity(direct))) {
        direct.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
        const r = direct.getBoundingClientRect();
        return { ok: true, x: offsetX + r.left + r.width / 2, y: offsetY + r.top + r.height / 2, observedName: label(direct) };
      }
      if (direct) return { ok: false, reason: 'selector_exact_name_mismatch', observedName: label(direct) };
      const elements = root.querySelectorAll ? Array.from(root.querySelectorAll('*')) : [];
      for (const el of elements) {
        visited += 1;
        if (el.shadowRoot) {
          const hit = walk(el.shadowRoot, offsetX, offsetY, depth + 1);
          if (hit && (hit.ok || hit.reason !== 'selector_not_found')) return hit;
        }
        if (el.tagName === 'IFRAME') {
          try {
            const frameRect = el.getBoundingClientRect();
            const hit = walk(el.contentDocument, offsetX + frameRect.left, offsetY + frameRect.top, depth + 1);
            if (hit && (hit.ok || hit.reason !== 'selector_not_found')) return hit;
          } catch {}
        }
      }
      return { ok: false, reason: 'selector_not_found' };
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
  async execute(tabId: number, action: ExecutableAction, trustedLocalFile?: TrustedLocalFile): Promise<CdpExecutionResult> {
    const target = debuggee(tabId)
    const startedAt = performance.now()
    const navigationSignals: string[] = []
    let fileChooserResolve: ((value: { backendNodeId: number; frameId?: string }) => void) | null = null
    const onEvent = (source: chrome.debugger.Debuggee, method: string, params?: Record<string, any>) => {
      if (source.tabId === tabId && /^(Page\.(frameNavigated|lifecycleEvent|navigatedWithinDocument)|Target\.(targetCreated|attachedToTarget))$/.test(method)) {
        if (navigationSignals.length < 30) navigationSignals.push(method)
      }
      if (source.tabId === tabId && method === 'Page.fileChooserOpened' && Number.isInteger(params?.backendNodeId)) {
        fileChooserResolve?.({ backendNodeId: Number(params!.backendNodeId), frameId: params?.frameId })
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
      let grounding = await this.resolvePoint(target, action)
      const revealSelector = action.content_insertion?.stage === 'select_bound_content'
        ? String(action.content_insertion?.reveal_selector || '').trim()
        : ''
      if (!grounding.point && revealSelector) {
        const revealAction: ExecutableAction = {
          ...action,
          target_selector: revealSelector,
          description: 'Reveal the previously observed content-insertion options',
          grounding: {
            source: 'dom_snapshot',
            selector_id: null,
            frame_id: action.grounding?.frame_id || 'top',
            accessibility_name: null,
            role: null,
            semantic_kind: 'content_insertion_trigger',
            expected_url_path: action.grounding?.expected_url_path || null,
            screenshot_verified: false,
            screenshot_hash: null,
            bounding_box: null,
          },
        }
        const revealGrounding = await this.resolvePoint(target, revealAction)
        if (revealGrounding.point) {
          await this.dispatch(target, revealAction, revealGrounding.point)
          await new Promise((resolve) => setTimeout(resolve, 160))
          const revealedTarget = await this.resolvePoint(target, action)
          grounding = {
            ...revealedTarget,
            attempts: [
              ...grounding.attempts,
              'content_insertion_reveal:selected_verified_trigger',
              ...revealedTarget.attempts,
            ],
            fallbackReason: grounding.fallbackReason || revealedTarget.fallbackReason,
          }
        } else {
          grounding = {
            ...grounding,
            attempts: [
              ...grounding.attempts,
              ...revealGrounding.attempts.map((attempt) => `content_insertion_reveal:${attempt}`),
            ],
          }
        }
      }
      if (!grounding.point) {
        return this.result(action, false, 'CDP could not ground the requested target without changing its identity.', inventory, null, grounding.screenshotHash, startedAt, grounding.attempts, grounding.fallbackReason)
      }
      const needsFileBinding = action.content_insertion?.opens_native_chooser === true
      if (needsFileBinding && !trustedLocalFile?.absolute_path) {
        return this.result(action, false, 'Trusted executor rejected the chooser because no exact approved local file was bound.', inventory, grounding.point.source, grounding.screenshotHash, startedAt, grounding.attempts, grounding.fallbackReason)
      }
      let chooserPromise: Promise<{ backendNodeId: number; frameId?: string }> | null = null
      if (needsFileBinding) {
        await send(target, 'Page.setInterceptFileChooserDialog', { enabled: true })
        chooserPromise = new Promise((resolve) => { fileChooserResolve = resolve })
      }
      await this.dispatch(target, action, grounding.point)
      if (chooserPromise && trustedLocalFile) {
        const chooser = await Promise.race([
          chooserPromise,
          new Promise<never>((_, reject) => setTimeout(() => reject(new Error('bounded_file_chooser_timeout')), 5_000)),
        ])
        await send(target, 'DOM.setFileInputFiles', {
          files: [trustedLocalFile.absolute_path],
          backendNodeId: chooser.backendNodeId,
        })
        await send(target, 'Page.setInterceptFileChooserDialog', { enabled: false }).catch(() => undefined)
        grounding.attempts.push(`file_binding:${trustedLocalFile.source}:exact_filename`)
      }
      await new Promise((resolve) => setTimeout(resolve, 180))
      return this.result(action, true, `CDP ${action.action_type} dispatched via ${grounding.point.source} grounding.`, inventory, grounding.point.source, grounding.screenshotHash, startedAt, grounding.attempts, grounding.fallbackReason)
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

  private async resolvePoint(target: chrome.debugger.Debuggee, action: ExecutableAction): Promise<CdpGroundingResolution> {
    const attempts: string[] = []
    if (action.action_type === 'keyboard_shortcut' && !action.target_selector) {
      return { point: { x: 0, y: 0, source: 'stable_selector' }, attempts: ['keyboard_shortcut:no_target'], fallbackReason: null, screenshotHash: null }
    }
    if (action.target_selector) {
      const evaluated = await send(target, 'Runtime.evaluate', {
        expression: runtimeGroundingExpression(
          action.target_selector,
          action.grounding?.accessibility_name?.trim() || null,
          action.description || null,
        ),
        returnByValue: true,
        awaitPromise: false,
      }).catch(() => ({} as ProtocolResult))
      const value = evaluated?.result?.value
      if (value?.ok === true && Number.isFinite(value?.x) && Number.isFinite(value?.y)) {
        attempts.push('stable_selector:selected_unique_exact')
        return { point: { x: value.x, y: value.y, source: 'stable_selector' }, attempts, fallbackReason: null, screenshotHash: null }
      }
      attempts.push(`stable_selector:rejected:${String(value?.reason || 'unresolved')}`)
    } else {
      attempts.push('stable_selector:unavailable')
    }

    const frameId = action.grounding?.frame_id && action.grounding.frame_id !== 'top' ? action.grounding.frame_id : undefined
    const ax = await send(target, 'Accessibility.getFullAXTree', frameId ? { frameId } : {}).catch(() => ({ nodes: [] }))
    const backendNodeId = action.action_type === 'click'
      ? chooseExactAccessibilityBackendNode(Array.isArray(ax.nodes) ? ax.nodes : [], action)
      : chooseAccessibilityBackendNode(Array.isArray(ax.nodes) ? ax.nodes : [], action)
    if (backendNodeId !== null) {
      const [box, metrics] = await Promise.all([
        send(target, 'DOM.getBoxModel', { backendNodeId }).catch(() => ({} as ProtocolResult)),
        send(target, 'Page.getLayoutMetrics').catch(() => ({} as ProtocolResult)),
      ])
      const viewport = metrics.visualViewport || metrics.layoutViewport || {}
      const center = centerFromBoxModel(box.model, Number(viewport.pageX || 0), Number(viewport.pageY || 0))
      if (center) {
        attempts.push(action.action_type === 'click' ? 'accessibility_name:selected_unique_exact' : 'accessibility_name:selected_ranked')
        return { point: { ...center, source: 'accessibility_name' }, attempts, fallbackReason: attempts[0], screenshotHash: null }
      }
    }
    attempts.push('accessibility_name:rejected:no_unique_exact_box')

    const box = action.grounding?.bounding_box
    const screenshotAllowed = action.grounding?.source === 'vision_region'
      && action.grounding?.screenshot_verified === true
      && Boolean(action.grounding?.screenshot_hash)
    if (screenshotAllowed && box && [box.x, box.y, box.width, box.height].every(Number.isFinite) && box.width > 0 && box.height > 0) {
      const screenshot = await send(target, 'Page.captureScreenshot', { format: 'jpeg', quality: 55, fromSurface: true }).catch(() => ({} as ProtocolResult))
      const screenshotHash = typeof screenshot.data === 'string' ? await sha256Text(screenshot.data) : null
      if (!screenshotHash || screenshotHash !== action.grounding?.screenshot_hash) {
        attempts.push('verified_screenshot:rejected:hash_mismatch')
        return { point: null, attempts, fallbackReason: attempts.slice(0, -1).join(';'), screenshotHash }
      }
      const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 }
      const metrics = await send(target, 'Page.getLayoutMetrics').catch(() => ({} as ProtocolResult))
      const viewport = metrics.cssVisualViewport || metrics.visualViewport || metrics.cssLayoutViewport || metrics.layoutViewport || {}
      const width = Number(viewport.clientWidth || 0)
      const height = Number(viewport.clientHeight || 0)
      if (width > 0 && height > 0 && (point.x < 0 || point.y < 0 || point.x > width || point.y > height)) {
        attempts.push('verified_screenshot:rejected:outside_viewport')
        return { point: null, attempts, fallbackReason: attempts.slice(0, -1).join(';'), screenshotHash }
      }
      const hitResult = await send(target, 'Runtime.evaluate', {
        expression: `(() => {
          const el = document.elementFromPoint(${JSON.stringify(point.x)}, ${JSON.stringify(point.y)});
          if (!el) return null;
          let selectorMatched = false;
          try { selectorMatched = Boolean(${JSON.stringify(action.target_selector)} && (el.matches(${JSON.stringify(action.target_selector)}) || el.closest(${JSON.stringify(action.target_selector)}))); } catch {}
          return {
            tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || '', selectorMatched,
            name: el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent || ''
          };
        })()`,
        returnByValue: true,
      }).catch(() => ({} as ProtocolResult))
      if (visionHitCompatible(hitResult?.result?.value || null, action)) {
        attempts.push('verified_screenshot:selected:hash_and_hit_verified')
        return { point: { ...point, source: 'verified_screenshot' }, attempts, fallbackReason: attempts.slice(0, -1).join(';'), screenshotHash }
      }
      attempts.push('verified_screenshot:rejected:hit_identity_mismatch')
      return { point: null, attempts, fallbackReason: attempts.slice(0, -1).join(';'), screenshotHash }
    }
    attempts.push('verified_screenshot:unavailable_or_unverified')
    return { point: null, attempts, fallbackReason: attempts.slice(0, -1).join(';'), screenshotHash: null }
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
      await mouse('mouseMoved')
      await mouse('mousePressed', { button: 'left', clickCount: 1 })
      await mouse('mouseReleased', { button: 'left', clickCount: 1 })
      const keyParameters = keyboardDispatchParameters(key, modifiers)
      await send(target, 'Input.dispatchKeyEvent', { type: 'rawKeyDown', ...keyParameters })
      await send(target, 'Input.dispatchKeyEvent', { type: 'keyUp', ...keyParameters, text: '', unmodifiedText: '' })
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
    groundingAttempts: string[] = [],
    fallbackReason: string | null = null,
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
        cdp_grounding_attempts: groundingAttempts.join('|'),
        cdp_fallback_reason: fallbackReason,
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
