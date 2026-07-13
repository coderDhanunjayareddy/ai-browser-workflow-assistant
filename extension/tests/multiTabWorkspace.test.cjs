const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'multi-tab-workspace-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--esModuleInterop',
  '--outDir', outDir,
  path.join(root, 'src', 'workspace', 'multiTabWorkspace.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  activateTab,
  createMultiTabWorkspace,
  registerTab,
  removeClosedTab,
  summarizeMultiTabWorkspace,
  updateTab,
  updateTabFactCount,
  updateTabPurpose,
} = require(path.join(outDir, 'multiTabWorkspace.js'))

function tab(id, overrides = {}) {
  return {
    id,
    windowId: overrides.windowId ?? 1,
    url: overrides.url ?? `https://example.test/page-${id}`,
    title: overrides.title ?? `Page ${id}`,
    active: overrides.active ?? false,
    status: overrides.status ?? 'complete',
  }
}

test('registers a new tab', () => {
  const workspace = registerTab(createMultiTabWorkspace(), tab(1, { title: 'Google Search', active: true }), 100)

  assert.equal(workspace.tabs.length, 1)
  assert.equal(workspace.tabs[0].tab_id, 1)
  assert.equal(workspace.tabs[0].title, 'Google Search')
  assert.equal(workspace.tabs[0].status, 'active')
  assert.equal(workspace.active_tab_id, 1)
})

test('activates one tab and marks previous active as visited', () => {
  let workspace = createMultiTabWorkspace()
  workspace = registerTab(workspace, tab(1, { title: 'Google Search', active: true }), 100)
  workspace = registerTab(workspace, tab(2, { title: 'Cursor Pricing' }), 101)
  workspace = activateTab(workspace, 2, 200)

  assert.equal(workspace.active_tab_id, 2)
  assert.equal(workspace.tabs.find((entry) => entry.tab_id === 2).status, 'active')
  assert.equal(workspace.tabs.find((entry) => entry.tab_id === 1).status, 'visited')
})

test('updates tab title and purpose', () => {
  let workspace = registerTab(createMultiTabWorkspace(), tab(1, { title: 'Loading' }), 100)
  workspace = updateTab(workspace, 1, { title: 'Cursor Pricing' }, 120)
  workspace = updateTabPurpose(workspace, 1, 'Collect Cursor pricing')

  assert.equal(workspace.tabs[0].title, 'Cursor Pricing')
  assert.equal(workspace.tabs[0].purpose, 'Collect Cursor pricing')
})

test('deduplicates tab ids', () => {
  let workspace = createMultiTabWorkspace()
  workspace = registerTab(workspace, tab(1, { title: 'Old' }), 100)
  workspace = registerTab(workspace, tab(1, { title: 'New' }), 110)

  assert.equal(workspace.tabs.length, 1)
  assert.equal(workspace.tabs[0].title, 'New')
})

test('removes closed tab', () => {
  let workspace = createMultiTabWorkspace()
  workspace = registerTab(workspace, tab(1), 100)
  workspace = registerTab(workspace, tab(2), 101)
  workspace = removeClosedTab(workspace, 1)

  assert.equal(workspace.tabs.length, 1)
  assert.equal(workspace.tabs[0].tab_id, 2)
})

test('generates compact summary without raw URLs', () => {
  let workspace = createMultiTabWorkspace()
  workspace = registerTab(workspace, tab(1, { title: 'Google Search', active: true, url: 'https://google.com/search?q=ai' }), 100)
  workspace = registerTab(workspace, tab(2, { title: 'Cursor Pricing', url: 'https://cursor.com/pricing' }), 101)
  workspace = updateTabFactCount(workspace, 2, 3)
  const summary = summarizeMultiTabWorkspace(workspace)

  assert.match(summary, /Tab Workspace/)
  assert.match(summary, /Active: Google Search/)
  assert.match(summary, /Cursor Pricing - visited, Facts: 3/)
  assert.doesNotMatch(summary, /https:\/\//)
})

test('active tab is preserved when bounded storage evicts old tabs', () => {
  let workspace = createMultiTabWorkspace()
  for (let index = 1; index <= 25; index++) {
    workspace = registerTab(workspace, tab(index, { title: `Page ${index}`, active: index === 25 }), index)
  }

  assert.equal(workspace.tabs.length, 20)
  assert.ok(workspace.tabs.some((entry) => entry.tab_id === 25 && entry.is_active))
})
