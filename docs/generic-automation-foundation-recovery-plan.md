# Generic Automation Foundation Recovery Plan

**Status:** Mandatory recovery phase before resuming the original Day 5–15 feature plan  
**Owner requirement:** Application and website names are validation examples, not core workflow definitions.  
**Release rule:** No feature is complete until the same capability contract passes cross-domain conformance gates.

## Decision

Use a **15-working-day foundation reset**. Preserve the reusable trusted executor, canonical action contract, safety policy, broker, evidence, and durable ledger. Remove application-specific orchestration authority from the core and route all work through one domain-independent capability kernel.

Rejected alternatives:

1. **Continue patching the current vertical slice:** fastest for one demo, but repeats the narrow-workflow failure and is rejected.
2. **Restart the repository from zero:** discards working safety and execution infrastructure and is unnecessarily expensive.
3. **Add more site adapters before a generic kernel:** creates additional competing pipelines and is rejected.

## Honest current baseline

The repository already contains reusable components, but they are surrounded by parallel systems and application-specific authority:

- Generic assets exist: typed contracts, capability registry, policy, approvals, authorization, grounding, CDP execution, verification, durable extension ledger, and mission persistence.
- Application references occur across core code, adapters, validators, task graphs, state models, knowledge files, and extension verification.
- The largest active violation is the deterministic application branch inside `backend/app/orchestrator/workflow_orchestrator.py`.
- Multiple orchestration, mission, execution-gateway, task-graph, semantic-kernel, and continuity implementations overlap. This makes it possible for a narrow path to bypass the intended generic contract.
- Current source-file audit (including adapters, comments, and fixtures, so not every occurrence is a violation): backend references span 15 WhatsApp files, 13 Gmail files, 6 LinkedIn files, 6 Amazon files, 5 YouTube files, and 5 MakeMyTrip files; extension references span 6 WhatsApp files, 4 Gmail files, and 1 YouTube file.
- Day 3–5 reports do not prove cross-domain capability completion. They remain partial until corrected by the conformance gates in this plan.

## Governing architecture

```text
Natural-language objective
        |
        v
Objective decomposition + capability matching
        |
        v
Durable mission graph (completed / active / pending objectives)
        |
        v
Observe page -> semantic UI graph -> ground candidate
        |                              |
        |                              v
        |                     ambiguity / hard boundary
        |                              |
        |                              v
        |                    human intervention checkpoint
        |                              |
        +------------------------------+ resume + re-observe
        |
        v
Policy + confirmation + idempotency
        |
        v
ONE trusted executor
        |
        v
Postcondition verification + evidence + durable checkpoint
```

### Core invariants

1. Core packages contain no application/domain workflow branches.
2. The planner emits capabilities and typed effects, never application procedures.
3. Target identity is grounded from the current page using stable selector, accessible role/name/state, relationship, and verified visual evidence in that order.
4. A site adapter can contribute declarative observations, terminology aliases, or verification hints. It cannot dispatch browser mutations, change user-supplied identities, or define an independent workflow.
5. Every mutation uses one canonical executor contract with origin, tab/frame, target, expected effect, safety class, and idempotency key.
6. Every action terminates as verified complete, confirmation required, clarification required, human intervention required, unsupported, externally blocked, partially complete, or safely failed.
7. Raw exceptions are diagnostic evidence, never the user-facing outcome.
8. A user completes only the smallest unavoidable human step. The system checkpoints before pausing and resumes by re-observing without replaying completed or uncertain actions.
9. Passwords, OTPs, payment secrets, and CAPTCHA answers are entered directly into the browser and are never requested in the assistant prompt.
10. Unknown sites use the same semantic capability discovery. They do not fall into a named-site pipeline.

## Generic capability ontology

Each capability declares inputs, preconditions, observable target semantics, expected effect, verification evidence, safety class, retry budget, idempotency scope, and intervention policy.

### Navigation and context

- Resolve public destination
- Navigate, open, focus, switch, and close tabs
- Observe URL/title/origin/frame/loading state
- Preserve objectives across tabs and redirects

