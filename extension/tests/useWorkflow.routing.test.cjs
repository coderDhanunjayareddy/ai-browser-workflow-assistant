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
      'src/content/extractor.ts',
      'src/background/target_tab.ts',
    ],
    { cwd: root, stdio: 'inherit' },
  )
}

compileRouter()
const {
  appendValidationPriorStepOnce,
  actionRequiresDomSettle,
  actionRequiresExplicitApproval,
  buildAnalyzeRequestBody,
  buildBackendIntentPriorStep,
  buildBudgetedPlannerContext,
  buildRejectedReportPriorStep,
  cancelWorkflowPatch,
  createMissionSnapshot,
  createFreshWorkflowSessionId,
  meaningfulWorkflowFailure,
  createMultiTabWorkspace,
  createTaskWorkspace,
  phaseContinuationActions,
  pageContextHasNamedEditableControl,
  pageContextEvidenceScore,
  initialObservationAttempts,
  postNavigationObservationAttempts,
  registerTab,
  routeAnalyzeOutcome,
  selectRicherPageContext,
  PLANNER_SUPPLEMENTAL_CONTEXT_BUDGET,
  summarizeMissionSnapshot,
  updateTabFactCount,
  updateMissionSnapshot,
  updateTaskWorkspace,
  validateObservableProgress,
  workflowLoopObservationPhase,
  shouldAutoExecuteAction,
  shouldRequestSemanticRecovery,
} = require(path.join(outDir, 'sidepanel/hooks/useWorkflow.js'))
const { mergeInteractiveElementLists } = require(path.join(outDir, 'content/extractor.js'))
const { isGroundedBrowserTarget, isSelectableBrowserTarget } = require(path.join(outDir, 'background/target_tab.js'))

test.after(() => {
  fs.rmSync(outDir, { recursive: true, force: true })
})

test('browser control accepts only grounded http/https page tabs', () => {
  assert.equal(isGroundedBrowserTarget('https://web.whatsapp.com/'), true)
  assert.equal(isGroundedBrowserTarget('http://localhost:3000/test'), true)
  assert.equal(isGroundedBrowserTarget('chrome-extension://abc/sidepanel.html'), false)
  assert.equal(isGroundedBrowserTarget('chrome://extensions'), false)
  assert.equal(isGroundedBrowserTarget('about:blank'), false)
})

test('target selection permits only web pages and safe navigation bootstrap tabs', () => {
  assert.equal(isSelectableBrowserTarget('https://web.whatsapp.com/'), true)
  assert.equal(isSelectableBrowserTarget('chrome://newtab/'), true)
  assert.equal(isSelectableBrowserTarget('chrome://new-tab-page/'), true)
  assert.equal(isSelectableBrowserTarget('about:blank'), true)
  assert.equal(isSelectableBrowserTarget('chrome-extension://abc/sidepanel.html'), false)
  assert.equal(isSelectableBrowserTarget('chrome://extensions/'), false)
  assert.equal(isSelectableBrowserTarget('file:///C:/secret.txt'), false)
})

test('each newly submitted task receives a fresh mission session identity', () => {
  const first = createFreshWorkflowSessionId()
  const second = createFreshWorkflowSessionId()
  assert.match(first, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)
  assert.notEqual(first, second)
})

test('navigation waits for DOM settle after the tab load completes', () => {
  assert.equal(actionRequiresDomSettle('navigate'), true)
  assert.equal(actionRequiresDomSettle('navigate_next_page'), true)
  assert.equal(actionRequiresDomSettle('open_new_tab'), false)
})

test('post-navigation observation retains the richest delayed page context', () => {
  const shell = pageContext({ visible_text: 'Loading', interactive_elements: [] })
  const hydrated = pageContext({
    visible_text: 'Chats Search or start new chat',
    interactive_elements: [
      { type: 'button', text: 'New chat', selector: '[aria-label="New chat"]', visible: true },
      { type: 'input', text: '', selector: '[aria-label="Search input textbox"]', visible: true },
    ],
  })

  assert.ok(pageContextEvidenceScore(hydrated) > pageContextEvidenceScore(shell))
  assert.equal(selectRicherPageContext(shell, hydrated), hydrated)
  assert.equal(selectRicherPageContext(hydrated, shell), hydrated)
})

test('interactive-field tasks use a bounded extended observation window', () => {
  assert.equal(postNavigationObservationAttempts('Detect whether the contact search field is visible'), 8)
  assert.equal(postNavigationObservationAttempts('Read the current documentation page'), 3)
  assert.equal(initialObservationAttempts('Attach a file to a message recipient'), 8)
  assert.equal(initialObservationAttempts('Read the current documentation page'), 1)
  assert.equal(pageContextHasNamedEditableControl(pageContext({ interactive_elements: [] })), false)
  assert.equal(pageContextHasNamedEditableControl(pageContext({
    interactive_elements: [{
      type: 'input',
      text: '',
      selector: 'input[aria-label="Search or start a new chat"]',
      visible: true,
      role: 'textbox',
      aria_label: 'Search or start a new chat',
    }],
  })), true)
})

