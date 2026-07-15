const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'tab-control-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'background', 'tab_control.ts'),
  path.join(root, 'src', 'workspace', 'multiTabWorkspace.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  canCloseTab,
  findTabEntryByReference,
  isTabControlAction,
  normalizeOpenTabUrl,
  parseTabReference,
} = require(path.join(outDir, 'background', 'tab_control.js'))
const {
  activateTab,
  createMultiTabWorkspace,
  registerTab,
  updateTabPurpose,
} = require(path.join(outDir, 'workspace', 'multiTabWorkspace.js'))

function action(action_type, value = null) {
  return {
    action_id: `${action_type}-1`,
    action_type,
    target_selector: null,
    value,
    description: `${action_type} ${value || ''}`,
  }
}

function workspace() {
  let state = createMultiTabWorkspace()
  state = registerTab(state, { id: 1, windowId: 1, title: 'Google Search', url: 'https://google.com/search', active: true }, 100)
  state = registerTab(state, { id: 2, windowId: 1, title: 'Cursor Pricing', url: 'https://cursor.com/pricing', active: false }, 110)
  state = updateTabPurpose(state, 2, 'Collect pricing')
  return state
}

test('open_new_tab is recognized and requires explicit safe URL', () => {
  assert.equal(isTabControlAction(action('open_new_tab', 'https://example.test')), true)
  assert.equal(normalizeOpenTabUrl('https://example.test'), 'https://example.test')
  assert.equal(normalizeOpenTabUrl('chrome://settings'), null)
  assert.equal(normalizeOpenTabUrl('example.test'), null)
})

test('switch by explicit id parses and matches workspace', () => {
  const ref = parseTabReference(action('switch_tab', 'tab:2'))
  const match = findTabEntryByReference(workspace(), ref)

  assert.equal(ref.kind, 'id')
  assert.equal(match.tab_id, 2)
  assert.equal(match.title, 'Cursor Pricing')
})

test('switch by explicit title parses and matches workspace', () => {
  const ref = parseTabReference(action('switch_tab', 'title:Cursor Pricing'))
  const match = findTabEntryByReference(workspace(), ref)

  assert.equal(ref.kind, 'title')
  assert.equal(match.tab_id, 2)
})

test('switch by explicit purpose parses and matches workspace', () => {
  const ref = parseTabReference(action('switch_tab', 'purpose:Collect pricing'))
  const match = findTabEntryByReference(workspace(), ref)

  assert.equal(ref.kind, 'purpose')
  assert.equal(match.tab_id, 2)
})

test('focus existing active tab preserves active workspace identity', () => {
  const state = activateTab(workspace(), 2, 200)

  assert.equal(state.active_tab_id, 2)
  assert.equal(state.tabs.find((tab) => tab.tab_id === 2).is_active, true)
  assert.equal(state.tabs.find((tab) => tab.tab_id === 1).status, 'visited')
})

test('close allowed tab passes safety checks', () => {
  const decision = canCloseTab({ id: 2, url: 'https://cursor.com/pricing', pinned: false }, 3)

  assert.equal(decision.allowed, true)
  assert.equal(decision.reason, 'allowed')
})

test('close refuses pinned, restricted, and final tabs', () => {
  assert.equal(canCloseTab({ id: 2, url: 'https://example.test', pinned: true }, 3).reason, 'refused_pinned_tab')
  assert.equal(canCloseTab({ id: 2, url: 'chrome://settings', pinned: false }, 3).reason, 'refused_restricted_tab')
  assert.equal(canCloseTab({ id: 2, url: 'https://example.test', pinned: false }, 1).reason, 'refused_last_tab')
})

test('unknown tab operation is ignored by tab controller', () => {
  assert.equal(isTabControlAction(action('click', '#target')), false)
})
