const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'action-verification-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'action_verification.ts'),
], { cwd: root, stdio: 'pipe' })

const { verifyActionEffect } = require(path.join(outDir, 'action_verification.js'))

function state(overrides = {}) {
  return {
    url: 'https://example.test/start',
    title: 'Example',
    domSignature: 'dom-a',
    visibleTextLength: 100,
    interactiveCount: 2,
    activeElementSignature: 'body',
    modalCount: 0,
    dialogCount: 0,
    expandedStates: [],
    checkboxStates: [],
    scrollX: 0,
    scrollY: 0,
    target: { exists: true, selector: '#target', tagName: 'button', visible: true },
    ...overrides,
  }
}

function action(action_type, value = null) {
  return {
    action_id: `${action_type}-1`,
    action_type,
    target_selector: '#target',
    value,
    description: `${action_type} target`,
  }
}

function result(action_type) {
  return { success: true, message: 'ok', action_id: `${action_type}-1` }
}

test('click is verified when page state changes', () => {
  const verification = verifyActionEffect(
    action('click'),
    result('click'),
    state(),
    state({ domSignature: 'dom-b', visibleTextLength: 120 }),
    23,
  )
  assert.equal(verification.verified, true)
  assert.equal(verification.reason, 'verified')
  assert.equal(verification.signals.dom_changed, true)
})

test('click reports no effect when state is unchanged', () => {
  const before = state()
  const verification = verifyActionEffect(action('click'), result('click'), before, state(), 12)
  assert.equal(verification.verified, false)
  assert.equal(verification.reason, 'no_effect')
})

test('fill is verified when value changes', () => {
  const verification = verifyActionEffect(
    action('fill', 'Ada'),
    result('fill'),
    state({ target: { exists: true, selector: '#target', tagName: 'input', inputType: 'text', value: '' } }),
    state({ target: { exists: true, selector: '#target', tagName: 'input', inputType: 'text', value: 'Ada' } }),
    18,
  )
  assert.equal(verification.verified, true)
  assert.equal(verification.reason, 'verified')
})

test('fill reports no effect when value is unchanged', () => {
  const unchanged = state({ target: { exists: true, selector: '#target', tagName: 'input', inputType: 'text', value: 'Ada' } })
  const verification = verifyActionEffect(action('fill', 'Grace'), result('fill'), unchanged, unchanged, 18)
  assert.equal(verification.verified, false)
  assert.equal(verification.reason, 'no_effect')
})

test('password fill verifies filled state without raw password value', () => {
  const verification = verifyActionEffect(
    action('fill', 'secret'),
    result('fill'),
    state({ target: { exists: true, selector: '#target', tagName: 'input', inputType: 'password', filled: false } }),
    state({ target: { exists: true, selector: '#target', tagName: 'input', inputType: 'password', filled: true } }),
    19,
  )
  assert.equal(verification.verified, true)
  assert.equal(verification.reason, 'verified')
  assert.equal(verification.after_state.target.value, undefined)
})

test('select_option is verified when selection changes', () => {
  const verification = verifyActionEffect(
    action('select_option', 'nyc'),
    result('select_option'),
    state({ target: { exists: true, selector: '#target', tagName: 'select', selectedValue: 'sf' } }),
    state({ target: { exists: true, selector: '#target', tagName: 'select', selectedValue: 'nyc' } }),
    15,
  )
  assert.equal(verification.verified, true)
})

test('select_option reports no effect when selection is unchanged', () => {
  const unchanged = state({ target: { exists: true, selector: '#target', tagName: 'select', selectedValue: 'sf' } })
  const verification = verifyActionEffect(action('select_option', 'nyc'), result('select_option'), unchanged, unchanged, 15)
  assert.equal(verification.verified, false)
  assert.equal(verification.reason, 'no_effect')
})

test('navigate is verified when URL changes', () => {
  const verification = verifyActionEffect(
    action('navigate', 'https://example.test/next'),
    result('navigate'),
    state({ url: 'https://example.test/start' }),
    state({ url: 'https://example.test/next', domSignature: 'dom-next' }),
    35,
  )
  assert.equal(verification.verified, true)
})

test('navigate reports no effect when URL is unchanged', () => {
  const before = state()
  const verification = verifyActionEffect(action('navigate', 'https://example.test/start'), result('navigate'), before, state(), 35)
  assert.equal(verification.verified, false)
  assert.equal(verification.reason, 'no_effect')
})

test('scroll is verified when scroll position changes', () => {
  const verification = verifyActionEffect(
    action('scroll', 'down'),
    result('scroll'),
    state({ scrollY: 0 }),
    state({ scrollY: 400 }),
    11,
  )
  assert.equal(verification.verified, true)
})

test('scroll reports no effect when scroll position is unchanged', () => {
  const before = state({ scrollY: 0 })
  const verification = verifyActionEffect(action('scroll', 'down'), result('scroll'), before, state({ scrollY: 0 }), 11)
  assert.equal(verification.verified, false)
  assert.equal(verification.reason, 'no_effect')
})

test('wait is verified when execution succeeds', () => {
  const before = state()
  const verification = verifyActionEffect(action('wait', '100'), result('wait'), before, state(), 101)
  assert.equal(verification.verified, true)
  assert.equal(verification.reason, 'verified')
  assert.equal(verification.signals.wait_completed, true)
})
