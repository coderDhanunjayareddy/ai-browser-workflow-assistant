# OpenAI Browser-Agent Blueprint and AI Browser Assist Gap Analysis

**Date:** 2026-08-14  
**Scope:** Publicly documented OpenAI browser products, a clearly labelled architectural reconstruction, and a code-based comparison with this repository.

## 1. Executive conclusion

The relevant OpenAI product is not one extension. It is a product family:

1. **Codex/ChatGPT Chrome extension** — lets ChatGPT work in the user's existing Chrome profile, signed-in sessions, tabs, and installed extensions.
2. **ChatGPT built-in browser** — an app-owned browser profile for shared browsing, local development, annotations, downloads, and computer use.
3. **ChatGPT cloud/visual browser and Agent** — a remote virtual computer for delegated, long-running work.
4. **Text browser, APIs/connectors, and terminal** — alternative tools selected when GUI interaction is not the safest or most efficient route.
5. **Atlas Agent mode** — a browser-native ChatGPT experience, including logged-in and logged-out modes with stricter boundaries for sensitive use.

OpenAI has documented capabilities, permissions, safety behavior, the computer-use API loop, and some model/evaluation details. It has **not** published the extension source code, production system prompts, model weights, private service topology, training data, complete action protocol, or implementation of its native host. Any document claiming to have extracted those private details would be guessing.

The strongest transferable idea is therefore not a secret prompt. It is the system design:

> Route each task to the least-powerful sufficient tool; maintain a persistent observe-plan-act-verify loop; treat all page content as untrusted; enforce authorization outside the model; ask for confirmation at the last responsible moment; and measure real end-to-end completion rather than module existence.

This repository already has substantial pieces of that design. Its largest remaining gap is not “more planning modules.” It is a production-grade browser control plane: CDP-backed trusted input, screenshot/vision grounding, frame and shadow-root coverage, a unified policy gate on the live execution path, resumable task state, and evidence from broad live-site evaluations.

## 2. What OpenAI publicly confirms

### 2.1 Chrome extension surface

Official documentation says the Chrome extension can:

- read and act on sites in an existing signed-in Chrome profile;
- use open tabs and selected text as context;
- use timestamped YouTube transcripts when captions exist;
- start or continue chats in a side panel;
- organize task tabs into tab groups;
- ask for website access once, per site, or for all sites;
- maintain allowlists and blocklists in the desktop app;
- request scoped browser-history access, with no permanent always-allow choice for history;
- connect to a cooperating native application.

The documented Chrome permission prompt can include debugger access, all-site read/write, history, notifications, bookmarks, downloads, native messaging, and tab-group management. OpenAI states that product-level confirmations and site policies remain in force even after Chrome grants extension permissions.

