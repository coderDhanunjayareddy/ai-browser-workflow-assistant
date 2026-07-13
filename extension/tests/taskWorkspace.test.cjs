const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'task-workspace-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2022',
  '--lib', 'ES2022,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--esModuleInterop',
  '--outDir', outDir,
  path.join(root, 'src', 'sidepanel', 'taskWorkspace.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  createTaskWorkspace,
  updateTaskWorkspace,
  summarizeTaskWorkspace,
} = require(path.join(outDir, 'sidepanel', 'taskWorkspace.js'))

function pageContext(overrides = {}) {
  return {
    url: overrides.url ?? 'https://example.test/pricing#plans',
    title: overrides.title ?? 'Cursor Pricing',
    metadata: overrides.metadata ?? { description: 'AI editor plans' },
    interactive_elements: [],
    content_blocks: [],
    headings: overrides.headings ?? ['Free Plan', 'Pro Plan'],
    selected_text: '',
    visible_text: overrides.visible_text ?? 'Free Plan: Yes\nStarting Price: $15/month',
    images: [],
  }
}

function completed(description, success = true) {
  return {
    action: {
      action_id: description.toLowerCase().replace(/\s+/g, '-'),
      action_type: 'click',
      target_selector: '#target',
      value: null,
      description,
      reasoning: 'Test action',
      confidence: 0.9,
      safety_level: 'safe',
    },
    result: { success, message: 'ok', action_id: 'a1' },
  }
}

test('workspace creation stores goal and pending objectives', () => {
  const workspace = createTaskWorkspace('Open Cursor pricing and compare plans')

  assert.equal(workspace.goal, 'Open Cursor pricing and compare plans')
  assert.ok(workspace.pendingObjectives.length >= 1)
  assert.equal(workspace.completedObjectives.length, 0)
  assert.equal(workspace.currentTarget, workspace.goal)
})

test('workspace update persists extracted facts', () => {
  const workspace = updateTaskWorkspace(createTaskWorkspace('Compare pricing'), pageContext())

  assert.ok(workspace.extractedFacts.some((fact) => fact.label === 'Starting Price' && fact.value === '$15/month'))
  assert.ok(workspace.extractedFacts.some((fact) => fact.label === 'Price' && fact.value.startsWith('$15')))
})

test('successful action completes an objective', () => {
  const workspace = updateTaskWorkspace(
    createTaskWorkspace('Open Cursor pricing'),
    pageContext(),
    [completed('Open Cursor pricing')],
  )

  assert.ok(workspace.completedObjectives.includes('Open Cursor pricing'))
  assert.equal(workspace.pendingObjectives.includes('Open Cursor pricing'), false)
})

test('visited URLs are deduplicated without hash fragments', () => {
  let workspace = createTaskWorkspace('Research pricing')
  workspace = updateTaskWorkspace(workspace, pageContext({ url: 'https://example.test/pricing#plans' }))
  workspace = updateTaskWorkspace(workspace, pageContext({ url: 'https://example.test/pricing#faq' }))

  assert.deepEqual(workspace.visitedUrls, ['https://example.test/pricing'])
})

test('workspace storage is bounded', () => {
  let workspace = createTaskWorkspace('Long research')
  for (let index = 0; index < 40; index++) {
    workspace = updateTaskWorkspace(
      workspace,
      pageContext({
        url: `https://example.test/page-${index}`,
        title: `Tool ${index} Pricing`,
        headings: [`Feature ${index}`],
        visible_text: `Fact ${index}: Value ${index}\nPrice: $${index}/month`,
      }),
      [completed(`Visit page ${index}`)],
    )
  }

  assert.equal(workspace.visitedUrls.length, 25)
  assert.equal(workspace.extractedFacts.length, 25)
  assert.equal(workspace.completedObjectives.length, 20)
  assert.ok(workspace.namedEntities.length <= 25)
})

test('workspace summary is compact and structured', () => {
  const workspace = updateTaskWorkspace(
    createTaskWorkspace('Compare Cursor and Windsurf pricing'),
    pageContext(),
    [completed('Open Cursor pricing')],
  )
  const summary = summarizeTaskWorkspace(workspace)

  assert.match(summary, /Workspace Summary/)
  assert.match(summary, /Goal: Compare Cursor and Windsurf pricing/)
  assert.match(summary, /Completed:/)
  assert.match(summary, /Visited: 1 pages/)
  assert.match(summary, /Facts:/)
  assert.ok(summary.length <= 1600)
})