test('context merge preserves ranked controls and enriches duplicate accessibility metadata', () => {
  const ranked = [
    { type: 'div', text: 'Search or start new chat', selector: '[contenteditable="true"]', visible: true },
    { type: 'button', text: 'New chat', selector: '[aria-label="New chat"]', visible: true },
  ]
  const enriched = [
    {
      type: 'div',
      text: '',
      selector: '[contenteditable="true"]',
      visible: true,
      role: 'textbox',
      aria_label: 'Search input textbox',
      accessibility_name: 'Search input textbox',
    },
    { type: 'button', text: 'Menu', selector: '[aria-label="Menu"]', visible: true },
  ]

  const merged = mergeInteractiveElementLists(ranked, enriched, 3)

  assert.deepEqual(merged.map((element) => element.selector), [
    '[contenteditable="true"]',
    '[aria-label="New chat"]',
    '[aria-label="Menu"]',
  ])
  assert.equal(merged[0].text, 'Search or start new chat')
  assert.equal(merged[0].role, 'textbox')
  assert.equal(merged[0].aria_label, 'Search input textbox')
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

test('auto mode executes only safe reversible browser actions', () => {
  const benignFill = action({ action_type: 'fill', target_selector: '#query', description: 'Fill search query' })
  assert.equal(shouldAutoExecuteAction(benignFill, 'auto'), true)
  assert.equal(shouldAutoExecuteAction(action({ action_type: 'click' }), 'auto'), false)
  assert.equal(shouldAutoExecuteAction(benignFill, 'manual'), false)
  assert.equal(shouldAutoExecuteAction(action({ action_type: 'fill', safety_level: 'caution' }), 'auto'), false)
  assert.equal(shouldAutoExecuteAction(action({ action_type: 'fill', safety_level: 'danger' }), 'auto'), false)
  assert.equal(shouldAutoExecuteAction(action({
    action_type: 'navigate',
    target_selector: '',
    value: 'https://www.youtube.com/',
    description: 'Open verified YouTube destination',
  }), 'auto'), true)
  assert.equal(shouldAutoExecuteAction(action({
    action_type: 'navigate',
    target_selector: '',
    value: 'chrome://settings',
  }), 'auto'), false)
})

test('raw workflow failures become meaningful bounded user outcomes', () => {
  const timeout = meaningfulWorkflowFailure('navigate execution timed out after 45000ms', 'execution', 'Open YouTube')
  assert.equal(timeout.category, 'timeout')
  assert.equal(timeout.retryable, true)
  assert.match(timeout.userMessage, /safe time limit/i)
  assert.doesNotMatch(timeout.userMessage, /45000/)

  const uncertain = meaningfulWorkflowFailure('This action may already have been dispatched before a restart, so it was not repeated.', 'execution')
  assert.equal(uncertain.category, 'uncertain_dispatch')
  assert.equal(uncertain.retryable, false)
  assert.match(uncertain.userMessage, /without repeating/i)

  const target = meaningfulWorkflowFailure('Selector target not found', 'execution', 'Open exact chat')
  assert.equal(target.category, 'target_not_found')
  assert.match(target.userMessage, /did not click a substitute/i)

  const errorPage = meaningfulWorkflowFailure(
    'Could not verify page progress after navigate: Extraction failed: Frame with ID 0 is showing error page',
    'execution',
    'Open synthetic destination',
  )
  assert.equal(errorPage.category, 'network')
  assert.equal(errorPage.retryable, false)
  assert.match(errorPage.userMessage, /after one attempt/i)
})

test('semantic recovery is bounded and never replans consequential or uncertain actions', () => {
  const safe = action({ action_type: 'navigate', target_selector: '', value: 'https://www.youtube.com/', description: 'Open YouTube' })
  const failedOnce = [completedAction({ action: safe, result: { success: false, message: 'navigation timeout', action_id: safe.action_id } })]
  assert.equal(shouldRequestSemanticRecovery(safe, failedOnce), true)
  assert.equal(shouldRequestSemanticRecovery(safe, failedOnce, false), false)
  const chromeErrorPage = [completedAction({
    action: safe,
    result: {
      success: false,
      message: 'Could not verify page progress after navigate: Extraction failed: Frame with ID 0 is showing error page',
      action_id: safe.action_id,
    },
  })]
  assert.equal(shouldRequestSemanticRecovery(safe, chromeErrorPage), false)

  const failedTwice = [...failedOnce, completedAction({ action: safe, result: { success: false, message: 'no_effect', action_id: safe.action_id } })]
  assert.equal(shouldRequestSemanticRecovery(safe, failedTwice), false)

  const send = action({ action_type: 'click', description: 'Send email message', safety_level: 'safe' })
  assert.equal(shouldRequestSemanticRecovery(send, [completedAction({ action: send, result: { success: false, message: 'failed', action_id: send.action_id } })]), false)

  const uncertain = action({ action_type: 'click', description: 'Open chat', safety_level: 'safe' })
  assert.equal(shouldRequestSemanticRecovery(uncertain, [completedAction({ action: uncertain, result: { success: false, message: 'may already have been dispatched', action_id: uncertain.action_id } })]), false)
})

test('auto mode pauses for critical action classes even when marked safe', () => {
  const sendEmail = action({
    action_type: 'click',
    description: 'Click send email to the recruiter',
    safety_level: 'safe',
  })
  const payment = action({
    action_type: 'click',
    description: 'Continue to payment checkout',
    safety_level: 'safe',
  })
  const share = action({ action_type: 'fill', description: 'Share this document with a collaborator', safety_level: 'safe' })
  const submit = action({ action_type: 'fill', description: 'Submit the completed contact form', safety_level: 'safe' })
  const accountSetting = action({ action_type: 'fill', description: 'Update account notification settings', safety_level: 'safe' })

  assert.equal(actionRequiresExplicitApproval(sendEmail), true)
  assert.equal(actionRequiresExplicitApproval(payment), true)
  assert.equal(actionRequiresExplicitApproval(share), true)
  assert.equal(actionRequiresExplicitApproval(submit), true)
  assert.equal(actionRequiresExplicitApproval(accountSetting), true)
  assert.equal(shouldAutoExecuteAction(sendEmail, 'auto'), false)
  assert.equal(shouldAutoExecuteAction(payment, 'auto'), false)
  assert.equal(shouldAutoExecuteAction(share, 'auto'), false)
  assert.equal(shouldAutoExecuteAction(submit, 'auto'), false)
  assert.equal(shouldAutoExecuteAction(accountSetting, 'auto'), false)
})

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

test('routes orchestrator phase continuation actions into the execution queue', () => {
  const first = action({
    action_id: 'open-1',
    action_type: 'open_new_tab',
    value: 'https://tool1.example/',
    description: 'Open result 1',
  })
  const second = action({
    action_id: 'open-2',
    action_type: 'open_new_tab',
    value: 'https://tool2.example/',
    description: 'Open result 2',
  })
  const third = action({
    action_id: 'open-3',
    action_type: 'open_new_tab',
    value: 'https://tool3.example/',
    description: 'Open result 3',
  })

  const result = response({
    outcome_kind: 'act',
    suggested_actions: [first],
    execution_orchestrator: {
      active_phase: 'OPEN',
      should_replan: false,
      reason: 'Continue OPEN phase',
      continuation_actions: [second, third],
    },
  })
  const routed = route(result)

  assert.equal(routed.phase, 'awaiting_execution')
  assert.deepEqual(routed.pendingActions.map((item) => item.action_id), ['open-1'])
  assert.deepEqual(
    phaseContinuationActions(result, [], 'https://example.test').map((item) => item.action_id),
    ['open-2', 'open-3'],
  )
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

test('routes report outcomes without SGV verification to continuation', () => {
  // PRC-1: an unverified report is not terminal; it becomes validation context
  // for the next normal observe -> analyze cycle.
  const routed = route(response({
    outcome_kind: 'report',
    report: {
      answer: 'INR 14,632.00',
      claim: 'The invoice total is visible on the page.',
    },
    suggested_actions: [action()],
  }))

  assert.equal(routed.phase, 'refreshing')
  assert.equal(routed.contractOutcome, 'report')
  assert.deepEqual(routed.pendingActions, [])
  assert.equal(routed.report.answer, 'INR 14,632.00')
  assert.equal(routed.continueAfterRejectedReport, true)
  assert.equal(routed.rejectedReportPriorStep.action_type, 'report_validation')
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
  assert.equal(routed.continueAfterRejectedReport, false)
  assert.equal(routed.rejectedReportPriorStep, null)
  assert.match(routed.analysisText, /Report answer: INR 14,632\.00/)
  assert.equal(routed.error, null)
})

test('Production SGV: unverified report (sgv_verified=false) continues with validation prior step', () => {
  // The backend set sgv_verified=false. The workflow does not invent an action;
  // it only sends validation feedback so the planner can decide the next turn.
  const routed = route(response({
    outcome_kind: 'report',
    sgv_verified: false,
    report: {
      answer: '₹15,299.00',
      claim: 'The price is shown on the product page.',
    },
    suggested_actions: [],
  }))

  assert.equal(routed.phase, 'refreshing')
  assert.equal(routed.contractOutcome, 'report')
  assert.deepEqual(routed.pendingActions, [])
  assert.equal(routed.report.answer, '₹15,299.00')
  assert.equal(routed.continueAfterRejectedReport, true)
  assert.match(routed.rejectedReportPriorStep.execution_result, /Report Validation/)
  assert.match(routed.rejectedReportPriorStep.execution_result, /Result:\nRejected/)
  assert.match(routed.rejectedReportPriorStep.execution_result, /continue gathering evidence/)
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

test('routes act-without-action as failed until completion evidence exists', () => {
  const routed = route(response({
    outcome_kind: 'act',
    suggested_actions: [],
  }))

  assert.equal(routed.phase, 'failed')
  assert.equal(routed.contractOutcome, 'act')
  assert.deepEqual(routed.pendingActions, [])
  assert.match(routed.error, /No executable browser action/)
})

test('routes successful backend-only intent to refresh loop', () => {
  const backendResponse = response({
    outcome_kind: 'act',
    suggested_actions: [],
    intent_execution: {
      schema_version: 'intent_execution.v1',
      intent_id: 'collect-1',
      intent: 'collect_search_results',
      owner: 'browser_intelligence',
      capability: 'serp_collection',
      dispatch_target: 'browser_intelligence',
      status: 'succeeded',
      reason: 'Collected 5 observed search results.',
      evidence: [],
      next_intents: [],
      blocking_reason: null,
    },
  })
  const routed = route(backendResponse)

  assert.equal(routed.phase, 'refreshing')
  assert.equal(routed.continueAfterBackendStep, true)
  assert.deepEqual(routed.pendingActions, [])
  assert.equal(routed.error, null)

  const priorStep = buildBackendIntentPriorStep(backendResponse, pageContext({
    url: 'https://example.test/source',
    title: 'Source page',
  }))
  assert.equal(priorStep.action_type, 'collect_search_results')
  assert.equal(priorStep.page_url, 'https://example.test/source')
  assert.match(priorStep.execution_result, /Collected 5 observed search results/)
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
  assert.match(request.supplemental_context, /Active Goal/)
  assert.match(request.supplemental_context, /Authoritative user-provided answers/)
})

test('validateObservableProgress accepts navigate when requested URL is already reached', () => {
  const before = pageContext({ url: 'https://www.google.com/', title: 'Google', visible_text: 'Google Search' })
  const after = pageContext({ url: 'https://www.google.com/', title: 'Google', visible_text: 'Google Search' })

  const error = validateObservableProgress(
    action({
      action_type: 'navigate',
      value: 'https://www.google.com',
      description: 'Open Google',
      target_selector: '',
    }),
    before,
    after,
  )

  assert.equal(error, null)
})

test('validateObservableProgress still rejects no-effect clicks', () => {
  const before = pageContext()
  const after = pageContext()

  const error = validateObservableProgress(
    action({ action_type: 'click', description: 'Open result', target_selector: '#result' }),
    before,
    after,
  )

  assert.match(error, /did not visibly change after click/)
})

test('validateObservableProgress accepts verified tab focus without visible page change', () => {
  const before = pageContext({
    url: 'https://tool.example/',
    title: 'Tool',
    visible_text: 'Tool details',
  })
  const after = pageContext({
    url: 'https://tool.example/',
    title: 'Tool',
    visible_text: 'Tool details',
  })

  const error = validateObservableProgress(
    action({
      action_type: 'focus_existing_tab',
      value: 'url:https://tool.example/',
      description: 'Focus opened source tab',
      target_selector: '',
    }),
    before,
    after,
    { success: true, tab_switch_verified: true },
  )

  assert.equal(error, null)
})

test('open new tab prior step carries structured browser evidence', () => {
  const openedContext = pageContext({
    url: 'https://tool.example/pricing',
    title: 'Tool Pricing',
    visible_text: 'Pricing details are visible',
  })
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Open top results and compare pricing.',
    openedContext,
    [completedAction({
      action: {
        action_id: 'open-1',
        action_type: 'open_new_tab',
        value: 'result:1',
        description: 'Open ranked result 1',
      },
      result: {
        success: true,
        message: 'Opened new tab: https://tool.example/pricing',
        action_id: 'open-1',
        opened_tab_id: 123,
        previous_tab_id: 77,
        active_tab_id: 123,
        tab_switch_verified: true,
        browser_timeline: {
          requested_url: 'https://tool.example/',
          opened_window_id: 1,
          navigation_complete_ms: 456,
        },
      },
      page_snapshot: {
        url: 'https://tool.example/pricing',
        title: 'Tool Pricing',
        metadata: {},
      },
    })],
    [],
  )

  assert.equal(request.prior_steps.length, 1)
  assert.equal(request.prior_steps[0].browser_evidence.opened_tab_id, 123)
  assert.equal(request.prior_steps[0].browser_evidence.previous_tab_id, 77)
  assert.equal(request.prior_steps[0].browser_evidence.tab_switch_verified, true)
  assert.equal(request.prior_steps[0].browser_evidence.page_url, 'https://tool.example/pricing')
  assert.equal(request.prior_steps[0].browser_evidence.page_title, 'Tool Pricing')
  assert.equal(request.prior_steps[0].browser_evidence.requested_url, 'https://tool.example/')
})

test('fill prior step carries form validation evidence', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Fill the sandbox form with fake data and fix validation errors.',
    pageContext({
      url: 'https://forms.example/sandbox',
      title: 'Sandbox Form',
      visible_text: 'Test form',
    }),
    [completedAction({
      action: action({
        action_id: 'fill-1',
        action_type: 'fill',
        target_selector: '#email',
        value: 'alex.tester@example.test',
        description: 'Fill email',
      }),
      result: {
        success: true,
        message: 'Filled field: #email',
        action_id: 'fill-1',
        form_field_name: 'email',
        form_field_label: 'Email',
        form_field_type: 'email',
        field_valid: true,
        form_valid: false,
        invalid_field_count: 1,
        filled_field_count: 1,
        submit_control_detected: true,
      },
      page_snapshot: {
        url: 'https://forms.example/sandbox',
        title: 'Sandbox Form',
        metadata: {},
      },
    })],
    [],
  )

  const evidence = request.prior_steps[0].browser_evidence
  assert.equal(evidence.form_field_name, 'email')
  assert.equal(evidence.field_valid, true)
  assert.equal(evidence.form_valid, false)
  assert.equal(evidence.invalid_field_count, 1)
  assert.match(request.prior_steps[0].execution_result, /Form Valid: no/)
  assert.match(request.prior_steps[0].execution_result, /Invalid Fields: 1/)
})

test('navigate next page prior step carries pagination evidence', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Collect directory entries across at least 3 pages.',
    pageContext({
      url: 'https://directory.example/page/2',
      title: 'Directory Page 2',
      visible_text: 'More listings',
    }),
    [completedAction({
      action: action({
        action_id: 'next-1',
        action_type: 'navigate_next_page',
        target_selector: '',
        value: 'https://directory.example/page/2',
        description: 'Go to next page',
      }),
      result: {
        success: true,
        message: 'Navigating to next page: https://directory.example/page/2',
        action_id: 'next-1',
        next_page_url: 'https://directory.example/page/2',
        pagination_mode: 'next_link',
        pagination_control_label: 'Next',
        pagination_used_fallback_click: false,
      },
      page_snapshot: {
        url: 'https://directory.example/page/2',
        title: 'Directory Page 2',
        metadata: {},
      },
    })],
    [],
  )

  const evidence = request.prior_steps[0].browser_evidence
  assert.equal(evidence.next_page_url, 'https://directory.example/page/2')
  assert.equal(evidence.pagination_mode, 'next_link')
  assert.equal(evidence.pagination_control_label, 'Next')
  assert.equal(evidence.pagination_used_fallback_click, false)
})

test('upload prior step carries file broker evidence', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Upload a small PDF file and report the result.',
    pageContext({
      url: 'https://upload.example/files',
      title: 'Upload Files',
      visible_text: 'Upload accepted',
    }),
    [completedAction({
      action: action({
        action_id: 'upload-1',
        action_type: 'click',
        target_selector: '#file',
        description: 'Upload file',
      }),
      result: {
        success: true,
        message: 'File upload already selected: test.pdf',
        action_id: 'upload-1',
        upload_attempted: true,
        upload_completed: true,
        filename: 'test.pdf',
        upload_target_selector: '#file',
        upload_files_count: 1,
        upload_backed_by_file_input: true,
        upload_requires_user_file_selection: false,
        upload_accepted: true,
      },
      page_snapshot: {
        url: 'https://upload.example/files',
        title: 'Upload Files',
        metadata: {},
      },
    })],
    [],
  )

  const evidence = request.prior_steps[0].browser_evidence
  assert.equal(evidence.upload_target_selector, '#file')
  assert.equal(evidence.upload_files_count, 1)
  assert.equal(evidence.upload_accepted, true)
})