Source: [OpenAI — Chrome extension](https://learn.chatgpt.com/docs/chrome-extension).

### 2.2 Built-in browser surface

The built-in browser uses a profile separate from regular Chrome. It can open pages, click, type, inspect rendered state, take screenshots, verify results, handle multiple tabs, download files, and accept visual annotations for local or public pages. It asks before new-site access and before sensitive actions. Official documentation currently says automated file uploads are unavailable in the built-in browser.

Source: [OpenAI — Browser](https://learn.chatgpt.com/docs/browser?surface=app).

### 2.3 ChatGPT Agent tool portfolio

OpenAI describes ChatGPT Agent as a unified system with a visual browser, a text browser, a terminal, direct API access, and connectors. The model can choose among them, preserve task context across tools, accept interruption or steering, pause for missing information, and continue long-running work.

This is important: the reference design is **not GUI-only automation**. A robust agent avoids the browser when a structured API, connector, text retrieval tool, or deterministic local operation is better.

Source: [OpenAI — Introducing ChatGPT agent](https://openai.com/index/introducing-chatgpt-agent/).

### 2.4 Computer-use execution pattern

OpenAI's API documentation defines three viable harness shapes:

- a built-in `computer` tool where the model returns UI actions for the application to execute;
- custom function tools over an existing Playwright/Selenium or other automation harness;
- an isolated code-execution harness that exposes persistent browser objects and returns text/screenshots.

The general loop is:

1. provide the user goal and current observation;
2. receive one or more proposed actions;
3. check policy and confirmation requirements in application code;
4. execute authorized actions in the browser/VM;
5. capture a new screenshot and structured state;
6. append the tool result to the same conversation/task state;
7. repeat until verified completion, user input, or a terminal failure.

OpenAI recommends an isolated browser or VM, empty inherited environment, disabled extensions and file-system access where possible, explicit site/account/action boundaries, and human involvement for high-impact actions.

Source: [OpenAI API — Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use).

### 2.5 Safety architecture

The documented controls are layered:

- page text, screenshots, files, email, and tool outputs are untrusted data, never user authorization;
- high-impact actions require confirmation close to execution;
- sensitive contexts may require continuous “watch mode” supervision;
- suspicious prompt injection should stop execution and be surfaced to the user;
- sensitive-data transmission needs narrow, informed consent;
- certain sites/actions are blocked;
- memory and terminal networking can be restricted;
- credentials, CAPTCHAs, and some payment steps are handed back to the user;
- logged-out browsing reduces exposure to existing cookies and accounts.

OpenAI's system card reports specialized prompt-injection training, automated monitors/filters, confirmations, watch mode, network restrictions, and product evaluations. These are product claims and evaluation results—not enough detail to reproduce the private classifiers or training.

Sources: [ChatGPT Agent system card](https://cdn.openai.com/pdf/839e66fc-602c-48bf-81d3-b21eacc3459d/chatgpt_agent_system_card.pdf), [OpenAI API — Computer use](https://developers.openai.com/api/docs/guides/tools-computer-use), [OpenAI — Atlas Agent](https://help.openai.com/en/articles/12628199).

## 3. Reconstructed OpenAI architecture

The following is an **inference from documented behavior and permissions**, not leaked or published source code.

```text
User / side panel / desktop chat
             |
             v
Task session + conversation state + interruption/resume
             |
             v
Planner / tool router
   |         |          |          |          |
   v         v          v          v          v
Chrome    Built-in   Visual     Text web   APIs/connectors/
bridge    browser    browser    retrieval   terminal
   |         |          |
   +---------+----------+
             v
Observation normalizer
(screenshot + DOM/a11y + URL/tab + downloads + tool results)
             |
             v
Policy engine / site grants / data-flow checks / confirmation gate
             |
             v
Action executor -> postcondition verifier -> trace/evals -> next turn
```

Probable Chrome-specific split:

```text
Chrome side panel
  <-> MV3 service worker
      <-> content/page observation
      <-> chrome.debugger / CDP for browser-level control
      <-> tabs, tabGroups, downloads, history, bookmarks
      <-> native messaging host
          <-> ChatGPT desktop task runtime and authenticated session
```

Why this inference is well supported:

- OpenAI documents debugger and native-application permissions.
- Chrome documents `chrome.debugger` as a CDP transport with DOM, Accessibility, Input, Network, Page, Runtime, Target, and screenshot-capable domains.
- Chrome documents native messaging as a service-worker/extension-page bridge to a local application.
- OpenAI documents cross-surface chat continuity, desktop settings, website policy, and automatic tool selection.

Primary browser-platform sources: [Chrome debugger API](https://developer.chrome.com/docs/extensions/reference/api/debugger), [Chrome native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging), [Chrome message passing](https://developer.chrome.com/docs/extensions/develop/concepts/messaging).

## 4. What this repository actually implements

### 4.1 Runtime shape

The current product is a Manifest V3 Chrome extension with a React side panel, event-driven service worker, injected extractors/executors, and a FastAPI/PostgreSQL backend. The live path observes a page, compresses context, calls a configured Gemini/OpenRouter/Grok/Anthropic-capable planner path, returns a structured next outcome, asks for or applies approval according to UI mode, executes an action, observes again, and checks progress.

Current planner outcomes include `act`, `wait`, `ask`, `report`, and `replan`. The prompt currently advertises click, fill, scroll, navigate, wait, select option, choose date, hover, keyboard shortcut, and multi-tab actions. The extension includes resilient locators, action verification, widget adapters, rich-text handling, file-transfer handling, multi-tab workspace state, and DOM-settle/progress checks.

### 4.2 Permission and control boundary

Current required permissions are `activeTab`, `downloads`, `sidePanel`, `storage`, `scripting`, and `tabs`, with HTTP and HTTPS host access. The project does **not** currently request debugger, native messaging, history, bookmarks, notifications, or tab-group permissions.

Consequences:

- it can act inside ordinary page DOM and manage tabs/download events;
- it cannot currently use CDP `Input`, `Target`, `Network`, or debugger-level frame control;
- DOM `.click()` and synthetic input remain weaker than browser-level trusted input;
- closed shadow roots, canvas/WebGL controls, browser chrome, permission bubbles, native dialogs, and some cross-origin frames remain inaccessible or unreliable;
- there is no desktop native-host bridge comparable to the documented OpenAI integration.

### 4.3 Breadth versus demonstrated maturity

Repository inventory on 2026-08-14:

- 676 backend Python files;
- 33 extension TypeScript/TSX files;
- 265 backend test files and 13 extension test files;
- 70 declared V4 browser capabilities;
- declared rollout: 34 beta, 32 shadow, 4 experimental;
- declared maturity: 47 at level 4, 10 at level 3, 9 at level 2, 4 at level 1.

Those maturity labels are internal metadata, not independent proof of live reliability. The latest checked live-sidepanel artifact contains one WhatsApp task that correctly pauses for recipient disambiguation; it is useful evidence for one flow, not a general success-rate estimate.

Several backend surfaces still explicitly identify themselves as in-memory, stubs, no-ops, or future persistence. Product UI also contains stub integration, billing, SSO, and SCIM operations. These should not be represented as production capabilities.

## 5. Capability comparison

| Area | OpenAI public product | This repository | Assessment |
|---|---|---|---|
| Existing signed-in Chrome | Yes | Yes | Core parity direction |
| Side-panel task UX | Yes | Yes | Present |
| Cross-app/native bridge | Documented native application bridge | No native messaging permission/host | Major gap |
| Browser-level input | Debugger permission documented; CDP is the likely mechanism | DOM injection/synthetic events | Major reliability gap |
| Perception | Screenshot/visual plus rendered inspection; text browser also available | Primarily DOM/a11y/text; partial visual capability modules | Major gap on visual-only UI |
| Multi-tab work | Tabs and task tab groups | Multi-tab workspace, no tabGroups permission | Partial |
| Downloads | Supported and permissioned | Download lifecycle handling present | Partial-to-strong |
| Uploads | Surface-dependent restrictions/handoffs | File-transfer adapters present | Needs broad live proof |
| Tool routing | GUI, text browser, terminal, APIs/connectors | Browser planner plus research/backend subsystems | Conceptually present, fragmented |
| Confirmation policy | Site grants + per-risk confirmation + watch mode | Action approval UI and policy modules | Good foundation; needs one enforced live gate |
| Prompt-injection defense | Training + monitors + policy + confirmation + isolation | Prompt rules/policy code, but no equivalent proven multilayer defense | Major security gap |
| Isolation | Remote VM/app-owned browser/logged-out mode available | Real user profile; optional Playwright paths | Higher blast radius in live Chrome |
| Resumability/background | Documented long-running task continuation | Session/mission state exists; multiple in-memory/stub stores remain | Partial |
| Evidence and evals | Public benchmark/system-card evaluation plus production controls | Large unit suite and benchmark scaffolding; limited live-site artifact | Major evidence gap |
| Product governance | Workspace controls, blocklists, RBAC, retention controls | Broad product/governance scaffolding, some stubs | Not production-ready |

## 6. Correct target architecture for this project

Do not pursue “every task a human can do” as a single unlimited permission set. Use capability tiers and explicit security boundaries.

### Plane A — Interaction surfaces

- Chrome side panel for signed-in, user-visible workflows.
- Isolated managed browser/VM for autonomous or high-uncertainty browsing.
- User takeover surface for credentials, CAPTCHA, MFA, payment details, and unsupported native UI.
- Optional desktop host only for narrowly scoped, user-enabled local capabilities.

### Plane B — Observation

Create one versioned observation envelope containing:

- URL, origin, tab/window/frame identity, navigation state;
- accessibility tree and compact DOM semantics;
- screenshot and viewport/device scale;
- focused element, selection, overlays, dialogs, downloads/uploads;
- recent action result and structured postconditions;
- provenance and trust label for every text/image field.

Use incremental DOM/a11y diffs for efficiency. Request full screenshots only when the page changed materially, grounding failed, or a visual surface is detected.

### Plane C — Planning and tool routing

- semantic task contract: goal, constraints, completion criteria, allowed data, allowed sites;
- deterministic router first: API/connector > structured text retrieval > DOM/CDP > visual coordinates;
- model proposes typed actions, never arbitrary privileged code in the extension;
- maintain a compact task ledger with completed facts, failed attempts, and open subgoals;
- bounded retries and replanning budgets;
- ask the user only for irreducible ambiguity or authorization.

### Plane D — Execution

Add a CDP adapter through `chrome.debugger` for:

- trusted mouse/keyboard/touch input;
- frame/target discovery and attachment;
- accessibility and DOM snapshots;
- screenshots;
- navigation/network lifecycle signals;
- download/navigation verification.

Keep existing DOM adapters as the fast semantic path. Use the order:

1. deterministic site/API adapter;
2. resilient DOM/a11y locator;
3. CDP browser-level action;
4. screenshot/coordinate grounding;
5. user handoff.

### Plane E — Policy and security

The executor must require a signed authorization decision, not trust planner fields such as `safety_level`.

Policy input should include user intent, action, site, account, data being transmitted, reversibility, financial/legal/medical impact, audience, and prior confirmation. Policy output should be `allow`, `confirm`, `watch`, `handoff`, or `deny`, with expiry and scope.

Add:

- per-origin optional permissions and visible site grants;
- logged-out/isolated mode for untrusted exploration;
- cross-origin data-flow labels and exfiltration prevention;
- prompt-injection detection plus a hard stop for suspicious instructions;
- secret/OTP/password redaction before model context;
- immutable audit records of policy decisions and user confirmations;
- extension/native-host signing and update-chain controls;
- strict service-worker message validation and sender checks.

Chrome explicitly recommends least privilege, optional permissions, HTTPS, strict input validation, and treating content-script messages as attacker-controlled. Sources: [Chrome extension security](https://developer.chrome.com/docs/extensions/develop/security-privacy/stay-secure), [Chrome user privacy](https://developer.chrome.com/docs/extensions/develop/security-privacy/user-privacy), [Chrome optional permissions](https://developer.chrome.com/docs/extensions/reference/api/permissions).

### Plane F — State, observability, and recovery

- one durable task/event schema rather than parallel registries;
- append-only action, observation, policy, confirmation, and verification events;
- encrypted secrets separated from task context;
- idempotency keys for all consequential actions;
- resumable checkpoints after every verified state transition;
- per-step latency/token/cost, grounding method, retry, and failure classification;
- replay that can reconstruct decisions without storing unnecessary sensitive page content.

### Plane G — Evaluation and release

Measure task completion, not module count. Release gates should include:

- success without intervention;
- success with expected confirmation/handoff;
- wrong-action and no-effect rate;
- duplicate side-effect rate;
- prompt-injection resistance and data-exfiltration rate;
- confirmation precision/recall, with 100% recall for defined critical actions;
- p50/p95 step latency, tokens, and cost;
- recovery success after stale DOM, navigation, popup, and ambiguous target;
- performance across SPAs, iframes, open shadow DOM, canvas, virtualized lists, rich editors, downloads, uploads, and multi-tab flows.

Use fixed fixtures for deterministic regression, then a controlled live-site suite with disposable accounts. Never claim broad browser coverage from unit tests or capability metadata alone.

## 7. Prioritized implementation roadmap

### Phase 0 — Freeze and measure (1–2 weeks)

1. Freeze new backend subsystems.
2. Publish a single live runtime map and mark every module `live`, `shadow`, `test-only`, `stub`, or `dead`.
3. Run 25–50 representative end-to-end tasks and publish raw pass/fail traces.
4. Define critical-action and sensitive-data policies before expanding autonomy.

Exit gate: trustworthy baseline metrics and no ambiguous production claims.

### Phase 1 — Unified live safety gate (2–3 weeks)

1. Put every action through one policy engine immediately before execution.
2. Implement origin grants, narrow confirmation receipts, expiry, and audit logging.
3. Add prompt-injection stop/escalate behavior and provenance labels.
4. Validate all service-worker messages and privileged URL/action arguments.

Exit gate: no consequential action can bypass policy; critical confirmation recall is 100% on the test suite.

### Phase 2 — CDP control and hybrid grounding (3–5 weeks)

1. Add `debugger` as an optional permission, requested only when advanced control is enabled.
2. Implement attach/detach lifecycle, target/frame inventory, Input actions, screenshots, and navigation signals.
3. Combine DOM/a11y locators with CDP input and vision fallback.
4. Preserve the existing DOM executor as a fast path and compare both in A/B traces.

Exit gate: materially lower no-effect rate across controlled inputs, iframes, popups, and complex widgets.

### Phase 3 — Durable autonomous loop (3–4 weeks)

1. Consolidate task, mission, approval, and execution state into one durable ledger.
2. Add checkpoint/resume, idempotency, bounded automatic retries, and explicit completion validators.
3. Auto-run only low-risk reversible steps; pause at policy boundaries.

Exit gate: long workflows resume after extension/service restart without duplicate side effects.

### Phase 4 — Tool routing and isolation (4–6 weeks)

1. Add structured web/search and connector/API routes for tasks that do not need GUI control.
2. Add an isolated managed-browser mode for untrusted research and logged-out exploration.
3. Consider native messaging only for capabilities that cannot safely live in the extension/backend boundary.

Exit gate: router chooses the lowest-risk adequate tool and can explain that choice in traces.

### Phase 5 — Production evidence (continuous)

1. Expand disposable-account live evaluations.
2. Red-team prompt injection, cross-origin leakage, account confusion, and confirmation bypass.
3. Roll out capabilities independently behind measurable gates.
4. Remove or archive parallel scaffolding that does not improve end-to-end results.

## 8. Immediate keep/change/remove decisions

### Keep and deepen

- real signed-in Chrome session as a deliberate user-visible mode;
- MV3 side panel and service-worker boundary;
- DOM/a11y extraction, resilient locators, widget/rich-text adapters;
- multi-tab workspace and post-action verification;
- typed planner outcomes and explicit ask/report/replan states;
- server-side model keys, trace tooling, and end-to-end Playwright harness.

### Change next

- replace planner-declared safety with executor-enforced policy authorization;
- add optional CDP control and screenshot grounding;
- consolidate volatile/parallel stores into one durable ledger;
- make capability status derive from executed evaluations;
- separate production UI from stub enterprise/product demos;
- replace broad required host access with optional origin grants where feasible.

### Stop or defer

- new governance/intelligence modules that are not wired into the live loop;
- claims of universal human equivalence;
- desktop-wide control until browser-only security and reliability gates pass;
- a native host with general shell/file access;
- training/fine-tuning before failure traces show that prompting, grounding, tools, and policy are no longer the bottleneck.

## 9. Honest product goal

The defensible goal is:

> Build a browser agent that can complete a continuously expanding, explicitly tested set of web tasks across user-visible Chrome and isolated browser modes, with verified outcomes, least-privilege access, safe handoff, and bounded autonomy.

No extension can literally perform everything a human can do. Browser and OS security boundaries intentionally block browser chrome, some native dialogs, CAPTCHAs, hardware-backed authentication, closed shadow roots, inaccessible canvases, DRM surfaces, and cross-origin data. Websites change, automation is blocked, and some actions legally or ethically require a person. Robustness comes from explicit capability contracts and graceful handoff—not pretending those boundaries do not exist.

## 10. Source boundary

All OpenAI product claims above come from official OpenAI documentation, product announcements, or the official system card. Chrome implementation guidance comes from Chrome for Developers. The reconstructed diagrams and recommendations are explicitly identified as inference. No private OpenAI code, prompts, weights, or internal documents were available or claimed.
