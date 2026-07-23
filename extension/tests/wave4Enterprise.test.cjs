const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wave4-enterprise-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'content', 'wave4_enterprise.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  isWave4EnterpriseAction,
  parseWave4Payload,
  executeWave4EnterpriseAction,
} = require(path.join(outDir, 'wave4_enterprise.js'))

test('Wave 4 enterprise action routing is explicit', () => {
  for (const action of [
    'google_workspace_adapter',
    'microsoft365_adapter',
    'github_advanced_adapter',
    'jira_adapter',
    'confluence_adapter',
    'slack_adapter',
    'notion_adapter',
    'figma_adapter',
    'canva_adapter',
    'salesforce_adapter',
    'sso_auth',
    'mfa_otp_handoff',
    'enterprise_file_workflow',
    'site_optimize',
  ]) {
    assert.equal(isWave4EnterpriseAction(action), true)
  }
  assert.equal(isWave4EnterpriseAction('visual_region'), false)
})

test('Wave 4 payload parsing preserves JSON and plain text', () => {
  assert.deepEqual(parseWave4Payload('hello'), { text: 'hello' })
  assert.deepEqual(parseWave4Payload('{"adapter":"slack"}'), { adapter: 'slack' })
  assert.deepEqual(parseWave4Payload(null), {})
})

test('Wave 4 executor refuses dangerous actions before DOM access', async () => {
  const result = await executeWave4EnterpriseAction({
    action_id: 'danger-enterprise',
    action_type: 'slack_adapter',
    target_selector: null,
    value: '{}',
    safety_level: 'danger',
  })
  assert.equal(result.success, false)
  assert.match(result.message, /dangerous/)
})

test('Wave 4 executor returns null for unrelated actions', async () => {
  const result = await executeWave4EnterpriseAction({
    action_id: 'wave3',
    action_type: 'canvas_action',
    target_selector: '#canvas',
    value: '{}',
  })
  assert.equal(result, null)
})
