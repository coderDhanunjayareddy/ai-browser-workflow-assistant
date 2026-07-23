const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wave2-core-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'wave2_core.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  isWave2CoreAction,
  parseWave2Payload,
  executeWave2CoreAction,
} = require(path.join(outDir, 'wave2_core.js'))

test('Wave 2 core action routing is explicit', () => {
  assert.equal(isWave2CoreAction('monaco_edit'), true)
  assert.equal(isWave2CoreAction('codemirror_edit'), true)
  assert.equal(isWave2CoreAction('drag_drop'), true)
  assert.equal(isWave2CoreAction('virtual_list_find'), true)
  assert.equal(isWave2CoreAction('shadow_click'), true)
  assert.equal(isWave2CoreAction('infinite_scroll'), true)
  assert.equal(isWave2CoreAction('advanced_keyboard'), true)
  assert.equal(isWave2CoreAction('clipboard'), true)
  assert.equal(isWave2CoreAction('rich_text'), false)
})

test('Wave 2 payload parsing preserves JSON commands and plain text', () => {
  assert.deepEqual(parseWave2Payload('hello'), { text: 'hello' })
  assert.deepEqual(parseWave2Payload('{"text":"hello","mode":"append"}'), { text: 'hello', mode: 'append' })
  assert.deepEqual(parseWave2Payload(null), {})
})

test('Wave 2 executor refuses dangerous actions before DOM access', async () => {
  const result = await executeWave2CoreAction({
    action_id: 'danger-1',
    action_type: 'clipboard',
    target_selector: null,
    value: '{"operation":"paste","text":"nope"}',
    safety_level: 'danger',
  })
  assert.equal(result.success, false)
  assert.match(result.message, /dangerous/)
})

test('Wave 2 executor returns null for unrelated actions', async () => {
  const result = await executeWave2CoreAction({
    action_id: 'fill-1',
    action_type: 'fill',
    target_selector: '#name',
    value: 'Ada',
  })
  assert.equal(result, null)
})
