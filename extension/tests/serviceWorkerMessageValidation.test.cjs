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
} = require(path.join(outDir, 'background', 'service_worker_message_validation.js'))
const { enforceLivePolicy } = require(path.join(outDir, 'background', 'live_policy_client.js'))

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

function contract(actionOverrides = {}, overrides = {}) {
  const boundAction = action(actionOverrides)
  return {
    schema_version: '1.0',
    dispatch_id: 'dispatch-1',
    action: boundAction,
    target_identity: {
      kind: 'element',
      selector: boundAction.target_selector,
      selector_id: 'observed-continue',
      exact_name: 'Continue',
      role: 'button',
      semantic_kind: 'control',
    },
    grounding_policy: {
      ordered_sources: ['stable_selector', 'accessibility_name', 'verified_screenshot'],
      accessibility_requires_exact_name: true,
      screenshot_coordinates_verified: false,
      screenshot_hash: null,
    },
    origin: { origin: 'https://example.com', observed_url: 'https://example.com/workflow', target_url: null },
    browser_binding: { tab_id: 1, window_id: 2, frame_id: 'top' },
    resource_identity: { url: 'https://example.com/workflow', title: 'Workflow' },
    expected_effect: { kind: 'target_state_change', description: 'Continue opens the next step' },
    safety_class: boundAction.safety_level,
    idempotency_key: 'mission:1:a-1',
    ...overrides,
  }
}

function executeMessage(overrides = {}) {
  return {
    type: 'EXECUTE_ACTION',
    contract: contract(),
    policy_context: policyContext(),
    ...overrides,
  }
}

test.after(() => fs.rmSync(outDir, { recursive: true, force: true }))

test('accepts a strictly bound internal execution message', () => {
  assert.equal(validateServiceWorkerMessage(executeMessage(), sender, runtimeId), null)
})

test('accepts a canonical New Tab navigation with no element grounding', () => {
  const navigationAction = action({
    action_id: 'navigate-whatsapp',
    action_type: 'navigate',
    target_selector: '',
    value: 'https://web.whatsapp.com/',
    description: 'Open WhatsApp',
  })
  const navigationContract = contract(navigationAction, {
    action: navigationAction,
    target_identity: {
      kind: 'url', selector: '', selector_id: null, exact_name: null, role: null, semantic_kind: null,
    },
    origin: {
      origin: 'https://web.whatsapp.com',
      observed_url: 'chrome://newtab/',
      target_url: 'https://web.whatsapp.com/',
    },
    resource_identity: { url: 'https://web.whatsapp.com/', title: '' },
    expected_effect: { kind: 'url_change', description: 'Open WhatsApp' },
  })
  assert.equal(
    validateServiceWorkerMessage(
      { type: 'EXECUTE_ACTION', contract: navigationContract, policy_context: policyContext() },
      sender,
      runtimeId,
    ),
    null,
  )
})

test('rejects privileged messages from content scripts or other extensions', () => {
  assert.match(
    validateServiceWorkerMessage(executeMessage(), { ...sender, url: 'https://web.whatsapp.com/', hasTab: true }, runtimeId),
    /only from this extension UI/,
  )
  assert.match(validateServiceWorkerMessage(executeMessage(), { ...sender, id: 'other-extension' }, runtimeId), /only from this extension UI/)
  assert.match(
    validateServiceWorkerMessage({ type: 'GET_TAB_WORKSPACE' }, { ...sender, url: 'https://example.test/', hasTab: true }, runtimeId),
    /only from this extension UI/,
  )
})

