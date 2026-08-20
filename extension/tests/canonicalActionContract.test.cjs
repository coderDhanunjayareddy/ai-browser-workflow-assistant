const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'canonical-action-contract-'))

execFileSync(process.execPath, [
  path.join(root, 'node_modules', 'typescript', 'bin', 'tsc'),
  '--target', 'ES2020',
  '--lib', 'ES2020,DOM',
  '--module', 'commonjs',
  '--moduleResolution', 'node',
  '--strict',
  '--skipLibCheck',
  '--outDir', outDir,
  path.join(root, 'src', 'execution', 'canonical_action_contract.ts'),
], { cwd: root, stdio: 'pipe' })

const {
  attachCanonicalContractEvidence,
  buildCanonicalActionContract,
} = require(path.join(outDir, 'execution', 'canonical_action_contract.js'))

function clickAction(overrides = {}) {
  return {
    action_id: 'click-1',
    action_type: 'click',
    target_selector: 'span[title="Teja Spc"]',
    value: null,
    description: 'Open exact recipient Teja Spc',
    reasoning: 'The user named this exact recipient',
    confidence: 0.99,
    safety_level: 'safe',
    grounding: {
      source: 'dom_snapshot',
      selector_id: 'recipient:teja-spc',
      frame_id: 'top',
      accessibility_name: 'Teja Spc',
      role: 'listitem',
      semantic_kind: 'recipient',
    },
    ...overrides,
  }
}

const context = {
  tab_id: 7,
  window_id: 3,
  url: 'https://web.whatsapp.com/',
  title: 'WhatsApp',
  metadata: {},
  interactive_elements: [],
  content_blocks: [],
  headings: [],
  selected_text: '',
  visible_text: '',
  images: [],
}

test.after(() => fs.rmSync(outDir, { recursive: true, force: true }))

test('contract preserves exact recipient, selector, resource, tab, frame, safety, and idempotency identity', () => {
  const contract = buildCanonicalActionContract(clickAction(), context, 'mission-1:7:click-1')
  assert.equal(contract.schema_version, '1.0')
  assert.equal(contract.target_identity.exact_name, 'Teja Spc')
  assert.equal(contract.target_identity.selector, 'span[title="Teja Spc"]')
  assert.equal(contract.target_identity.selector_id, 'recipient:teja-spc')
  assert.equal(contract.target_identity.semantic_kind, 'recipient')
  assert.equal(contract.origin.origin, 'https://web.whatsapp.com')
  assert.equal(contract.origin.target_url, null)
  assert.equal(contract.browser_binding.tab_id, 7)
  assert.equal(contract.browser_binding.frame_id, 'top')
  assert.equal(contract.resource_identity.url, context.url)
  assert.equal(contract.safety_class, 'safe')
  assert.equal(contract.expected_effect.kind, 'target_state_change')
  assert.equal(contract.idempotency_key, 'mission-1:7:click-1')
})

test('contract fails closed for an ungrounded click, invalid origin, or missing idempotency key', () => {
  assert.throws(
    () => buildCanonicalActionContract(clickAction({ target_selector: '', grounding: undefined }), context, 'key'),
    /exact observed selector/,
  )
  assert.throws(() => buildCanonicalActionContract(clickAction(), { ...context, url: 'chrome://settings' }, 'key'), /non-http\/https/)
  assert.throws(() => buildCanonicalActionContract(clickAction(), context, ''), /idempotency key/)
})

test('navigation-result click preserves its exact URL postcondition', () => {
  const contract = buildCanonicalActionContract(clickAction({
    grounding: {
      source: 'dom_snapshot',
      accessibility_name: 'Telugu music result',
      role: 'link',
      semantic_kind: 'navigation_result',
      expected_url_path: '/watch',
    },
  }), context, 'media-result-key')
  assert.equal(contract.expected_effect.kind, 'url_change')
  assert.equal(contract.expected_effect.url_path, '/watch')
})

test('explicit navigation can bootstrap from New Tab but not another privileged page', () => {
  const navigate = clickAction({
    action_id: 'navigate-1', action_type: 'navigate', target_selector: '', grounding: {},
    value: 'https://web.whatsapp.com/', description: 'Open WhatsApp',
  })
  const bootstrap = buildCanonicalActionContract(navigate, { ...context, url: 'chrome://newtab/', title: 'New Tab' }, 'nav-key')
  assert.equal(bootstrap.origin.observed_url, 'chrome://newtab/')
  assert.equal(bootstrap.origin.target_url, 'https://web.whatsapp.com/')
  assert.equal(bootstrap.origin.origin, 'https://web.whatsapp.com')
  assert.equal(bootstrap.resource_identity.url, 'https://web.whatsapp.com/')
  assert.equal(bootstrap.action.target_selector, '')
  assert.equal(bootstrap.target_identity.selector, '')
  assert.equal(bootstrap.action.grounding, undefined)
  assert.throws(() => buildCanonicalActionContract(navigate, { ...context, url: 'chrome://settings/' }, 'nav-key'), /privileged source/)
})

test('dispatch result exposes the one canonical path and immutable contract identity', () => {
  const contract = buildCanonicalActionContract(clickAction(), context, 'mission-1:7:click-1')
  const result = attachCanonicalContractEvidence(
    { success: true, adapter_trace: { cdp_attempted: true } },
    contract,
    'service_worker>policy>canonical_cdp_click',
  )
  assert.equal(result.dispatch_path, 'service_worker>policy>canonical_cdp_click')
  assert.equal(result.contract_target_name, 'Teja Spc')
  assert.equal(result.contract_resource_url, 'https://web.whatsapp.com/')
  assert.equal(result.contract_idempotency_key, 'mission-1:7:click-1')
  assert.equal(result.adapter_trace.target_selector_preserved, true)
  assert.equal(result.adapter_trace.expected_effect, 'target_state_change')
})

test('production service worker has one click mutation route and no selector-recovery dispatch for click', () => {
  const worker = fs.readFileSync(path.join(root, 'src', 'background', 'service-worker.ts'), 'utf8')
  const clickBranch = worker.match(/if \(action\.action_type === 'click'\) \{[\s\S]*?\n    \}/)?.[0] || ''
  assert.match(clickBranch, /cdpController\.execute/)
  assert.doesNotMatch(clickBranch, /executeAction|executeActionV2|findRecoverySelector|\.click\(/)
  assert.match(worker, /Click rejected outside the canonical CDP dispatch path/)
})

test('production service worker dispatches keyboard shortcuts through trusted CDP input', () => {
  const worker = fs.readFileSync(path.join(root, 'src', 'background', 'service-worker.ts'), 'utf8')
  const keyboardBranch = worker.match(/if \(action\.action_type === 'keyboard_shortcut'\) \{[\s\S]*?\n    \}/)?.[0] || ''
  assert.match(keyboardBranch, /cdpController\.execute/)
  assert.match(worker, /service_worker>policy>canonical_cdp_keyboard/)
})

test('navigation waits for redirect chains to settle before verification or a dependent action', () => {
  const worker = fs.readFileSync(path.join(root, 'src', 'background', 'service-worker.ts'), 'utf8')
  assert.match(worker, /await waitForTabNavigationSettle\(tab\.id, tabUrl\)/)
  assert.match(worker, /stableSamples >= 6/)
})

test('open-new-tab validates the exact source tab separately from the destination origin', () => {
  const worker = fs.readFileSync(path.join(root, 'src/background/service-worker.ts'), 'utf8')
  assert.match(worker, /!\['navigate', 'open_new_tab'\]\.includes\(action\.action_type\)/)
})
