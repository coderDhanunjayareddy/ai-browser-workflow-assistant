const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = path.join(root, '.tmp-service-worker-policy-test')

fs.rmSync(outDir, { recursive: true, force: true })
execFileSync(
  process.execPath,
  [
    path.join(root, 'node_modules/typescript/bin/tsc'),
    '--target', 'ES2020',
    '--lib', 'ES2020,DOM',
    '--module', 'commonjs',
    '--moduleResolution', 'node',
    '--strict',
    '--skipLibCheck',
    '--outDir', outDir,
    'src/background/service_worker_message_validation.ts',
    'src/background/live_policy_client.ts',
  ],
  { cwd: root, stdio: 'inherit' },
)

const {
  validateExecutableAction,
  validatePolicyContext,
  validateServiceWorkerMessage,
} = require(path.join(outDir, 'service_worker_message_validation.js'))
const { enforceLivePolicy } = require(path.join(outDir, 'live_policy_client.js'))

const runtimeId = 'extension-id'
const sender = { id: runtimeId, url: `chrome-extension://${runtimeId}/src/sidepanel/index.html`, hasTab: false }

function action(overrides = {}) {
  return {
    action_id: 'a-1',
    action_type: 'click',
    target_selector: '#continue',
    value: null,
    description: 'Click Continue',
    reasoning: 'Continue the task',
    safety_level: 'safe',
    ...overrides,
  }
}

function policyContext(overrides = {}) {
  return {
    session_id: 'session-1',
    provenance: [
      { source_type: 'user', source_id: 'task', trust: 'trusted', labels: ['direct_user_task'] },
      { source_type: 'planner', source_id: 'action:a-1', trust: 'untrusted', labels: ['model_proposed'] },
      { source_type: 'page', source_id: 'page:1', trust: 'untrusted', labels: ['page_observation'] },
    ],
    ...overrides,
  }
}

function executeMessage(overrides = {}) {
  return {
    type: 'EXECUTE_ACTION',
    tab_id: 1,
    action: action(),
    policy_context: policyContext(),
    ...overrides,
  }
}

test.after(() => fs.rmSync(outDir, { recursive: true, force: true }))

test('accepts a strictly bound internal execution message', () => {
  assert.equal(validateServiceWorkerMessage(executeMessage(), sender, runtimeId), null)
})

test('rejects privileged messages from content scripts or other extensions', () => {
  assert.match(validateServiceWorkerMessage(executeMessage(), { ...sender, hasTab: true }, runtimeId), /only from this extension UI/)
  assert.match(validateServiceWorkerMessage(executeMessage(), { ...sender, id: 'other-extension' }, runtimeId), /only from this extension UI/)
  assert.match(
    validateServiceWorkerMessage({ type: 'GET_TAB_WORKSPACE' }, { ...sender, hasTab: true }, runtimeId),
    /only from this extension UI/,
  )
})

test('requires complete user, planner, and page provenance', () => {
  assert.equal(validatePolicyContext(policyContext({ provenance: [] })), false)
  const missingUser = policyContext().provenance.filter((item) => item.source_type !== 'user')
  assert.equal(validatePolicyContext(policyContext({ provenance: missingUser })), false)
  assert.match(
    validateServiceWorkerMessage(executeMessage({ policy_context: policyContext({ provenance: missingUser }) }), sender, runtimeId),
    /invalid policy context/,
  )
})

test('rejects unsafe or malformed privileged URL arguments', () => {
  assert.equal(validateExecutableAction(action({ action_type: 'navigate', value: 'javascript:alert(1)' })), false)
  assert.equal(validateExecutableAction(action({ action_type: 'open_new_tab', value: 'chrome://extensions' })), false)
  assert.equal(validateExecutableAction(action({ action_type: 'navigate', value: 'https://example.com' })), true)
})

