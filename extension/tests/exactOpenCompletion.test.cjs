const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'exact-open-completion-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020', '--lib', 'ES2020,DOM', '--module', 'commonjs',
  '--moduleResolution', 'node', '--strict', '--skipLibCheck', '--outDir', outDir,
  path.join(root, 'src', 'execution', 'exact_open_completion.ts'),
], { cwd: root, stdio: 'pipe' })

const { exactOpenOnlyCompletion } = require(path.join(outDir, 'execution', 'exact_open_completion.js'))

const action = { action_type: 'click' }
const result = {
  success: true,
  adapter_trace: {
    exact_identity_verified: true,
    exact_target_kind: 'chat',
    exact_expected_name: 'Teja Spc',
    exact_observed_name: 'Teja Spc',
  },
}

test('verified exact chat completes an open-only task despite negative safety terms', () => {
  const completion = exactOpenOnlyCompletion(
    'Open WhatsApp and open the exact direct chat named Teja Spc. Do not type a message, attach a file, or send anything.',
    action,
    result,
  )
  assert.deepEqual(completion, { targetKind: 'chat', targetName: 'Teja Spc' })
})

test('affirmative downstream mutation prevents open-only completion', () => {
  assert.equal(exactOpenOnlyCompletion('Open chat Teja Spc and attach the approved file.', action, result), null)
})

test('unverified identity cannot complete the task', () => {
  assert.equal(exactOpenOnlyCompletion('Open chat Teja Spc.', action, { ...result, adapter_trace: { ...result.adapter_trace, exact_identity_verified: false } }), null)
})

test('canonical contract target plus verified exact click completes without optional adapter trace', () => {
  const completion = exactOpenOnlyCompletion(
    'Open WhatsApp and open the exact direct chat named Teja Spc. Do not send anything.',
    { action_type: 'click', description: 'Open the exact observed result visibly named Teja Spc', grounding: { semantic_kind: 'recipient' } },
    {
      success: true,
      contract_target_name: 'Teja Spc',
      contract_resource_url: 'https://web.whatsapp.com/',
      verification: { verified: true, signals: {
        exact_identity_verified: true, exact_target_kind: 'chat',
        exact_expected_name: 'Teja Spc', exact_observed_name: 'Teja Spc',
      } },
    },
  )
  assert.deepEqual(completion, { targetKind: 'chat', targetName: 'Teja Spc' })
})

test('generic click success and an exact-sounding description cannot replace identity evidence', () => {
  const completion = exactOpenOnlyCompletion(
    'Open WhatsApp and open the exact direct chat named Teja Spc. Do not type or send anything.',
    { action_type: 'click', description: 'Open the exact WhatsApp search result visibly named Teja Spc' },
    { success: true },
  )
  assert.equal(completion, null)
})
