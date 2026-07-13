const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const root = path.resolve(__dirname, '..')
const outDir = path.join(root, '.tmp-router-test')

function compileRouter() {
  fs.rmSync(outDir, { recursive: true, force: true })
  execFileSync(
    process.execPath,
    [
      path.join(root, 'node_modules/typescript/bin/tsc'),
      '--target',
      'ES2020',
      '--lib',
      'ES2020,DOM,DOM.Iterable',
      '--module',
      'commonjs',
      '--moduleResolution',
      'node',
      '--jsx',
      'react-jsx',
      '--strict',
      '--skipLibCheck',
      '--esModuleInterop',
      '--outDir',
      outDir,
      'src/sidepanel/hooks/useWorkflow.ts',
    ],
    { cwd: root, stdio: 'inherit' },
  )
}

compileRouter()
const {
  buildAnalyzeRequestBody,
  cancelWorkflowPatch,
  createMultiTabWorkspace,
  createTaskWorkspace,
  registerTab,
  routeAnalyzeOutcome,
  updateTabFactCount,
  updateTaskWorkspace,
  workflowLoopObservationPhase,
} = require(path.join(outDir, 'sidepanel/hooks/useWorkflow.js'))

test.after(() => {
  fs.rmSync(outDir, { recursive: true, force: true })
})

function action(overrides = {}) {
  return {
    action_id: overrides.action_id ?? 'a1',
    action_type: overrides.action_type ?? 'click',
    target_selector: overrides.target_selector ?? '#submit',
    value: overrides.value ?? null,
    description: overrides.description ?? 'Click submit',
    reasoning: overrides.reasoning ?? 'The button advances the workflow.',
    confidence: overrides.confidence ?? 0.9,
    safety_level: overrides.safety_level ?? 'safe',
  }
}

function response(overrides = {}) {
  return {
    session_id: 'session-1',
    analysis: 'Planner analysis',
    suggested_actions: [],
    ...overrides,
  }
}

function pageContext(overrides = {}) {
  return {
    url: overrides.url ?? 'https://example.test',
    title: overrides.title ?? 'Example',
    metadata: overrides.metadata ?? {},
    interactive_elements: overrides.interactive_elements ?? [],
    content_blocks: overrides.content_blocks ?? [],
    headings: overrides.headings ?? [],
    selected_text: overrides.selected_text ?? '',
    visible_text: overrides.visible_text ?? 'Visible page text',
    images: overrides.images ?? [],
  }
}

function completedAction(overrides = {}) {
  return {
    action: action(overrides.action ?? {}),
    result: overrides.result ?? {
      success: true,
      message: 'Clicked search',
      action_id: 'a1',
    },
    analysis_snapshot: overrides.analysis_snapshot ?? 'Initial analysis',
    page_snapshot: overrides.page_snapshot ?? {
      url: 'https://example.test/search',
      title: 'Search',
      metadata: {},
    },
  }
}

function route(result) {
  return routeAnalyzeOutcome(result, {
    completedActions: [],
    currentUrl: 'https://example.test',
    userInputs: [],
  })
}

test('routes act outcomes through the existing action path', () => {
  const routed = route(response({
    outcome_kind: 'act',
    suggested_actions: [action()],
    goal_convergence: true,
  }))

  assert.equal(routed.phase, 'awaiting_execution')
  assert.equal(routed.contractOutcome, 'act')
  assert.equal(routed.pendingActions.length, 1)
  assert.equal(routed.pendingActions[0].action_type, 'click')
  assert.equal(routed.goalConvergence, true)
  assert.equal(routed.report, null)
  assert.equal(routed.replan, null)
})

test('routes wait outcomes through the existing wait action path', () => {
  const routed = route(response({
    outcome_kind: 'wait',
    suggested_actions: [action({
      action_type: 'wait',
      target_selector: '',
      description: 'Wait for the page to settle',
    })],
  }))

  assert.equal(routed.phase, 'awaiting_execution')
  assert.equal(routed.contractOutcome, 'wait')
  assert.equal(routed.pendingActions.length, 1)
  assert.equal(routed.pendingActions[0].action_type, 'wait')
})

test('routes ask outcomes to clarification without actions', () => {
  const routed = route(response({
    outcome_kind: 'ask',
    clarification_question: 'Which account should I use?',
    suggested_actions: [action()],
  }))

  assert.equal(routed.phase, 'awaiting_user')
  assert.equal(routed.contractOutcome, 'ask')
  assert.equal(routed.clarificationQuestion, 'Which account should I use?')
  assert.deepEqual(routed.pendingActions, [])
})