### Discovery and reading

- Find controls, regions, lists, tables, dialogs, menus, and documents
- Search/filter/paginate/load delayed content
- Extract structured facts with provenance
- Summarize across tabs

### Interaction

- Click/activate
- Fill/type/edit rich text
- Select option/date/toggle
- Scroll/hover/drag where evidence supports it
- Handle menus, dialogs, dropdowns, and complex forms

### Content transfer

- Bind approved local content
- Upload/attach/insert file, image, video, audio, GIF, emoji, or structured content
- Download and verify filename, type, size, and destination

### Consequential operations

- Send/share/submit/post/publish
- Delete/archive
- Purchase/pay/book
- Change account, security, or privacy settings
- Require immediate exact confirmation and exactly-once dispatch

### Human intervention

- Authentication/sign-in
- MFA/OTP/passkey/security key
- CAPTCHA/bot verification
- Privileged browser/OS UI
- Sensitive data entry
- Genuine destination/account ambiguity
- External approval or authorization

## Human intervention contract

An intervention checkpoint contains:

- Stable intervention ID and mission/objective IDs
- Reason code and intervention kind
- One concise requested human action
- Explicit data-handling rule (`direct_browser_only` for secrets)
- Observed origin, tab, frame, and pre-intervention page fingerprint
- Completed and pending objective IDs
- Expected resume condition expressed as observable evidence
- Intervention request budget (normally one request per unchanged gate)
- Expiry/staleness policy
- Idempotency and uncertain-action state

Resume sequence:

1. User completes the minor step directly in the browser.
2. System re-observes the bound tab/origin.
3. System verifies the resume condition.
4. If verified, mark the intervention satisfied and continue the next pending objective.
5. If unchanged, explain precisely what remains; do not repeat completed work.
6. If origin/account changed, require identity clarification rather than guessing.

## 15-working-day implementation plan

### Days 1–2 — Evidence reset and authority audit

- Freeze feature work and live consequential tests.
- Inventory every planner, orchestrator, executor, adapter, validator, state store, and report.
- Classify application references as core violation, optional adapter hint, trusted registry data, test fixture, or documentation.
- Select one authoritative mission store, capability kernel, policy path, executor, verifier, and durable ledger.
- Mark competing paths deprecated and prevent new call sites.
- Correct Day 3–5 status and remove unsupported general-readiness claims.

**Exit:** Machine-readable authority map; zero uncertainty about which component owns each stage.

### Days 3–4 — Capability and objective contracts

- Define the versioned generic capability request/result schemas.
- Define durable objective states and dependencies.
- Add required capability matching before destination or action selection.
- Separate user identities and constraints from planner/site evidence.
- Reject application procedure fields in core action contracts.

**Exit:** Natural-language tasks compile into domain-independent objectives and capabilities.

### Days 5–6 — Semantic observation and grounding

- Build one semantic UI graph from DOM, accessibility tree, frame tree, and bounded visual evidence.
- Represent role, accessible name, state, relationships, region, visibility, actionability, and bounding box separately from descendant content.
- Rank candidates by capability compatibility and exact identity evidence.
- Fail closed on ambiguity; screenshot coordinates require current hit-target verification.
- Add dynamic-content settle events instead of fixed sleeps wherever browser events exist.

**Exit:** Unfamiliar synthetic pages resolve controls without domain code; unrelated descendant text cannot become an action target.

### Days 7–8 — One executor and effect verifier

- Route all mutations through the canonical trusted executor.
- Remove or disable competing click/type/upload paths.
- Make expected effects typed and capability-specific.
- Verify destination, document/thread, value, selection, preview, download, submission, and no-effect states.
- Enforce retry budgets from effect and safety class, not error-string heuristics.

**Exit:** One observable dispatch path and one verification path for every mutation.

### Day 9 — Human intervention and resumability

- Implement the intervention checkpoint contract and side-panel UI.
- Detect CAPTCHA, authentication, MFA, privileged UI, sensitive entry, ambiguity, and external approval as typed gates.
- Preserve mission/objective state and uncertain-action state.
- Resume only after re-observation satisfies the expected condition.
- Add one-request-per-unchanged-gate and secret-handling protections.

