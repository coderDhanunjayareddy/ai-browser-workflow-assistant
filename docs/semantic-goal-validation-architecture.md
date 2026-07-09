# Semantic Goal Validation Architecture

**Status:** Architecture document. Design only; no implementation plan, no milestones, no estimates.
**Scope:** semantic goal completion and validation in the browser workflow loop.
**Evidence base:** `backend/benchmark/reports/planner-contract-v2-final.json`, the valid Planner Contract V2 nightly Playwright benchmark run with 54.5% completion. The remaining non-infrastructure workflow failures were:
- `youtube_com__video_search` - `TIMEOUT`
- `fixture__pagination` - `TIMEOUT`
- `flipkart_com__product_filter` - `STUCK`
- `github_com__pr_read_comments` - `FAILED/GROUNDING`

The dominant remaining bottleneck is not that actions fail to execute. It is that the loop does not consistently decide whether the original user goal has been achieved. In the YouTube task, search results and result titles were already visible, but the loop continued through repeated Report outcomes until max steps. In the pagination task, the click was treated as progress because the URL changed to `#`, even though the semantic page state stayed on page 1. In the Flipkart task, HP evidence became present in extracted interactive/content evidence, but the loop continued selecting irrelevant actions because the success criterion remained unsatisfied. These are convergence failures: action success, page change, planner confidence, and goal completion are not the same thing.

---

## 1. What Is a Goal?

A **Goal** is the user's requested end state, expressed independently of the actions that might achieve it.

It is not:
- the next browser action;
- the final URL alone;
- a successful click, fill, wait, or navigation;
- the planner's belief that the task is done;
- a benchmark criterion by itself.

It is the semantic condition that must become true in the world the browser exposes. For example:

| Task | Goal |
|---|---|
| YouTube search | Search results for "Python tutorial for beginners" are present. |
| Pagination fixture | Page 2 of the list is active and page 2 items are visible. |
| Flipkart filter | Laptop results are filtered or otherwise visibly narrowed to HP. |
| GitHub PR read | The target PR/comment content is available and the requested author/comment can be extracted. |

The Goal remains stable across the loop. Actions are attempts to satisfy it; Reports are claims that it is satisfied; validation is the independent judgment that connects evidence to the Goal.

---

## 2. What Evidence Proves a Goal Is Satisfied?

A Goal is satisfied by **semantic evidence**, not by action completion. Semantic evidence is observable browser state that directly supports the user's requested end state.

Evidence can come from the same canonical observation pipeline already used by Planner Contract V2:
- URL and title;
- visible text;
- content blocks;
- interactive element text, accessibility names, aria labels, state, and values;
- verified state facts;
- planner Report claims;
- prior attempt ledger entries.

Evidence must be tied to the original Goal. It is not enough for the page to change; the change must make the Goal true.

Benchmark examples:

- In `youtube_com__video_search`, the URL `search_query=Python+tutorial+for+beginners` plus visible/content evidence such as "Python Full Course for Beginners" and "Python for Beginners - Learn Coding with Python in 1 Hour" proved the search-results goal more directly than the previous action success did.
- In `fixture__pagination`, the click on `#p2` and URL hash change did not prove completion because snapshots still showed `Item A`, `Item B`, and `page 1`, while required evidence `page 2` and `Item C` was absent.
- In `flipkart_com__product_filter`, later snapshots contained HP evidence in interactive elements and result records, while the validator's checked visible text slice did not. That exposed a mismatch between available semantic evidence and the narrow criterion actually consumed.
- In `github_com__pr_read_comments`, the page title and DOM said "Page not found"; the target PR/comment content never became available. No action success on search controls could prove the original extraction goal.

---

## 3. Semantic Evidence vs. Action Success

**Action success** answers: "Did the browser operation execute?"

**Semantic goal satisfaction** answers: "Is the user's requested end state now true?"

They are related but separate:

| Signal | Meaning | Example |
|---|---|---|
| Execution success | The browser accepted the action. | Clicking `#p2` returned success. |
| Observable progress | Some page signature changed. | YouTube URL changed to a search URL. |
| Semantic evidence | Goal-specific facts are present. | YouTube results contain Python beginner videos. |
| Goal satisfaction | The evidence meets the original goal. | Search results for the requested query are present. |

The final benchmark shows both directions of mismatch:

- False action confidence: `fixture__pagination` clicked successfully, but the list stayed on page 1.
- False non-completion: `youtube_com__video_search` reached a result page with relevant result evidence, but the loop kept consuming Reports until timeout.
- Irrelevant progress: `flipkart_com__product_filter` repeatedly clicked "Laptops"; some clicks changed page signatures, but not toward the HP filter goal.

Validation must therefore judge semantic evidence directly. Action success is an input to the ledger, not a verdict on the Goal.

---

## 4. How Validation Consumes Planner Report Outcomes

Planner Contract V2 makes `Report` a first-class outcome. A Report is a **claim**, not completion.

Validation should consume a Report as structured semantic evidence:

- `answer`: the value or result the planner believes satisfies the Goal;
- `claim`: the planner's explanation of why the Goal is satisfied;
- current observation: the browser state from which the claim was made;
- prior ledger: the attempts that led to the claim.

The Report must be checked against the Goal using the same evidence model as action outcomes. The planner is allowed to say "the answer is already visible"; validation decides whether the claim is supported.

The benchmark demonstrates why this distinction matters:

- YouTube: repeated Reports likely indicated the planner recognized completion, but the orchestrator did not turn supported Report evidence into completion.
- Pagination: Reports after a failed semantic transition should not complete, because the observation still showed page 1.
- Flipkart: if HP appears in extracted element evidence, validation should consider that evidence; if the goal specifically requires the HP filter applied, validation must distinguish "HP product text exists" from "HP filter is active."

