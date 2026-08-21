const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = path.join(root, '.tmp-consequential-ledger-test')

fs.rmSync(outDir, { recursive: true, force: true })
execFileSync(process.execPath, [
  path.join(root, 'node_modules/typescript/bin/tsc'),
  '--target', 'ES2020', '--lib', 'ES2020,DOM', '--types', 'chrome',
  '--module', 'commonjs', '--moduleResolution', 'node', '--strict', '--skipLibCheck',
  '--outDir', outDir, 'src/background/consequential_submission_ledger.ts',
], { cwd: root, stdio: 'inherit' })

const { ConsequentialSubmissionLedger, SUBMISSION_LEDGER_KEY } = require(
  path.join(outDir, 'background', 'consequential_submission_ledger.js'),
)

function declaration(overrides = {}) {
  return {
    schema_version: 'consequential_submission.v1', submission_id: 'submission-1', operation: 'send',
    destination_entity: 'Consenting Test Recipient', content_identity: 'synthetic-day5.txt',
    preview_required: true, verification_mode: 'delivered_content_and_destination', ...overrides,
  }
}

function contract() {
  return { idempotency_key: 'mission:1:submission:submission-1', origin: { origin: 'https://example.test' } }
}

function storage() {
  const state = {}
  return {
    state,
    async get(key) { return { [key]: structuredClone(state[key] || {}) } },
    async set(items) { Object.assign(state, structuredClone(items)) },
  }
}

test.after(() => fs.rmSync(outDir, { recursive: true, force: true }))

test('concurrent reservations permit exactly one mutation attempt', async () => {
  const store = storage()
  const ledger = new ConsequentialSubmissionLedger(store)
  const results = await Promise.all(Array.from({ length: 20 }, () => ledger.reserve(contract(), declaration(), 100)))
  assert.equal(results.filter((result) => result.allowed).length, 1)
  assert.equal(results.filter((result) => !result.allowed && result.reason === 'uncertain_prior_dispatch').length, 19)
  assert.equal(store.state[SUBMISSION_LEDGER_KEY]['submission-1'].attempts, 1)
})

test('delivered and uncertain records both fail closed on replay', async () => {
  for (const state of ['delivered', 'uncertain']) {
    const store = storage()
    const ledger = new ConsequentialSubmissionLedger(store)
    assert.equal((await ledger.reserve(contract(), declaration(), 100)).allowed, true)
    await ledger.settle('submission-1', state, 101)
    const replay = await ledger.reserve(contract(), declaration(), 102)
    assert.equal(replay.allowed, false)
    assert.equal(replay.reason, state === 'delivered' ? 'already_delivered' : 'uncertain_prior_dispatch')
  }
})

test('a reused submission id cannot be rebound to a different destination', async () => {
  const store = storage()
  const ledger = new ConsequentialSubmissionLedger(store)
  await ledger.reserve(contract(), declaration(), 100)
  const drifted = await ledger.reserve(contract(), declaration({ destination_entity: 'Wrong Recipient' }), 101)
  assert.equal(drifted.allowed, false)
  assert.equal(drifted.reason, 'uncertain_prior_dispatch')
})