test('accepts the same packaged extension UI when rendered in a validation tab', () => {
  const extensionTabSender = { ...sender, hasTab: true }
  assert.equal(validateServiceWorkerMessage(executeMessage(), extensionTabSender, runtimeId), null)
  assert.equal(validateServiceWorkerMessage({ type: 'GET_RUNTIME_IDENTITY' }, extensionTabSender, runtimeId), null)
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

test('content insertion declaration is typed and preserved inside the canonical action', () => {
  const insertion = {
    schema_version: 'content_insertion_request.v1',
    request_id: 'content-request-1',
    kind: 'document',
    expected_effect: 'preview_then_send',
    requires_bound_file: true,
    destination_entity: 'Synthetic Recipient',
    stage: 'select_bound_content',
    opens_native_chooser: true,
    requested_filename: 'synthetic-day5.txt',
  }
  assert.equal(validateExecutableAction(action({ content_insertion: insertion })), true)
  assert.equal(validateServiceWorkerMessage(executeMessage({ contract: contract({ content_insertion: insertion }) }), sender, runtimeId), null)
  assert.equal(validateExecutableAction(action({ content_insertion: { ...insertion, kind: 'unknown' } })), false)
  assert.equal(validateExecutableAction(action({ content_insertion: { ...insertion, opens_native_chooser: 'yes' } })), false)
  assert.equal(validateExecutableAction(action({ content_insertion: { ...insertion, requested_filename: '..\\secret.txt' } })), false)
})

test('consequential submission declaration binds destination and content identity', () => {
  const submission = {
    schema_version: 'consequential_submission.v1',
    submission_id: 'submission-1',
    operation: 'send',
    destination_entity: 'Consenting Test Recipient',
    content_identity: 'synthetic-day5.txt',
    preview_required: true,
    verification_mode: 'delivered_content_and_destination',
  }
  assert.equal(validateExecutableAction(action({ consequential_submission: submission })), true)
  assert.equal(validateServiceWorkerMessage(executeMessage({ contract: contract({ consequential_submission: submission }) }), sender, runtimeId), null)
  assert.equal(validateExecutableAction(action({ consequential_submission: { ...submission, destination_entity: '' } })), false)
  assert.equal(validateExecutableAction(action({ consequential_submission: { ...submission, operation: 'retry' } })), false)
  assert.equal(validateExecutableAction(action({ consequential_submission: { ...submission, preview_required: false } })), false)
})

test('rejects malformed action fields and tab bindings', () => {
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({}, { browser_binding: { tab_id: -1, window_id: 2, frame_id: 'top' } }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({ action_id: '' }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({ safety_level: 'trusted' }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({ grounding: { source: 'vision_region', bounding_box: { x: 1, y: 2, width: -1, height: 20 } } }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.equal(validateServiceWorkerMessage(executeMessage({ contract: contract({ grounding: { source: 'dom_snapshot', bounding_box: { x: 1, y: 2, width: 10, height: 20 } } }) }), sender, runtimeId), null)
})

test('canonical contract rejects target, origin, frame, safety, and resource identity drift', () => {
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({}, { target_identity: { ...contract().target_identity, selector: '#other' } }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({}, { origin: { origin: 'https://evil.example', observed_url: 'https://example.com/workflow' } }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({ grounding: { source: 'dom_snapshot', frame_id: 'child' } }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({}, { safety_class: 'danger' }) }), sender, runtimeId), /invalid canonical action contract/)
  assert.match(validateServiceWorkerMessage(executeMessage({ contract: contract({}, { resource_identity: { url: 'https://example.com/other', title: 'Other' } }) }), sender, runtimeId), /invalid canonical action contract/)
})

test('validates every non-execution message family and rejects unknown types', () => {
  assert.equal(validateServiceWorkerMessage({ type: 'EXTRACT_CONTEXT', tab_id: 2 }, sender, runtimeId), null)
  assert.match(validateServiceWorkerMessage({ type: 'EXTRACT_CONTEXT', tab_id: '2' }, sender, runtimeId), /invalid tab binding/)
  assert.equal(validateServiceWorkerMessage({ type: 'START_VOICE_CAPTURE', language: 'en-US' }, sender, runtimeId), null)
  assert.match(validateServiceWorkerMessage({ type: 'START_VOICE_CAPTURE', language: '../bad' }, sender, runtimeId), /invalid language/)
  assert.equal(validateServiceWorkerMessage({ type: 'WAIT_FOR_TAB_LOAD' }, sender, runtimeId), null)
  assert.equal(validateServiceWorkerMessage({ type: 'WAIT_FOR_DOM_SETTLE' }, sender, runtimeId), null)
  assert.equal(validateServiceWorkerMessage({ type: 'GET_TAB_WORKSPACE' }, sender, runtimeId), null)
  assert.equal(validateServiceWorkerMessage({ type: 'GET_RUNTIME_IDENTITY' }, sender, runtimeId), null)
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
  const unavailable = await enforceLivePolicy('http://policy', contract(), 'https://example.com', policyContext(), async () => {
    throw new Error('offline')
  })
  assert.equal(unavailable.allowed, false)
  assert.equal(unavailable.decision_reason, 'policy_engine_unavailable')

  const httpError = await enforceLivePolicy('http://policy', contract(), 'https://example.com', policyContext(), async () => ({
    ok: false,
    status: 503,
  }))
  assert.equal(httpError.allowed, false)
  assert.equal(httpError.decision_reason, 'policy_engine_http_503')

  const malformed = await enforceLivePolicy('http://policy', contract(), 'https://example.com', policyContext(), async () => ({
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
    contract({ action_id: 'pay-1', description: 'Place order' }),
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
  assert.equal(request.body.execution_contract.action.action_id, 'pay-1')
  assert.equal(request.body.execution_contract.idempotency_key, 'mission:1:a-1')
  assert.equal(request.body.origin, 'https://shop.example/checkout')
  assert.equal(request.body.confirmation_receipt_id, 'receipt-1')
})