test('routes unverified report outcomes to reported phase (sgv_verified absent)', () => {
  // Regression: existing behavior before SGV — no sgv_verified field means
  // the workflow continues with the existing 'reported' phase.
  const routed = route(response({
    outcome_kind: 'report',
    report: {
      answer: 'INR 14,632.00',
      claim: 'The invoice total is visible on the page.',
    },
    suggested_actions: [action()],
  }))

  assert.equal(routed.phase, 'reported')
  assert.equal(routed.contractOutcome, 'report')
  assert.deepEqual(routed.pendingActions, [])
  assert.equal(routed.report.answer, 'INR 14,632.00')
  assert.match(routed.analysisText, /Report answer: INR 14,632\.00/)
  assert.match(routed.analysisText, /Report claim: The invoice total is visible on the page\./)
})

test('Production SGV: verified report (sgv_verified=true) routes to completed', () => {
  // The backend set sgv_verified=true — the workflow may complete now.
  // The extension routes to 'completed' and preserves the report for display.
  const routed = route(response({
    outcome_kind: 'report',
    sgv_verified: true,
    report: {
      answer: 'INR 14,632.00',
      claim: 'The invoice total is visible on the page.',
    },
    suggested_actions: [],
  }))

  assert.equal(routed.phase, 'completed')
  assert.equal(routed.contractOutcome, 'report')
  assert.deepEqual(routed.pendingActions, [])
  assert.equal(routed.report.answer, 'INR 14,632.00')
  assert.match(routed.analysisText, /Report answer: INR 14,632\.00/)
  assert.equal(routed.error, null)
})

test('Production SGV: unverified report (sgv_verified=false) routes to reported for existing loop continuation', () => {
  // The backend set sgv_verified=false — the workflow continues using the
  // existing 'reported' phase. No new SGV-specific execution path is created.
  // The planner will decide the next action on the following analyze cycle.
  const routed = route(response({
    outcome_kind: 'report',
    sgv_verified: false,
    report: {
      answer: '₹15,299.00',
      claim: 'The price is shown on the product page.',
    },
    suggested_actions: [],
  }))

  assert.equal(routed.phase, 'reported')
  assert.equal(routed.contractOutcome, 'report')
  assert.deepEqual(routed.pendingActions, [])
  assert.equal(routed.report.answer, '₹15,299.00')
  assert.equal(routed.error, null)
})

test('routes replan outcomes to presentation without actions or automatic retry', () => {
  const routed = route(response({
    outcome_kind: 'replan',
    replan: {
      reason: 'The current approach is not changing the page state.',
    },
    suggested_actions: [action()],
  }))

  assert.equal(routed.phase, 'replan')
  assert.equal(routed.contractOutcome, 'replan')
  assert.deepEqual(routed.pendingActions, [])
  assert.equal(routed.replan.reason, 'The current approach is not changing the page state.')
  assert.match(routed.analysisText, /Replan reason: The current approach is not changing the page state\./)
})

test('preserves backward compatibility when outcome_kind is absent', () => {
  const actionRoute = route(response({
    suggested_actions: [action()],
  }))
  const askRoute = route(response({
    clarification_question: 'What date should I enter?',
    suggested_actions: [],
  }))

  assert.equal(actionRoute.phase, 'awaiting_execution')
  assert.equal(actionRoute.contractOutcome, 'act')
  assert.equal(actionRoute.pendingActions.length, 1)
  assert.equal(askRoute.phase, 'awaiting_user')
  assert.equal(askRoute.contractOutcome, 'ask')
  assert.equal(askRoute.clarificationQuestion, 'What date should I enter?')
})

test('routes completion when no executable action remains', () => {
  const routed = route(response({
    outcome_kind: 'act',
    suggested_actions: [],
  }))

  assert.equal(routed.phase, 'completed')
  assert.equal(routed.contractOutcome, 'act')
  assert.deepEqual(routed.pendingActions, [])
})

test('execute to refresh to analyze loop sends fresh observation with prior steps', () => {
  const freshContext = pageContext({
    url: 'https://example.test/results',
    title: 'Results',
    visible_text: 'Python tutorial results are visible',
  })
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Search YouTube for Python tutorials.',
    freshContext,
    [completedAction()],
    ['Question: preferred language\nAnswer: English'],
  )

  assert.equal(workflowLoopObservationPhase(true), 'refreshing')
  assert.equal(request.page_context.url, 'https://example.test/results')
  assert.equal(request.prior_steps.length, 1)
  assert.match(request.prior_steps[0].execution_result, /Clicked search/)
  assert.match(request.prior_steps[0].execution_result, /Execution Feedback/)
  assert.match(request.prior_steps[0].execution_result, /Execution: success/)
  assert.match(request.supplemental_context, /Authoritative user-provided answers/)
})