**Exit:** Restart/login/MFA/CAPTCHA simulations resume without duplicate actions or repeated questions.

### Day 10 — Policy and confirmations

- Centralize risk classification around operation and effect.
- Require immediate confirmation for send/delete/share/purchase/submit/account changes.
- Bind confirmation to exact destination, exact content, current origin, and one idempotency key.
- Make uncertain consequential dispatch non-retriable.

**Exit:** All consequential classes pause correctly across unrelated domains.

### Days 11–12 — Adapter isolation and migration

- Move remaining application knowledge behind the declarative adapter interface.
- Adapters may add aliases, region hints, known postconditions, and capability exclusions.
- Adapters may not execute, construct selectors without live evidence, reinterpret user identity, or own state machines.
- Delete/disable named task graphs and validators that bypass the kernel after their behavior is represented generically.

**Exit:** Removing all adapters still leaves the synthetic and unseen-site capability suite functional.

### Days 13–14 — Cross-domain conformance and robustness

- For every capability, run:
  - Neutral synthetic fixture
  - Two structurally different real services where safe and authorized
  - One unseen/randomized synthetic DOM
  - Dynamic content, dialog, frame, delayed render, and stale-selector variants
  - Authentication/intervention and restart/resume variants
  - Prompt-injection, cross-origin, account-confusion, and privileged-URL safety cases
- Record latency, retries, no-effect actions, duplicate effects, and screenshots/traces.

**Exit:** Capability matrix passes without application branches in the core.

### Day 15 — Foundation release decision

- Run full regression and architecture-policy checks.
- Audit core source for domain/application literals.
- Review every remaining adapter and exception.
- Publish pass/fail evidence and known unsupported classes.
- Decide whether the original Day 5 exactly-once send gate may resume.

**Exit:** Evidence-backed release decision, not an automatic declaration of completion.

## Per-feature completion gate

A feature is complete only when all are true:

1. Versioned generic capability contract exists.
2. No core domain/app branch is required.
3. Semantic observation and grounding pass on randomized DOM variants.
4. Mutation uses the one trusted executor.
5. Expected effect is verified.
6. Retry/no-effect/timeout behavior is bounded.
7. Human intervention pauses and resumes correctly where applicable.
8. Consequential variants require exact confirmation and are idempotent.
9. Synthetic + two different real-service validations pass.
10. Unknown/unsupported cases return meaningful outcomes.
11. Traces, screenshots, latency, retries, and duplicate-side-effect counts are recorded.

## Architecture enforcement checks

- CI fails when core directories add known domain literals outside approved registry/adapter/test paths.
- CI fails when a second browser mutation dispatcher is introduced.
- CI fails when a capability lacks precondition, postcondition, safety, retry, and intervention metadata.
- CI fails when a site adapter imports executor or policy mutation APIs.
- CI fails when a report claims completion without linked raw evidence.

## Research basis

- WebDriver BiDi models browser automation as bidirectional events and includes explicit browsing-context prompt events: https://www.w3.org/TR/webdriver-bidi/
- WAI-ARIA defines interoperable roles, names, states, and properties; accessible names should be concise and distinguish purpose: https://www.w3.org/WAI/ARIA/apg/practices/names-and-descriptions/
- Chrome documents that extension service-worker globals can disappear and durable state must be persisted: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Chrome DevTools Protocol exposes file-chooser events and exact file-input binding primitives: https://chromedevtools.github.io/devtools-protocol/tot/Page/
- Playwright documents event-coupled file chooser handling and reusable authenticated browser state for controlled testing: https://playwright.dev/docs/api/class-page and https://playwright.dev/docs/auth

## Immediate implementation order

The first code change is the generic human-intervention contract plus durable checkpoint support. It does not mention any application. The second is a machine-readable authority map and CI rule preventing new domain literals in core paths. Only then does migration of existing application branches begin.
