const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wave3-visual-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'wave3_visual.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  isWave3VisualAction,
  parseWave3Payload,
  executeWave3VisualAction,
} = require(path.join(outDir, 'wave3_visual.js'))

test('Wave 3 visual action routing is explicit', () => {
  assert.equal(isWave3VisualAction('canvas_action'), true)
  assert.equal(isWave3VisualAction('svg_action'), true)
  assert.equal(isWave3VisualAction('pdf_viewer'), true)
  assert.equal(isWave3VisualAction('chart_action'), true)
  assert.equal(isWave3VisualAction('map_action'), true)
  assert.equal(isWave3VisualAction('media_control'), true)
  assert.equal(isWave3VisualAction('file_preview'), true)
  assert.equal(isWave3VisualAction('visual_region'), true)
  assert.equal(isWave3VisualAction('clipboard'), false)
})

test('Wave 3 payload parsing preserves JSON and plain text', () => {
  assert.deepEqual(parseWave3Payload('hello'), { text: 'hello' })
  assert.deepEqual(parseWave3Payload('{"operation":"click","x":4}'), { operation: 'click', x: 4 })
  assert.deepEqual(parseWave3Payload(null), {})
})

test('Wave 3 executor refuses dangerous actions before DOM access', async () => {
  const result = await executeWave3VisualAction({
    action_id: 'danger-visual',
    action_type: 'canvas_action',
    target_selector: '#canvas',
    value: '{"operation":"click"}',
    safety_level: 'danger',
  })
  assert.equal(result.success, false)
  assert.match(result.message, /dangerous/)
})

test('Wave 3 executor returns null for unrelated actions', async () => {
  const result = await executeWave3VisualAction({
    action_id: 'wave2',
    action_type: 'drag_drop',
    target_selector: '#source',
    value: '{}',
  })
  assert.equal(result, null)
})