test('successful execution feedback is included in latest planner context', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Open the search results.',
    pageContext(),
    [completedAction({
      result: {
        success: true,
        message: 'Clicked search',
        action_id: 'a1',
        verification: {
          verified: true,
          reason: 'verified',
          before_state: { domSignature: '<button id="raw">Search</button>' },
          after_state: { domSignature: '<main>Results</main>' },
          signals: { dom_changed: true },
        },
      },
    })],
    [],
  )

  const executionResult = request.prior_steps[0].execution_result
  assert.match(executionResult, /Execution Feedback/)
  assert.match(executionResult, /Action: click/)
  assert.match(executionResult, /Execution: success/)
  assert.match(executionResult, /Verification: verified/)
  assert.match(executionResult, /Treat the action as having produced the intended browser effect/)
})

test('no-effect execution feedback is included without leaking raw DOM', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Open filters.',
    pageContext(),
    [completedAction({
      result: {
        success: true,
        message: 'Clicked filters',
        action_id: 'a1',
        verification: {
          verified: false,
          reason: 'no_effect',
          before_state: { domSignature: '<button id="filters">Filters</button>' },
          after_state: { domSignature: '<button id="filters">Filters</button>' },
          signals: { dom_changed: false, url_changed: false },
        },
      },
    })],
    [],
  )

  const executionResult = request.prior_steps[0].execution_result
  assert.match(executionResult, /Verification: no_effect/)
  assert.match(executionResult, /Avoid repeating this selector/)
  assert.doesNotMatch(executionResult, /<button/)
  assert.doesNotMatch(executionResult, /domSignature/)
  assert.doesNotMatch(executionResult, /before_state/)
  assert.doesNotMatch(executionResult, /after_state/)
})

test('recovery success feedback is included', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Fill email.',
    pageContext(),
    [completedAction({
      action: { action_type: 'fill', description: 'Fill Email', target_selector: '#old-email', value: 'ada@example.test' },
      result: {
        success: true,
        message: 'Filled field: input[name="email"]',
        action_id: 'a1',
        verification: {
          verified: true,
          reason: 'verified',
          before_state: {},
          after_state: {},
          signals: { target_value_changed: true },
        },
        recovery_attempted: true,
        recovery_selector: 'input[name="email"]',
        recovery_source: 'associated_label',
        recovery_verified: true,
        recovery_reason: 'verified',
      },
    })],
    [],
  )

  const executionResult = request.prior_steps[0].execution_result
  assert.match(executionResult, /Recovery: attempted/)
  assert.match(executionResult, /Recovery Result: verified/)
  assert.match(executionResult, /Recovery Reason: verified/)
  assert.doesNotMatch(executionResult, /input\[name="email"\]/)
})

test('recovery failure feedback is included', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Open filters.',
    pageContext(),
    [completedAction({
      result: {
        success: true,
        message: 'Clicked filters',
        action_id: 'a1',
        verification: {
          verified: false,
          reason: 'no_effect',
          before_state: {},
          after_state: {},
          signals: {},
        },
        recovery_attempted: true,
        recovery_selector: 'button[aria-label="Filters"]',
        recovery_source: 'aria_label',
        recovery_verified: false,
        recovery_reason: 'no_effect',
      },
    })],
    [],
  )

  const executionResult = request.prior_steps[0].execution_result
  assert.match(executionResult, /Recovery: attempted/)
  assert.match(executionResult, /Recovery Result: failed/)
  assert.match(executionResult, /Recovery Reason: no_effect/)
  assert.match(executionResult, /Avoid repeating this selector/)
})

test('only latest execution includes feedback', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Search products.',
    pageContext(),
    [
      completedAction({
        result: {
          success: true,
          message: 'Clicked first step',
          action_id: 'a1',
          verification: { verified: false, reason: 'no_effect', before_state: {}, after_state: {}, signals: {} },
        },
      }),
      completedAction({
        action: { action_id: 'a2', description: 'Click second step' },
        result: {
          success: true,
          message: 'Clicked second step',
          action_id: 'a2',
          verification: { verified: true, reason: 'verified', before_state: {}, after_state: {}, signals: {} },
        },
      }),
    ],
    [],
  )

  assert.doesNotMatch(request.prior_steps[0].execution_result, /Execution Feedback/)
  assert.match(request.prior_steps[1].execution_result, /Execution Feedback/)
})

