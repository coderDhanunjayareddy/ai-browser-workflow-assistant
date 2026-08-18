const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = path.join(root, '.tmp-cdp-control-test')

fs.rmSync(outDir, { recursive: true, force: true })
execFileSync(
  process.execPath,
  [
    path.join(root, 'node_modules/typescript/bin/tsc'),
    '--target', 'ES2020',
    '--lib', 'ES2020,DOM',
    '--types', 'chrome',
    '--module', 'commonjs',
    '--moduleResolution', 'node',
    '--strict',
    '--skipLibCheck',
    '--outDir', outDir,
    'src/background/cdp_control.ts',
    'src/background/service_worker_message_validation.ts',
  ],
  { cwd: root, stdio: 'inherit' },
)

const {
  CdpController,
  centerFromBoxModel,
  chooseAccessibilityBackendNode,
  chooseExactAccessibilityBackendNode,
  countFrames,
  shouldAttemptCdpFallback,
  visionHitCompatible,
} = require(path.join(outDir, 'background', 'cdp_control.js'))

function action(overrides = {}) {
  return {
    action_id: 'action-1',
    action_type: 'click',
    target_selector: '#save',
    value: null,
    description: 'Open details',
    reasoning: 'Requested by user',
    safety_level: 'safe',
    ...overrides,
  }
}

function installChromeMock(commandHandler) {
  const calls = []
  let listener = null
  global.chrome = {
    debugger: {
      attach: async (target, version) => { calls.push(['attach', target, version]) },
      detach: async (target) => { calls.push(['detach', target]) },
      sendCommand: async (target, method, params) => {
        calls.push(['command', method, params])
        return commandHandler(method, params)
      },
      onEvent: {
        addListener: (value) => { listener = value; calls.push(['listener-add']) },
        removeListener: (value) => { assert.equal(value, listener); calls.push(['listener-remove']) },
      },
    },
  }
  return calls
}

test.after(() => fs.rmSync(outDir, { recursive: true, force: true }))

test('fallback is limited to safe, non-consequential no-effect actions', () => {
  assert.equal(shouldAttemptCdpFallback(action(), { success: true, verification: { reason: 'no_effect' } }), false)
  assert.equal(shouldAttemptCdpFallback(action({ action_type: 'fill' }), { success: true, verification: { reason: 'no_effect' } }), true)
  assert.equal(shouldAttemptCdpFallback(action({ description: 'Submit payment' }), { success: true, verification: { reason: 'no_effect' } }), false)
  assert.equal(shouldAttemptCdpFallback(action({ safety_level: 'caution' }), { success: false }), false)
  assert.equal(shouldAttemptCdpFallback(action(), { success: true, verification: { reason: 'verified' } }), false)
})

test('frame inventory recursively counts nested frames', () => {
  const result = countFrames({
    frame: { id: 'root' },
    childFrames: [{ frame: { id: 'child' }, childFrames: [{ frame: { id: 'grandchild' } }] }],
  })
  assert.deepEqual(result, { count: 3, ids: ['root', 'child', 'grandchild'] })
})

test('accessibility grounding ranks role and accessible name', () => {
  const selected = chooseAccessibilityBackendNode([
    { backendDOMNodeId: 10, role: { value: 'button' }, name: { value: 'Cancel' } },
    { backendDOMNodeId: 20, role: { value: 'button' }, name: { value: 'Open details' } },
  ], action())
  assert.equal(selected, 20)
})

test('click accessibility fallback requires one exact name and role match', () => {
  const nodes = [
    { backendDOMNodeId: 10, role: { value: 'listitem' }, name: { value: 'Teja' } },
    { backendDOMNodeId: 20, role: { value: 'listitem' }, name: { value: 'Teja Spc' } },
  ]
  const exactAction = action({ grounding: { source: 'dom_snapshot', accessibility_name: 'Teja Spc', role: 'listitem' } })
  assert.equal(chooseExactAccessibilityBackendNode(nodes, exactAction), 20)
  assert.equal(chooseExactAccessibilityBackendNode([...nodes, { ...nodes[1], backendDOMNodeId: 30 }], exactAction), null)
})

test('box model center is converted from page to viewport coordinates', () => {
  assert.deepEqual(
    centerFromBoxModel({ content: [100, 200, 140, 200, 140, 240, 100, 240] }, 10, 20),
    { x: 110, y: 200 },
  )
})

test('vision coordinates require a current compatible hit target', () => {
  const exact = action({ grounding: { source: 'vision_region', accessibility_name: 'Open details', role: 'button' } })
  assert.equal(visionHitCompatible({ tag: 'button', role: 'button', name: 'Open details', selectorMatched: false }, exact), true)
  assert.equal(visionHitCompatible({ tag: 'button', role: 'button', name: 'Delete account', selectorMatched: false }, exact), false)
  assert.equal(visionHitCompatible({ tag: 'div', name: '', selectorMatched: true }, action()), true)
  assert.equal(visionHitCompatible({ tag: 'canvas', name: '', selectorMatched: false }, action({ action_type: 'canvas_action' })), true)
  assert.equal(visionHitCompatible(null, action()), false)
})

test('controller attaches, inventories, dispatches trusted input, and always detaches', async () => {
  const calls = installChromeMock((method) => {
    if (method === 'Target.getTargets') return { targetInfos: [{ targetId: 'page' }] }
    if (method === 'Page.getFrameTree') return { frameTree: { frame: { id: 'root' } } }
    if (method === 'Runtime.evaluate') return { result: { value: { ok: true, x: 50, y: 75 } } }
    return {}
  })
  const result = await new CdpController().execute(7, action())
  assert.equal(result.success, true)
  assert.equal(result.cdp_grounding_source, 'stable_selector')
  assert.equal(result.adapter_trace.cdp_grounding_attempts, 'stable_selector:selected_unique_exact')
  assert.equal(result.cdp_frame_count, 1)
  assert.equal(calls[0][0], 'attach')
  assert.ok(calls.some((item) => item[0] === 'command' && item[1] === 'Input.dispatchMouseEvent' && item[2].type === 'mousePressed'))
  assert.deepEqual(calls.slice(-2).map((item) => item[0]), ['listener-remove', 'detach'])
})

test('controller detaches when grounding fails', async () => {
  const calls = installChromeMock((method) => {
    if (method === 'Target.getTargets') return { targetInfos: [] }
    if (method === 'Page.getFrameTree') return { frameTree: null }
    if (method === 'Runtime.evaluate') return { result: { value: null } }
    if (method === 'Accessibility.getFullAXTree') return { nodes: [] }
    return {}
  })
  const result = await new CdpController().execute(8, action({ grounding: undefined }))
  assert.equal(result.success, false)
  assert.match(result.message, /could not ground/i)
  assert.equal(calls.at(-1)[0], 'detach')
})