test('rejects malformed action fields and tab bindings', () => {
  assert.match(validateServiceWorkerMessage(executeMessage({ tab_id: -1 }), sender, runtimeId), /invalid tab binding/)
  assert.match(validateServiceWorkerMessage(executeMessage({ action: action({ action_id: '' }) }), sender, runtimeId), /invalid action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ action: action({ safety_level: 'trusted' }) }), sender, runtimeId), /invalid action contract/)
})

test('validates every non-execution message family and rejects unknown types', () => {
  assert.equal(validateServiceWorkerMessage({ type: 'EXTRACT_CONTEXT', tab_id: 2 }, sender, runtimeId), null)
  assert.match(validateServiceWorkerMessage({ type: 'EXTRACT_CONTEXT', tab_id: '2' }, sender, runtimeId), /invalid tab binding/)
  assert.equal(validateServiceWorkerMessage({ type: 'START_VOICE_CAPTURE', language: 'en-US' }, sender, runtimeId), null)
  assert.match(validateServiceWorkerMessage({ type: 'START_VOICE_CAPTURE', language: '../bad' }, sender, runtimeId), /invalid language/)
  assert.equal(validateServiceWorkerMessage({ type: 'WAIT_FOR_TAB_LOAD' }, sender, runtimeId), null)
  assert.equal(validateServiceWorkerMessage({ type: 'WAIT_FOR_DOM_SETTLE' }, sender, runtimeId), null)
  assert.equal(validateServiceWorkerMessage({ type: 'GET_TAB_WORKSPACE' }, sender, runtimeId), null)
  assert.match(validateServiceWorkerMessage({ type: 'RUN_SCRIPT' }, sender, runtimeId), /Unknown or malformed/)
})

test('malformed value fuzz corpus fails closed without throwing', () => {
  const corpus = [null, undefined, true, 1, '', [], {}, { type: null }, { type: 'EXECUTE_ACTION' }]
  for (const value of corpus) {
    const result = validateServiceWorkerMessage(value, sender, runtimeId)
    assert.equal(typeof result, 'string')
  }
})

test('live policy client fails closed on transport, HTTP, and malformed responses', async () => {
  const unavailable = await enforceLivePolicy('http://policy', action(), 'https://example.com', policyContext(), async () => {
    throw new Error('offline')
  })
  assert.equal(unavailable.allowed, false)
  assert.equal(unavailable.decision_reason, 'policy_engine_unavailable')

  const httpError = await enforceLivePolicy('http://policy', action(), 'https://example.com', policyContext(), async () => ({
    ok: false,
    status: 503,
  }))
  assert.equal(httpError.allowed, false)
  assert.equal(httpError.decision_reason, 'policy_engine_http_503')

  const malformed = await enforceLivePolicy('http://policy', action(), 'https://example.com', policyContext(), async () => ({
    ok: true,
    status: 200,
    json: async () => ({ allowed: true }),
  }))
  assert.equal(malformed.allowed, false)
  assert.equal(malformed.decision_reason, 'invalid_policy_engine_response')
})

test('live policy client forwards the exact action and narrow authority', async () => {
  let request
  const decision = await enforceLivePolicy(
    'http://policy',
    action({ action_id: 'pay-1', description: 'Place order' }),
    'https://shop.example/checkout',
    policyContext({ confirmation_receipt_id: 'receipt-1' }),
    async (url, init) => {
      request = { url, body: JSON.parse(init.body) }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          allowed: true,
          policy_decision: 'allow_with_confirmation',
          decision_reason: 'confirmed_action_allowed',
          decision_id: 'decision-1',
        }),
      }
    },
  )
  assert.equal(decision.allowed, true)
  assert.equal(request.url, 'http://policy/policy/enforce')
  assert.equal(request.body.action.action_id, 'pay-1')
  assert.equal(request.body.origin, 'https://shop.example/checkout')
  assert.equal(request.body.confirmation_receipt_id, 'receipt-1')
})