test('planner execution feedback remains bounded', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Open filters.',
    pageContext(),
    [completedAction({
      result: {
        success: true,
        message: 'Clicked filters',
        action_id: 'a1',
        verification: {
          verified: false,
          reason: 'no_effect',
          before_state: {},
          after_state: {},
          signals: {},
        },
        recovery_attempted: true,
        recovery_verified: false,
        recovery_reason: 'x'.repeat(3000),
      },
    })],
    [],
  )

  assert.ok(request.prior_steps[0].execution_result.length < 1100)
})

test('initial workflow loop observes before first analyze without prior steps', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Find tutorials.',
    pageContext(),
    [],
    [],
  )

  assert.equal(workflowLoopObservationPhase(false), 'observing')
  assert.equal(request.prior_steps, undefined)
  assert.equal(request.supplemental_context, '')
})

test('planner context includes compact task workspace summary when provided', () => {
  const ctx = pageContext({
    url: 'https://cursor.com/pricing',
    title: 'Cursor Pricing',
    headings: ['Plans'],
    visible_text: 'Free Plan: Yes\nStarting Price: $20/month\n<div>raw dom should not appear</div>',
  })
  const workspace = updateTaskWorkspace(
    createTaskWorkspace('Compare AI code assistant pricing'),
    ctx,
    [completedAction({ action: { description: 'Open Cursor pricing' } })],
  )
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Compare AI code assistant pricing',
    ctx,
    [completedAction()],
    [],
    workspace,
  )

  assert.match(request.supplemental_context, /Workspace Summary/)
  assert.match(request.supplemental_context, /Goal: Compare AI code assistant pricing/)
  assert.match(request.supplemental_context, /Completed:/)
  assert.match(request.supplemental_context, /Open Cursor pricing/)
  assert.match(request.supplemental_context, /Visited: 1 pages/)
  assert.match(request.supplemental_context, /Starting Price = \$20\/month/)
  assert.doesNotMatch(request.supplemental_context, /<div>/)
})

test('planner context includes compact multi-tab workspace summary when provided', () => {
  const ctx = pageContext({
    tab_id: 2,
    url: 'https://cursor.com/pricing',
    title: 'Cursor Pricing',
    headings: ['Plans'],
    visible_text: 'Starting Price: $20/month',
  })
  let tabWorkspace = createMultiTabWorkspace()
  tabWorkspace = registerTab(tabWorkspace, {
    id: 1,
    windowId: 1,
    url: 'https://google.com/search?q=ai',
    title: 'Google Search',
    active: false,
  })
  tabWorkspace = registerTab(tabWorkspace, {
    id: 2,
    windowId: 1,
    url: 'https://cursor.com/pricing',
    title: 'Cursor Pricing',
    active: true,
  })
  tabWorkspace = updateTabFactCount(tabWorkspace, 2, 3)
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Compare AI code assistant pricing',
    ctx,
    [],
    [],
    null,
    tabWorkspace,
  )

  assert.match(request.supplemental_context, /Tab Workspace/)
  assert.match(request.supplemental_context, /Active: Cursor Pricing/)
  assert.match(request.supplemental_context, /Google Search - visited/)
  assert.match(request.supplemental_context, /Cursor Pricing - active, Facts: 3/)
  assert.doesNotMatch(request.supplemental_context, /https:\/\//)
})

test('cancellation clears pending actions and enters cancelled state', () => {
  const patch = cancelWorkflowPatch()

  assert.equal(patch.phase, 'cancelled')
  assert.deepEqual(patch.pendingActions, [])
})

test('goal convergence is presentation state only for report/replan outcomes', () => {
  const reportRoute = route(response({
    outcome_kind: 'report',
    goal_convergence: true,
    report: {
      answer: 'Ready',
      claim: 'The status is visible.',
    },
  }))
  const replanRoute = route(response({
    outcome_kind: 'replan',
    goal_convergence: true,
    replan: {
      reason: 'Planner chose to change approach.',
    },
  }))

  assert.equal(reportRoute.goalConvergence, true)
  assert.equal(reportRoute.phase, 'reported')
  assert.deepEqual(reportRoute.pendingActions, [])
  assert.equal(replanRoute.goalConvergence, true)
  assert.equal(replanRoute.phase, 'replan')
  assert.deepEqual(replanRoute.pendingActions, [])
})