Report validation therefore has three possible outcomes:

| Outcome | Meaning |
|---|---|
| Verified | The Report is supported by current evidence and satisfies the Goal. |
| Refuted | Current evidence contradicts the Report. |
| Uncertain | Evidence is relevant but insufficient or ambiguous. |

Only Verified can terminate the loop.

---

## 5. Continue vs. Complete

The orchestrator owns loop termination. Planner outcomes, action results, and validation records all feed into one decision:

```
Observe -> Represent -> Rank -> Compress -> Planner Outcome
                                      |
                                      v
                              Semantic Validation
                                      |
                    +-----------------+-----------------+
                    |                                   |
                 Complete                            Continue
```

The orchestrator should decide **Complete** when:
- the original Goal is satisfied by validated semantic evidence; or
- a planner Report is verified against the current observation and Goal.

The orchestrator should decide **Continue** when:
- action execution succeeded but goal evidence is absent;
- the page changed but the Goal is not yet true;
- a Report is refuted or uncertain;
- evidence indicates progress but not completion;
- the current state contradicts the Goal.

The key architectural change is the order of authority:

1. The Goal is authoritative.
2. Evidence is evaluated against the Goal.
3. Planner outcomes and actions are interpreted through that evaluation.
4. The loop terminates only on validated Goal satisfaction.

This keeps the loop from treating action success as completion and from treating unverified Reports as completion. It also keeps the loop from ignoring supported Reports, which caused the YouTube-style timeout.

---

## 6. Representing Uncertainty

Validation should not collapse every non-complete state into failure. It should represent uncertainty explicitly.

Recommended validation states at the architecture level:

| State | Meaning |
|---|---|
| `satisfied` | Evidence proves the Goal. |
| `not_satisfied` | Evidence shows the Goal is not met. |
| `contradicted` | Evidence directly disproves the claim or expected state. |
| `uncertain` | Evidence is incomplete, ambiguous, stale, truncated, or conflicting. |

Uncertainty should carry:
- supporting evidence snippets;
- missing evidence;
- contradictory evidence;
- confidence;
- source fields used, such as URL, title, visible text, content blocks, or interactive elements.

Benchmark examples:

- `youtube_com__video_search`: evidence should not remain uncertain once result content blocks include relevant Python beginner result titles.
- `fixture__pagination`: evidence should be `not_satisfied` or `contradicted`, because the snapshot still says `page 1`.
- `flipkart_com__product_filter`: evidence may be uncertain if HP product results are visible but active filter state is not proven.
- `github_com__pr_read_comments`: evidence is contradicted at the start by "Page not found" for the target URL.

Uncertainty prevents both false completion and endless unsupported retries.

---

## 7. Preventing False Positives and False Negatives

### False Positives

A false positive occurs when the loop completes even though the Goal is not actually satisfied.

Prevention principles:
- Do not accept action success as goal satisfaction.
- Do not accept a URL change without semantic page evidence.
- Do not accept a Report unless the current observation supports it.
- Do not accept generic keyword presence when the Goal requires a specific state.

Evidence:
- `fixture__pagination` would be a false positive if `#p2` click success or URL `#` were accepted. The semantic evidence still showed page 1.
- `flipkart_com__product_filter` would be a false positive if any HP product mention were accepted as proof that the HP brand filter had been applied, unless the Goal definition permits result evidence as sufficient.

### False Negatives

A false negative occurs when the Goal is satisfied but the loop continues.

Prevention principles:
- Validate against all relevant observation fields, not only a narrow visible-text slice.
- Treat content blocks and accessibility names as first-class evidence.
- Let verified Reports terminate.
- Keep the Goal stable across attempts, so completion can be recognized even after non-action outcomes.

Evidence:
- `youtube_com__video_search` had relevant result evidence in content blocks and interactive elements but timed out after repeated Reports.
- `flipkart_com__product_filter` had HP evidence in later snapshots outside the visible-text slice used by the final criterion.

The architecture must balance both risks: stricter evidence for stateful goals, broader evidence intake for already-observed information.

---

## 8. Integration With Planner Contract V2

This architecture does not introduce a parallel loop. It extends the existing Planner Contract V2 flow by making semantic validation the single interpretation point for all outcome kinds.

Planner Contract V2 outcomes remain unchanged:

| Outcome | Validation role |
|---|---|
| Act | Validate whether the action changed evidence toward or into the Goal. |
| Report | Validate the claim against current evidence and the Goal. |
| Wait | Re-observe, then validate whether new evidence changes goal status. |
| Ask | Pause only if the missing information is required to evaluate or pursue the Goal. |
| Replan | Continue with a revised approach, but keep the original Goal as the completion target. |

Every outcome still becomes one attempt record in the same ledger. Semantic validation reads the same ledger and observation state; it does not create a second memory, second planner, or second success system.

The integration point is simple:

```
Planner Outcome -> Outcome-specific handling -> Semantic Goal Validation -> Orchestrator decision
```

For Act, validation is no longer limited to "did the action work?" It asks whether the Goal is now satisfied.

For Report, validation is no longer a no-action special case. It asks whether the Report is supported.

For repeated Reports, validation prevents timeout loops by resolving the Report as verified, refuted, or uncertain and making the orchestrator act on that result.

For failed actions, validation separates execution failure from goal failure. A failed click may still leave the Goal satisfied if the evidence is already present; a successful click may still leave the Goal unsatisfied if the evidence is absent.

---

## Architectural Thesis

The browser workflow loop should terminate on validated semantic satisfaction of the user's original Goal, not on action success and not on planner self-certification. Planner Contract V2 made non-action outcomes representable; semantic goal validation makes those outcomes convergent by evaluating Reports, actions, waits, and replans against one stable Goal and one shared evidence model.

