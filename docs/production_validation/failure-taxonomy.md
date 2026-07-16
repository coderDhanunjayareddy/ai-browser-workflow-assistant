# Production Validation Failure Taxonomy

Classify every failed or partial PVS task by the earliest incorrect component. Use one primary category and optional secondary tags.

## Planner

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| PL-01 | Wrong action | Planner chose an action that could not advance the mission. | Correct evidence existed, but action was irrelevant. |
| PL-02 | Premature report | Planner reported before enough evidence was collected. | SGV rejection or missing mission objectives. |
| PL-03 | Wrong selector choice | Planner selected a semantically wrong element selector. | Element metadata distinguished correct target from chosen target. |
| PL-04 | Goal misunderstanding | Planner optimized for a different goal than the user requested. | Mission snapshot and user goal contradict decision. |
| PL-05 | Mission drift | Planner abandons or forgets original mission. | Later decisions ignore mission snapshot/workspace. |
| PL-06 | No action suggested | Planner produces no executable outcome when progress remains possible. | Parsed response has no action/report/ask/replan. |
| PL-07 | Repeated action | Planner repeats same ineffective action despite feedback. | PriorStep contains failure/no-effect/rejection. |
| PL-08 | Bad report content | Report outcome exists but claim/answer is unsupported or incomplete. | SGV rejection or missing required facts. |

## Prompt / Model

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| PM-01 | Prompt ambiguity | Instructions allow a plausible but wrong interpretation. | Multiple valid interpretations found in rendered prompt. |
| PM-02 | Capability unawareness | Planner fails to use available tab/upload/widget capability. | Prompt contains capability guidance but decision ignores it. |
| PM-03 | Context ignored | Planner received correct mission/workspace/execution evidence but did not use it. | Trace shows context present before wrong decision. |
| PM-04 | Model output malformed | Provider response cannot be parsed or is truncated. | Raw provider response invalid or incomplete. |

## Context / Memory

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| CM-01 | Context compression loss | Answer-bearing or action-critical evidence lost before planner request. | Observation has evidence; prompt/compressed context does not. |
| CM-02 | Workspace loss | Completed objective, fact, or pending objective missing from workspace. | Prior observations/actions contain fact; workspace omits it. |
| CM-03 | Mission state error | Mission Snapshot status/progress/focus incorrect. | Snapshot contradicts trace evidence. |
| CM-04 | Tab confusion | Active/open tab summary incorrect or planner uses wrong tab. | Tab workspace mismatch or stale active tab. |
| CM-05 | Long-context drift | Relevant earlier evidence aged out without durable summary. | Earlier fact absent from workspace/mission snapshot. |

## Grounding / Element Selection

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| GR-01 | Missing element | Correct element absent from observation. | DOM has element but observation lacks it. |
| GR-02 | Ambiguous element | Multiple candidates indistinguishable in context. | Same text/role/selector quality. |
| GR-03 | Wrong semantic metadata | Element role/text/destination mislabeled or incomplete. | Extracted metadata contradicts DOM/browser state. |
| GR-04 | Selector instability | Selector valid at planning but invalid at execution due to DOM change. | Element disappeared or selector no longer resolves. |

## Browser Execution

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| EX-01 | Selector failure | Selector not found or not actionable. | Execution error or target missing. |
| EX-02 | No-effect action | Action succeeds technically but page state does not change. | Verification reason `no_effect`. |
| EX-03 | Dynamic UI failure | Generic action cannot operate a custom widget. | Widget pattern visible; generic click/fill fails. |
| EX-04 | Covered/blocked element | Target exists but overlay or modal prevents interaction. | Verification or page state shows overlay/modal. |
| EX-05 | Navigation failure | Navigation does not reach intended page or times out. | URL/title unchanged or wrong state. |
| EX-06 | Scroll failure | Required content not reached after scroll. | Scroll unchanged or content still missing. |

## Adaptive Execution

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| AE-01 | Selector recovery unavailable | No alternate selector chosen when one existed. | Observation has alternate candidate; recovery not attempted/successful. |
| AE-02 | Selector recovery wrong | Recovery selector points to wrong semantic target. | Recovered selector executes but wrong page/state. |
| AE-03 | Widget adapter missing | Unsupported widget type blocks progress. | Known widget pattern not handled. |
| AE-04 | Widget adapter incorrect | Adapter activates but fails or selects wrong value. | Adapter metadata and final state mismatch. |
| AE-05 | File upload failure | Upload not completed or filename not visible. | Upload metadata false/missing. |
| AE-06 | File download failure | Download not detected/completed. | Download metadata false/missing. |
| AE-07 | Tab control failure | Open/switch/close/focus operation not verified. | Tab metadata mismatch. |

## Validation

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| VA-01 | SGV false rejection | Correct report rejected despite evidence. | Page evidence supports report; SGV rejects. |
| VA-02 | SGV false acceptance | Incorrect report accepted. | Accepted report contradicts page evidence. |
| VA-03 | Validation evidence missing | Validator lacks evidence available elsewhere. | Observation/workspace has fact; verifier does not consume it. |
| VA-04 | Completion not recognized | Goal satisfied but workflow continues. | Mission complete and evidence present, but no completion. |

## Convergence / Recovery

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| CR-01 | GC too strict | Stagnation exists but GC does not trigger. | Repeated unchanged semantic evidence. |
| CR-02 | GC too lenient | GC triggers during productive progress. | Form state/evidence changed. |
| CR-03 | SG context missing | GC fires but strategy context not delivered. | Trace lacks SG prior step after GC. |
| CR-04 | PR not entered | Recovery should activate after GC/SG but does not. | GC/SG present; planner request not recovery turn. |
| CR-05 | PR ineffective | Recovery turn repeats failed behavior. | Recovery context present; next action unchanged. |

## Environment / Website

| Code | Failure Type | Definition | Evidence |
|---|---|---|---|
| EN-01 | Authentication required | Workflow cannot proceed without login. | Login wall shown. |
| EN-02 | CAPTCHA / bot challenge | Website blocks automation. | CAPTCHA/challenge page visible. |
| EN-03 | Rate limiting | Website throttles or blocks repeated requests. | 429/rate message. |
| EN-04 | Network failure | Page/API unavailable. | Browser/network error. |
| EN-05 | Permission denied | Browser or OS permission blocks task. | Permission prompt/denial. |
| EN-06 | Paid/account feature | Requested workflow requires subscription/account. | Page indicates gated feature. |

## Classification Rules

1. Classify the earliest incorrect component, not the final symptom.
2. If environment blocks the first meaningful action, classify as Environment.
3. If the planner received correct context and still chose wrong, classify Planner or Prompt/Model.
4. If the planner did not receive required evidence, classify Context/Memory or Grounding.
5. If action was correct but browser behavior failed, classify Browser Execution or Adaptive Execution.
6. If a report was involved, evaluate SGV separately before assigning Planner vs Validation.
7. Use secondary tags only after assigning one primary category.
