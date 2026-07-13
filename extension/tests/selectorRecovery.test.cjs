const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'selector-recovery-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'selector_recovery.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  chooseRecoveryCandidate,
  shouldAttemptSelectorRecovery,
} = require(path.join(outDir, 'selector_recovery.js'))

function action(action_type, description, target_selector = '#stale', value = null, safety_level = 'safe') {
  return {
    action_id: `${action_type}-1`,
    action_type,
    target_selector,
    value,
    description,
    safety_level,
  }
}

function candidate(selector, source, text, action_types = ['click'], visible = true) {
  return { selector, source, text, visible, action_types }
}

const successResult = { success: true, message: 'ok', action_id: 'a1' }
const noEffect = {
  verified: false,
  reason: 'no_effect',
  before_state: {},
  after_state: {},
  signals: {},
}

test('click recovers by aria-label', () => {
  const choice = chooseRecoveryCandidate(action('click', 'Open search'), [
    candidate('#stale', 'same_selector', 'old target'),
    candidate('button[aria-label="Search"]', 'aria_label', 'Search'),
  ])
  assert.equal(choice.selector, 'button[aria-label="Search"]')
  assert.equal(choice.source, 'aria_label')
})

test('click recovers by button text', () => {
  const choice = chooseRecoveryCandidate(action('click', 'Click Continue'), [
    candidate('main > button:nth-of-type(2)', 'button_text', 'Continue'),
  ])
  assert.equal(choice.selector, 'main > button:nth-of-type(2)')
  assert.equal(choice.source, 'button_text')
})

test('recovery fails when no relevant visible candidate exists', () => {
  const choice = chooseRecoveryCandidate(action('click', 'Open filters'), [
    candidate('button[aria-label="Delete"]', 'aria_label', 'Delete'),
    candidate('button[aria-label="Filters"]', 'aria_label', 'Filters', ['click'], false),
  ])
  assert.equal(choice, null)
})

test('recovery is attempted only once', () => {
  assert.equal(shouldAttemptSelectorRecovery(action('click', 'Open filters'), successResult, noEffect, false), true)
  assert.equal(shouldAttemptSelectorRecovery(action('click', 'Open filters'), successResult, noEffect, true), false)
})

test('fill recovers with an alternate labelled selector', () => {
  const choice = chooseRecoveryCandidate(action('fill', 'Fill Email', '#old-email', 'ada@example.test'), [
    candidate('input[name="email"]', 'associated_label', 'Email', ['fill']),
  ])
  assert.equal(choice.selector, 'input[name="email"]')
  assert.equal(choice.source, 'associated_label')
})

test('fill recovery fails when alternate selector is unrelated', () => {
  const choice = chooseRecoveryCandidate(action('fill', 'Fill Email', '#old-email', 'ada@example.test'), [
    candidate('input[name="phone"]', 'associated_label', 'Phone', ['fill']),
  ])
  assert.equal(choice, null)
})

test('select_option recovers with an alternate selector', () => {
  const choice = chooseRecoveryCandidate(action('select_option', 'Choose State', '#old-state', 'California'), [
    candidate('select[name="state"]', 'associated_label', 'State', ['select_option']),
  ])
  assert.equal(choice.selector, 'select[name="state"]')
  assert.equal(choice.source, 'associated_label')
})

test('destructive actions never retry', () => {
  assert.equal(
    shouldAttemptSelectorRecovery(action('click', 'Delete this account', '#delete', null, 'safe'), successResult, noEffect, false),
    false,
  )
  assert.equal(
    shouldAttemptSelectorRecovery(action('click', 'Open menu', '#menu', null, 'danger'), successResult, noEffect, false),
    false,
  )
})

test('unsupported actions do not trigger selector recovery', () => {
  assert.equal(shouldAttemptSelectorRecovery(action('navigate', 'Go to docs'), successResult, noEffect, false), false)
  assert.equal(shouldAttemptSelectorRecovery(action('scroll', 'Scroll down'), successResult, noEffect, false), false)
  assert.equal(shouldAttemptSelectorRecovery(action('wait', 'Wait'), successResult, noEffect, false), false)
})