test('content broker evidence remains schema-bounded and outranks verbose adapter diagnostics', () => {
  const adapter_trace = Object.fromEntries(
    Array.from({ length: 30 }, (_, index) => [`diagnostic_${index}`, `value-${index}`]),
  )
  const request = buildAnalyzeRequestBody(
    'session-content',
    'Attach the file named synthetic-day4.txt and verify its preview. Do not send anything.',
    pageContext({ url: 'https://messaging.example.test/thread/123' }),
    [completedAction({
      action: action({ action_id: 'content-1', action_type: 'click', target_selector: '#document' }),
      result: {
        success: true,
        message: 'Broker-bound content preview verified: synthetic-day4.txt',
        action_id: 'content-1',
        adapter_trace,
        content_request_id: 'content-request-1',
        content_kind: 'document',
        insertion_effect: 'preview_then_send',
        destination_origin: 'https://messaging.example.test',
        destination_entity: 'Synthetic Recipient',
        upload_attempted: true,
        upload_completed: true,
        upload_files_count: 1,
        upload_backed_by_file_input: true,
        upload_accepted: true,
        preview_identity_observed: true,
        chooser_cancelled: false,
        filename: 'synthetic-day4.txt',
        mime_type: 'text/plain',
        size_bytes: 64,
        content_sha256: 'a'.repeat(64),
      },
    })],
    [],
  )

  const evidence = request.prior_steps[0].browser_evidence
  assert.ok(Object.keys(evidence).length <= 30)
  assert.equal(evidence.filename, 'synthetic-day4.txt')
  assert.equal(evidence.preview_identity_observed, true)
  assert.equal(evidence.destination_origin, 'https://messaging.example.test')
  assert.equal(evidence.upload_files_count, 1)
})

