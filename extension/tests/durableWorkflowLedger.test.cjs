const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = path.join(root, '.tmp-durable-ledger-test')

fs.rmSync(outDir, { recursive: true, force: true })
execFileSync(process.execPath, [
  path.join(root, 'node_modules/typescript/bin/tsc'),
  '--target', 'ES2020', '--lib', 'ES2020,DOM,DOM.Iterable', '--types', 'chrome',
  '--module', 'commonjs', '--moduleResolution', 'node', '--strict', '--skipLibCheck',
  '--outDir', outDir, 'src/sidepanel/durableWorkflowLedger.ts',
], { cwd: root, stdio: 'inherit' })

const ledgerApi = require(path.join(outDir, 'sidepanel', 'durableWorkflowLedger.js'))

function workflow(overrides = {}) {
  return {
    sessionId: 'mission-1', task: 'Collect two facts', analysisText: '',
    pendingActions: [], activeAction: null, completedActions: [], validationPriorSteps: [],
    workspace: null, tabWorkspace: null, missionSnapshot: null, userInputs: [],
    clarificationQuestion: null, contractOutcome: null, report: null, replan: null,
    goalConvergence: false, phase: 'awaiting_execution', error: null, ...overrides,
  }
}

function action(overrides = {}) {
  return {
    action_id: 'action-1', intent_id: 'intent-1', mission_id: 'mission-1',
    action_type: 'fill', target_selector: '#query', value: 'browser agents',
    description: 'Fill search query', reasoning: 'Needed for research',
    confidence: 0.9, safety_level: 'safe', ...overrides,
  }
}

test.after(() => fs.rmSync(outDir, { recursive: true, force: true }))

test('checkpoint consolidates workflow and approval state in one ledger', () => {
  const pending = action()
  const state = workflow({ pendingActions: [pending] })
  const ledger = ledgerApi.createDurableLedger(state, 100)
  assert.equal(ledger.workflow.task, state.task)
  assert.equal(ledger.approval.status, 'awaiting_user')
  assert.equal(ledger.approval.actionId, pending.action_id)
})

test('completed execution is idempotent and cannot dispatch twice', () => {
  let ledger = ledgerApi.createDurableLedger(workflow(), 100)
  const first = ledgerApi.reserveDurableExecution(ledger, action(), 7, 'auto', 101)
  assert.equal(first.accepted, true)
  ledger = ledgerApi.completeDurableExecution(first.ledger, first.record.key, {
    success: true, message: 'filled', action_id: 'action-1',
  }, 102)
  const duplicate = ledgerApi.reserveDurableExecution(ledger, action(), 7, 'auto', 103)
  assert.equal(duplicate.accepted, false)
  assert.equal(duplicate.reason, 'already_succeeded')
})

test('restart marks an in-flight action uncertain and pauses instead of replaying it', () => {
  const executing = workflow({ phase: 'executing', activeAction: action() })
  const ledger = ledgerApi.createDurableLedger(executing, 100)
  const reserved = ledgerApi.reserveDurableExecution(ledger, action(), 7, 'manual', 101)
  const restored = ledgerApi.normalizeLedgerAfterRestart(reserved.ledger, 102)
  assert.equal(restored.executions[reserved.record.key].status, 'uncertain')
  assert.equal(restored.workflow.phase, 'failed')
  assert.match(restored.workflow.error, /will not be repeated/i)
})

test('automatic retries are bounded and limited to low-risk reversible actions', () => {
  assert.equal(ledgerApi.isLowRiskReversibleAction(action()), true)
  assert.equal(ledgerApi.isLowRiskReversibleAction(action({ action_type: 'click' })), false)
  assert.equal(ledgerApi.isLowRiskReversibleAction(action({ safety_level: 'caution' })), false)

  let ledger = ledgerApi.createDurableLedger(workflow(), 100)
  const first = ledgerApi.reserveDurableExecution(ledger, action(), 7, 'auto', 101)
  ledger = ledgerApi.completeDurableExecution(first.ledger, first.record.key, {
    success: false, message: 'temporary failure', action_id: 'action-1',
  }, 102)
  const second = ledgerApi.reserveDurableExecution(ledger, action(), 7, 'auto', 103)
  assert.equal(second.accepted, true)
  ledger = ledgerApi.completeDurableExecution(second.ledger, second.record.key, {
    success: false, message: 'still failed', action_id: 'action-1',
  }, 104)
  const third = ledgerApi.reserveDurableExecution(ledger, action(), 7, 'auto', 105)
  assert.equal(third.accepted, false)
  assert.equal(third.reason, 'attempt_limit')
})

test('completion requires SGV or a durable mission result', () => {
  assert.equal(ledgerApi.completionEvidenceValid({}), false)
  assert.equal(ledgerApi.completionEvidenceValid({ sgvVerified: true }), true)
  assert.equal(ledgerApi.completionEvidenceValid({ missionResultAvailable: true }), true)
})

test('long awaiting workflow survives a serialized extension restart with verified history intact', () => {
  const completedActions = Array.from({ length: 12 }, (_, index) => ({
    action: action({ action_id: `done-${index}`, intent_id: `done-intent-${index}` }),
    result: { success: true, message: 'verified', action_id: `done-${index}` },
  }))
  const pending = action({ action_id: 'next-action', intent_id: 'next-intent' })
  const before = workflow({ completedActions, pendingActions: [pending] })
  const serialized = JSON.stringify(ledgerApi.createDurableLedger(before, 100))
  const restored = ledgerApi.normalizeLedgerAfterRestart(JSON.parse(serialized), 200)
  assert.equal(restored.workflow.phase, 'awaiting_execution')
  assert.equal(restored.workflow.completedActions.length, 12)
  assert.equal(restored.workflow.pendingActions[0].action_id, 'next-action')
  assert.equal(restored.approval.status, 'none')
})
