export interface Wave3Action {
  action_id: string
  action_type: string
  target_selector: string | null
  value: string | null
  description?: string
  reasoning?: string
  safety_level?: string
}

export interface Wave3Result {
  success: boolean
  message: string
  action_id: string
  wave3_capability?: string
  wave3_validated?: boolean
  wave3_details?: Record<string, string | number | boolean | null>
}

const WAVE3_ACTIONS = new Set([
  'canvas_action',
  'svg_action',
  'pdf_viewer',
  'chart_action',
  'map_action',
  'media_control',
  'file_preview',
  'visual_region',
])

export function parseWave3Payload(value: string | null): Record<string, unknown> {
  if (!value) return {}
  try {
    const parsed = JSON.parse(value)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : { text: value }
  } catch {
    return { text: value }
  }
}

export function isWave3VisualAction(actionType: string): boolean {
  return WAVE3_ACTIONS.has(actionType)
}

export async function executeWave3VisualAction(action: Wave3Action): Promise<Wave3Result | null> {
  const wave3Actions = new Set([
    'canvas_action',
    'svg_action',
    'pdf_viewer',
    'chart_action',
    'map_action',
    'media_control',
    'file_preview',
    'visual_region',
  ])
  if (!wave3Actions.has(action.action_type)) return null
  if (action.safety_level === 'danger') {
    return { success: false, message: 'Wave 3 action refused because it is marked dangerous.', action_id: action.action_id }
  }

  const payload = (() => {
    if (!action.value) return {}
    try {
      const parsed = JSON.parse(action.value)
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : { text: action.value }
    } catch {
      return { text: action.value }
    }
  })()

  function q(selector: string | null): Element | null {
    if (!selector) return null
    try { return document.querySelector(selector) } catch { return null }
  }

  function visible(candidate: Element | null): candidate is HTMLElement | SVGElement {
    if (!(candidate instanceof HTMLElement) && !(candidate instanceof SVGElement)) return false
    const rect = candidate.getBoundingClientRect()
    const style = window.getComputedStyle(candidate)
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden'
  }

  function mouseEventAt(el: Element, type: string, x: number, y: number): void {
    const rect = el.getBoundingClientRect()
    el.dispatchEvent(new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      clientX: rect.left + x,
      clientY: rect.top + y,
      view: window,
    }))
  }

  function coordinateAction(capability: string, expected?: 'canvas' | 'svg'): Wave3Result {
    const target = q(action.target_selector)
    if (!target || !visible(target)) {
      return { success: false, message: 'Visual target not found.', action_id: action.action_id, wave3_capability: capability, wave3_validated: false }
    }
    const root = expected === 'svg' ? target.closest('svg') || target : target
    if (expected === 'canvas' && !(root instanceof HTMLCanvasElement)) {
      return { success: false, message: 'Canvas target not found.', action_id: action.action_id, wave3_capability: capability, wave3_validated: false }
    }
    if (expected === 'svg' && !(root instanceof SVGElement)) {
      return { success: false, message: 'SVG target not found.', action_id: action.action_id, wave3_capability: capability, wave3_validated: false }
    }
    const rect = root.getBoundingClientRect()
    const x = Number(payload.x ?? rect.width / 2)
    const y = Number(payload.y ?? rect.height / 2)
    const operation = String(payload.operation ?? 'click')
    if (operation === 'hover') mouseEventAt(root, 'mousemove', x, y)
    else if (operation === 'drag') {
      mouseEventAt(root, 'mousedown', x, y)
      mouseEventAt(root, 'mousemove', Number(payload.to_x ?? x), Number(payload.to_y ?? y))
      mouseEventAt(root, 'mouseup', Number(payload.to_x ?? x), Number(payload.to_y ?? y))
    } else if (operation === 'draw') {
      mouseEventAt(root, 'mousedown', x, y)
      const points = Array.isArray(payload.points) ? payload.points : []
      for (const point of points) {
        if (point && typeof point === 'object') {
          const p = point as Record<string, unknown>
          mouseEventAt(root, 'mousemove', Number(p.x ?? x), Number(p.y ?? y))
        }
      }
      mouseEventAt(root, 'mouseup', x, y)
    } else {
      mouseEventAt(root, 'click', x, y)
    }
    return {
      success: true,
      message: `${capability} ${operation} completed.`,
      action_id: action.action_id,
      wave3_capability: capability,
      wave3_validated: true,
      wave3_details: { operation, x, y, width: Math.round(rect.width), height: Math.round(rect.height) },
    }
  }

  function pdfViewer(): Wave3Result {
    const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim()
    const embeds = document.querySelectorAll('embed[type="application/pdf"], iframe[src$=".pdf"], object[type="application/pdf"], pdf-viewer')
    const query = String(payload.query ?? payload.text ?? '')
    const detected = embeds.length > 0 || location.href.toLowerCase().includes('.pdf') || text.toLowerCase().includes('page')
    const matched = query ? text.toLowerCase().includes(query.toLowerCase()) : true
    return { success: detected && matched, message: detected ? 'PDF viewer detected.' : 'PDF viewer not detected.', action_id: action.action_id, wave3_capability: 'browser.pdf.viewer', wave3_validated: detected && matched, wave3_details: { embed_count: embeds.length, query_match: matched } }
  }

  function mediaControl(): Wave3Result {
    const target = q(action.target_selector)
    if (!(target instanceof HTMLMediaElement)) return { success: false, message: 'Media element not found.', action_id: action.action_id, wave3_capability: 'browser.media.controls', wave3_validated: false }
    const operation = String(payload.operation ?? 'status')
    if (operation === 'play') void target.play?.()
    if (operation === 'pause') target.pause()
    if (operation === 'seek') target.currentTime = Number(payload.current_time ?? payload.time ?? 0)
    if (operation === 'volume') target.volume = Math.max(0, Math.min(1, Number(payload.volume ?? 1)))
    if (operation === 'fullscreen') void target.requestFullscreen?.()
    return { success: true, message: `Media ${operation} completed.`, action_id: action.action_id, wave3_capability: 'browser.media.controls', wave3_validated: true, wave3_details: { operation, paused: target.paused, current_time: Math.round(target.currentTime * 1000) / 1000, volume: target.volume } }
  }

  function filePreview(): Wave3Result {
    const root = q(action.target_selector) || document.body
    const previews = Array.from(document.querySelectorAll('img, embed, object, iframe, video, audio, canvas, [role="dialog"], .preview, [data-testid*="preview"]')).filter(visible)
    const expected = String(payload.expected_text ?? payload.text ?? '')
    const text = (root?.textContent || '').replace(/\s+/g, ' ').trim()
    const matched = expected ? text.toLowerCase().includes(expected.toLowerCase()) : true
    const detected = previews.length > 0
    return { success: detected && matched, message: detected ? 'File preview detected.' : 'File preview not detected.', action_id: action.action_id, wave3_capability: 'browser.file.preview', wave3_validated: detected && matched, wave3_details: { preview_count: previews.length, expected_match: matched } }
  }

  function visualRegion(): Wave3Result {
    const target = q(action.target_selector)
    const mode = String(payload.mode ?? (target ? 'element' : 'viewport'))
    const rect = target?.getBoundingClientRect()
    return {
      success: true,
      message: 'Visual capture metadata prepared.',
      action_id: action.action_id,
      wave3_capability: 'browser.visual_regions',
      wave3_validated: true,
      wave3_details: {
        mode,
        x: Number(payload.x ?? rect?.left ?? 0),
        y: Number(payload.y ?? rect?.top ?? 0),
        width: Number(payload.width ?? rect?.width ?? window.innerWidth),
        height: Number(payload.height ?? rect?.height ?? window.innerHeight),
      },
    }
  }

  if (action.action_type === 'canvas_action') return coordinateAction('browser.canvas', 'canvas')
  if (action.action_type === 'svg_action') return coordinateAction('browser.svg.interaction', 'svg')
  if (action.action_type === 'chart_action') return coordinateAction('browser.charts.graphs')
  if (action.action_type === 'map_action') return coordinateAction('browser.maps.interactive')
  if (action.action_type === 'pdf_viewer') return pdfViewer()
  if (action.action_type === 'media_control') return mediaControl()
  if (action.action_type === 'file_preview') return filePreview()
  if (action.action_type === 'visual_region') return visualRegion()
  return null
}