test('context budget manager leaves under-budget context unchanged', () => {
  const context = buildBudgetedPlannerContext([
    { heading: 'Mission Snapshot', content: 'Goal: Find invoice total', priority: 1 },
    { heading: 'Workspace Summary', content: 'Visited: 1 pages', priority: 2 },
  ])

  assert.equal(context, [
    'Mission Snapshot\nGoal: Find invoice total',
    'Workspace Summary\nVisited: 1 pages',
  ].join('\n\n'))
})

test('context budget manager trims lower-priority sections before current state', () => {
  const context = buildBudgetedPlannerContext([
    { heading: 'Mission Snapshot', content: 'Goal: Compare repositories', priority: 1 },
    { heading: 'Workspace Summary', content: 'Current Target: Repository B', priority: 2 },
    { heading: 'Old Prior Steps', content: 'old\n'.repeat(2000), priority: 4 },
  ], 240)

  assert.match(context, /Mission Snapshot/)
  assert.match(context, /Workspace Summary/)
  assert.doesNotMatch(context, /Old Prior Steps/)
  assert.ok(context.length <= 240)
})

test('context budget manager preserves mission and latest execution feedback', () => {
  const context = buildBudgetedPlannerContext([
    { heading: 'Mission Snapshot', content: 'Goal: Compare repositories', priority: 1 },
    {
      heading: 'Execution Feedback',
      content: "Execution Assessment: The selected element's semantic purpose did not match the intended goal.",
      priority: 1,
    },
    { heading: 'Older History', content: 'older details\n'.repeat(400), priority: 4 },
  ], 360)

  assert.match(context, /Mission Snapshot/)
  assert.match(context, /Execution Feedback/)
  assert.match(context, /semantic purpose did not match/)
  assert.doesNotMatch(context, /Older History/)
  assert.ok(context.length <= 360)
})

test('context budget manager preserves latest report validation', () => {
  const context = buildBudgetedPlannerContext([
    { heading: 'Mission Snapshot', content: 'Goal: Compare products', priority: 1 },
    {
      heading: 'Report Validation',
      content: 'Result: Rejected\nReason: The previous report could not be verified against current page evidence.',
      priority: 1,
    },
    { heading: 'Redundant Notes', content: 'note\n'.repeat(500), priority: 4 },
  ], 330)

  assert.match(context, /Report Validation/)
  assert.match(context, /Result: Rejected/)
  assert.doesNotMatch(context, /Redundant Notes/)
  assert.ok(context.length <= 330)
})

test('context budget manager output never exceeds planner supplemental limit', () => {
  const context = buildBudgetedPlannerContext([
    { heading: 'Mission Snapshot', content: 'Goal: ' + 'mission '.repeat(500), priority: 1 },
    { heading: 'Workspace Summary', content: 'workspace '.repeat(1000), priority: 2 },
    { heading: 'Tab Workspace', content: 'tabs '.repeat(1000), priority: 2 },
    { heading: 'Older History', content: 'history '.repeat(1000), priority: 4 },
  ])

  assert.ok(context.length <= PLANNER_SUPPLEMENTAL_CONTEXT_BUDGET)
  assert.match(context, /Mission Snapshot/)
})

test('context budget manager is deterministic for identical input', () => {
  const sections = [
    { heading: 'Mission Snapshot', content: 'Goal: ' + 'x '.repeat(1000), priority: 1 },
    { heading: 'Workspace Summary', content: 'Facts: ' + 'y '.repeat(1000), priority: 2 },
  ]

  assert.equal(
    buildBudgetedPlannerContext(sections, 500),
    buildBudgetedPlannerContext(sections, 500),
  )
})

test('mission starts correctly', () => {
  const mission = createMissionSnapshot('Compare repository stars.')

  assert.equal(mission.goal, 'Compare repository stars.')
  assert.equal(mission.missionStatus, 'not_started')
  assert.deepEqual(mission.completedObjectives, [])
  assert.deepEqual(mission.remainingObjectives, ['Compare repository stars.'])
  assert.equal(mission.currentFocus, 'Compare repository stars.')
  assert.equal(mission.confidence, 'low')
  assert.equal(mission.progressEstimate, 0)
})

test('mission completed objectives accumulate and do not duplicate repeated actions', () => {
  const ctx = pageContext({ title: 'Search Results', visible_text: 'Repository A: 10 stars' })
  const workspace = updateTaskWorkspace(
    createTaskWorkspace('Open repository and collect stars'),
    ctx,
    [
      completedAction({ action: { description: 'Open repository' } }),
      completedAction({ action: { description: 'Open repository' } }),
    ],
  )
  const mission = updateMissionSnapshot({
    goal: 'Open repository and collect stars',
    workspace,
    completedActions: [
      completedAction({ action: { description: 'Open repository' } }),
      completedAction({ action: { description: 'Open repository' } }),
    ],
  })

  assert.equal(mission.completedObjectives.filter((objective) => objective === 'Open repository').length, 1)
  assert.match(mission.knownBlockers.join('\n'), /Repeated browser action observed/)
})

test('mission remaining objectives shrink as workspace completes objectives', () => {
  const workspace = updateTaskWorkspace(
    createTaskWorkspace('Open first repository and open second repository'),
    pageContext({ title: 'First Repository' }),
    [completedAction({ action: { description: 'Open first repository' } })],
  )
  const mission = updateMissionSnapshot({
    goal: 'Open first repository and open second repository',
    workspace,
    completedActions: [completedAction({ action: { description: 'Open first repository' } })],
  })

  assert.match(mission.completedObjectives.join('\n'), /Open first repository/)
  assert.doesNotMatch(mission.remainingObjectives.join('\n'), /^Open first repository$/)
})

test('mission evidence accumulates from task and tab workspaces', () => {
  const ctx = pageContext({
    tab_id: 7,
    title: 'Repository A',
    visible_text: 'Stars: 31.8k\nLast updated: 4 minutes ago',
  })
  const workspace = updateTaskWorkspace(createTaskWorkspace('Compare repositories'), ctx, [])
  let tabWorkspace = createMultiTabWorkspace()
  tabWorkspace = registerTab(tabWorkspace, {
    id: 7,
    windowId: 1,
    url: 'https://example.test/a',
    title: 'Repository A',
    active: true,
  })
  tabWorkspace = updateTabFactCount(tabWorkspace, 7, workspace.extractedFacts.length)
  const mission = updateMissionSnapshot({
    goal: 'Compare repositories',
    workspace,
    tabWorkspace,
  })

  assert.match(mission.evidenceCollected.join('\n'), /Stars = 31\.8k/)
  assert.match(mission.evidenceCollected.join('\n'), /Repository A: \d+ facts/)
  assert.equal(mission.missionStatus, 'in_progress')
})

test('mission snapshot remains bounded', () => {
  const workspace = createTaskWorkspace('Compare many repositories')
  workspace.completedObjectives = Array.from({ length: 30 }, (_, index) => `Completed ${index}`)
  workspace.pendingObjectives = Array.from({ length: 30 }, (_, index) => `Remaining ${index}`)
  workspace.extractedFacts = Array.from({ length: 40 }, (_, index) => ({
    subject: `Repo ${index}`,
    label: 'Stars',
    value: `${index}`,
  }))
  const mission = updateMissionSnapshot({
    goal: 'Compare many repositories',
    workspace,
  })
  const summary = summarizeMissionSnapshot(mission)

  assert.ok(mission.completedObjectives.length <= 8)
  assert.ok(mission.remainingObjectives.length <= 8)
  assert.ok(mission.evidenceCollected.length <= 10)
  assert.ok(summary.length <= 1800)
})

test('mission updates after verified report', () => {
  const mission = updateMissionSnapshot({
    goal: 'Tell me the invoice total.',
    workspace: updateTaskWorkspace(createTaskWorkspace('Tell me the invoice total.'), pageContext({
      title: 'Invoice',
      visible_text: 'Total Due: INR 14,632.00',
    }), []),
    verifiedReport: true,
  })

  assert.equal(mission.missionStatus, 'completed')
  assert.equal(mission.progressEstimate, 100)
  assert.equal(mission.confidence, 'high')
})

test('mission updates after rejected report', () => {
  const rejectedStep = buildRejectedReportPriorStep(response({
    outcome_kind: 'report',
    sgv_verified: false,
    analysis: 'Reported too early.',
    report: {
      answer: 'Only one repository inspected.',
      claim: 'Comparison is complete.',
    },
    suggested_actions: [],
  }))
  const mission = updateMissionSnapshot({
    goal: 'Compare two repositories.',
    validationPriorSteps: [rejectedStep],
  })

  assert.equal(mission.missionStatus, 'blocked')
  assert.match(mission.knownBlockers.join('\n'), /Previous report was rejected by validation/)
})

test('planner context includes mission snapshot before workspace summary', () => {
  const ctx = pageContext({
    url: 'https://example.test/repo-a',
    title: 'Repository A',
    visible_text: 'Stars: 31.8k',
  })
  const workspace = updateTaskWorkspace(createTaskWorkspace('Compare repositories'), ctx, [
    completedAction({ action: { description: 'Open first repository' } }),
  ])
  const mission = updateMissionSnapshot({
    goal: 'Compare repositories',
    workspace,
    completedActions: [completedAction({ action: { description: 'Open first repository' } })],
  })
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Compare repositories',
    ctx,
    [],
    [],
    workspace,
    null,
    [],
    mission,
  )

  assert.match(request.supplemental_context, /^Active Goal/)
  assert.ok(request.supplemental_context.indexOf('Active Goal') < request.supplemental_context.indexOf('Mission Snapshot'))
  assert.ok(request.supplemental_context.indexOf('Mission Snapshot') < request.supplemental_context.indexOf('Workspace Summary'))
  assert.doesNotMatch(request.supplemental_context, /<html|<div|screenshot|DOM/i)
})

test('rejected report validation prior step is appended to planner request', () => {
  const rejectedStep = buildRejectedReportPriorStep(response({
    outcome_kind: 'report',
    sgv_verified: false,
    analysis: 'Reported too early.',
    report: {
      answer: 'Only one repository was inspected.',
      claim: 'This satisfies the comparison.',
    },
    suggested_actions: [],
  }), pageContext({ url: 'https://github.com/one/repo', title: 'One Repo' }))

  const request = buildAnalyzeRequestBody(
    'session-1',
    'Compare two repositories.',
    pageContext({ url: 'https://github.com/one/repo', title: 'One Repo' }),
    [completedAction()],
    [],
    null,
    null,
    [rejectedStep],
  )

  assert.equal(request.prior_steps.length, 2)
  assert.equal(request.prior_steps[1].action_type, 'report_validation')
  assert.match(request.prior_steps[1].execution_result, /Report Validation/)
  assert.match(request.prior_steps[1].execution_result, /The previous report could not be verified/)
  assert.match(request.prior_steps[1].execution_result, /avoid repeating the rejected report/)
  assert.doesNotMatch(request.prior_steps[1].execution_result, /<html|<div|screenshot|DOM/i)
})

test('identical rejected reports do not duplicate validation prior steps', () => {
  const rejectedStep = buildRejectedReportPriorStep(response({
    outcome_kind: 'report',
    sgv_verified: false,
    analysis: 'Reported too early.',
    report: {
      answer: 'Only one repository was inspected.',
      claim: 'This satisfies the comparison.',
    },
    suggested_actions: [],
  }), pageContext({ url: 'https://github.com/one/repo', title: 'One Repo' }))

  const once = appendValidationPriorStepOnce([], rejectedStep)
  const twice = appendValidationPriorStepOnce(once, rejectedStep)

  assert.equal(once.length, 1)
  assert.equal(twice.length, 1)
  assert.deepEqual(twice, once)
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

test('execution semantic mismatch feedback is included generically', () => {
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Open the repository page.',
    pageContext({ url: 'https://example.test/not-found', title: 'Page not found' }),
    [completedAction({
      action: {
        description: 'Click the repository link',
        target_selector: 'a[href="/example/repository/metadata"]',
      },
      result: {
        success: true,
        message: 'Clicked target',
        action_id: 'a1',
        verification: {
          verified: true,
          reason: 'verified',
          before_state: {},
          after_state: {},
          signals: { url_changed: true },
        },
        semantic_mismatch: true,
        semantic_mismatch_reason: 'obvious_wrong_page',
        semantic_mismatch_observed_result: 'The browser reached a page state that appears unrelated to the intended goal.',
        semantic_mismatch_assessment: "The selected element's semantic purpose did not match the intended goal.",
      },
    })],
    [],
  )

  const executionResult = request.prior_steps[0].execution_result
  assert.match(executionResult, /Execution Feedback/)
  assert.match(executionResult, /Execution: success/)
  assert.match(executionResult, /Verification: verified/)
  assert.match(executionResult, /Semantic Assessment: mismatch/)
  assert.match(executionResult, /The selected element's semantic purpose did not match the intended goal/)
  assert.match(executionResult, /Select an element whose semantic purpose matches the requested goal/)
  assert.doesNotMatch(executionResult, /stargazers/i)
  assert.doesNotMatch(executionResult, /<html|<div|screenshot|DOM/i)
})

test('repeated identical semantic mismatch feedback is not duplicated in prior steps', () => {
  const failedAction = {
    action: {
      description: 'Click the repository link',
      target_selector: 'a[href="/example/repository/metadata"]',
    },
    result: {
      success: true,
      message: 'Clicked target',
      action_id: 'a1',
      verification: {
        verified: true,
        reason: 'verified',
        before_state: {},
        after_state: {},
        signals: { url_changed: true },
      },
      semantic_mismatch: true,
      semantic_mismatch_reason: 'obvious_wrong_page',
      semantic_mismatch_observed_result: 'The browser reached a page state that appears unrelated to the intended goal.',
      semantic_mismatch_assessment: "The selected element's semantic purpose did not match the intended goal.",
    },
  }
  const request = buildAnalyzeRequestBody(
    'session-1',
    'Open the repository page.',
    pageContext({ url: 'https://example.test/not-found', title: 'Page not found' }),
    [
      completedAction(failedAction),
      completedAction(failedAction),
    ],
    [],
  )

  assert.equal(request.prior_steps.length, 2)
  assert.doesNotMatch(request.prior_steps[0].execution_result, /Semantic Assessment: mismatch/)
  assert.match(request.prior_steps[1].execution_result, /Semantic Assessment: mismatch/)
  assert.equal(
    (request.prior_steps[1].execution_result.match(/Execution Feedback/g) ?? []).length,
    1,
  )
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
  assert.equal(request.supplemental_context, 'Active Goal\nFind tutorials.')
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
  assert.equal(reportRoute.phase, 'refreshing')
  assert.deepEqual(reportRoute.pendingActions, [])
  assert.equal(reportRoute.continueAfterRejectedReport, true)
  assert.equal(replanRoute.goalConvergence, true)
  assert.equal(replanRoute.phase, 'replan')
  assert.deepEqual(replanRoute.pendingActions, [])
})
