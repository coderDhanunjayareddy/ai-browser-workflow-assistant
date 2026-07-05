# Observation & Grounding Architecture

**Status:** Architecture document. Design only — no code, no pseudocode, no estimates, no milestones.
**Scope:** everything that happens **before** the planner reasons — from raw DOM to the candidate list the planner receives. Reasoning, reflection, execution, and recovery are treated as consumers of this subsystem's output, not redesigned here.
**Evidence base:** the grounding investigation established that Grounding is the current largest bottleneck and is **not one defect** — it is three independent failures at three different layers: **extraction coverage** (accordion `<summary>` elements never extracted), **ranking** (Amazon's correct search-submit button scored 4 vs. a decoy's 16, because the ranker never reads the selector string or the element's action-fitness), and **representation** (eleven Amazon add-to-cart buttons are literally indistinguishable to the ranker — an exact 26-point tie broken only by incidental DOM order). This document designs a layered pipeline in which each of those three failures has exactly one home, and no home is asked to do more than one job.

---

## Part 1 — Layer responsibilities and contracts

Seven layers, each with one job, one input contract, one output contract. No layer may perform another's job as a side effect — the investigation's central lesson is that today's single monolithic `extractor_v2.ts` + `RelevanceRanker` conflates several of these, which is precisely why a coverage gap (accordion), a scoring gap (Amazon), and a disambiguation gap (add-to-cart) all hid inside "the extractor" and "the ranker" as if they were one problem.

| Layer | Responsibility | Consumes | Produces | Must NOT do |
|---|---|---|---|---|
| **DOM Extraction** | Walk the complete render tree — including shadow roots and same-origin-permitted iframes — and record every node's raw structural facts: tag, attributes, text content, computed geometry, computed visibility. | The live document | A structural node inventory | Decide what is "interactive" or "important" (that is premature judgment two layers early) |
| **Accessibility Extraction** | Compute each node's **accessible role, accessible name, accessible description, and interaction state** using the full accessible-name/role computation (native semantics, ARIA attributes, `aria-labelledby`/`aria-owns` references, associated `<label>`s, descendant `alt` text, `title` fallback) — not a shortlist of attribute checks. | The structural inventory | Role/name/description/state per node | Decide relevance, ranking, or candidacy — this layer answers "what is this, accessibly," not "does it matter" |
| **Semantic Representation** | Fuse structure + accessibility into **meaning**: form membership, table membership (with row/column position), list/repeated-group membership, disclosure state (summary/details, expandable regions), section/landmark and nearest-heading association, nearby-label association. | Structural + accessibility data | A semantic page model | Decide which elements are candidates, or how they should be ordered |
| **Candidate Generation** | Decide, from the semantic model, which nodes are **eligible for planner consideration at all** — interactivity determination. Coverage-first: a node omitted here can never be recovered downstream. | The semantic page model | A candidate set (unranked, uncompressed) | Rank, deduplicate, or filter for relevance — that is over-reach into Ranking's job |
| **Candidate Ranking** | Order the **entire** candidate set by relevance to the current task. Produces a complete ordering; loses no candidate. | Candidate set + task + (optionally) working-memory signal | A ranked candidate list, same cardinality as the input | Truncate, group, or compress — ranking answers "in what order," not "how much fits" |
| **Candidate Compression** | Fit the ranked list into a token budget **without discarding coverage silently** — grouping duplicates, summarizing repeated structures, budgeting across categories rather than truncating by raw rank alone. | The ranked list + a budget | A bounded candidate representation | Re-rank, or decide interactivity — compression is a budget operation over an already-correct ordering |
| **Planner Input** | Render the compressed representation into the planner's actual input — text/JSON formatting, selector display convention, instructional framing. | The compressed representation | The literal planner-facing content | Decide which elements appear or in what order — purely presentational |

The contract discipline is the point: **DOM Extraction cannot fix a ranking problem, and Ranking cannot fix a coverage problem** — which is exactly why the investigation found three defects that no single patch could address at once.

---

## Part 2 — Ideal internal element representation

Before the planner reasons, every candidate should carry a record substantially richer than today's `InteractiveElement` (which has `type, text, selector, visible, input_type, placeholder, role, aria_label, accessibility_name, state, bounding_box, element_id` — a reasonable start, but one selector, no context, no grouping, no geometry beyond a box).

**Identity**
- A stable element identifier (survives re-observation of the same underlying control across steps, where feasible)
- A **ranked list of selector candidates** (not one CSS string) — id, data-testid, aria-based, text-based, structural, xpath fallback, mirroring the already-built-but-dead `LocatorRanker` strategy ordering

**Structural**
- Tag name, DOM depth, ancestor-chain summary
- Shadow-root / iframe provenance (was this node reached by piercing a boundary, and which)

**Accessibility**
- Computed role (from the real accessible-role algorithm, not a tag-to-role guess table)
- Computed accessible name and description (full algorithm, not "check four attributes")
- State: checked, expanded, selected, disabled, readonly, pressed, current

**Content**
- Visible text, placeholder, current value (already established as necessary by the observation-completeness work)
- Alt text of any contained image, in case the accessible name derives from it

**Geometry**
- Bounding box
- Visibility: rendered, in-viewport, **occlusion-aware** (is anything else painted on top of this box's center point right now)

**Interactivity**
- Enabled/focusable
- Native interactive semantics vs. ARIA-widget-only vs. script-driven-only (three genuinely different confidence levels for "this is really actionable")

**Context** — the field class the add-to-cart investigation proved is structurally absent today
- Containing form (id/name)
- Containing table (id, row index, column index/header)
- Containing list (id, item index)
- Nearest section/landmark and nearest heading text
- Nearest distinguishing label or sibling content (e.g., the product title beside an "Add to cart" button)

**Grouping**
- Repeated-group identity (a stable marker that "this control belongs to the same structural pattern as N siblings")
- Ordinal position within that group

**Provenance**
- How the node was discovered (native DOM, ARIA widget pattern, shadow-pierced, iframe-crossed) and a confidence signal on the accessible-name computation, so downstream layers can weigh a low-confidence name differently than a high-confidence one

**Deliberately excluded from this record:** attempt/outcome history. Per-element history belongs to Working Memory's Episodic Attempt Ledger (the reasoning-feedback-loop architecture), not to the grounding record — grounding is a stateless, per-observation transformation; history is looked up by identity when Ranking needs it (Part 4, "negative evidence"), never stored here.

---

## Part 3 — Candidate Generation

**The accordion failure is a Candidate Generation defect, precisely located:** today's candidacy test is a hardcoded CSS tag/role allowlist (`INTERACTIVE_SELECTOR`), and `<summary>` simply is not on the list. This is not a scoring problem or a compression problem — the element never became a candidate at all, so no downstream layer ever had a chance to see it.

**Governing principles:**

- **Coverage-first.** Candidacy determination should be *inclusive by construction* — the cost of including a borderline element (it gets a low rank, gets compressed away if truly irrelevant) is recoverable. The cost of excluding it is not. Every other layer downstream can filter; this layer cannot un-drop.
- **Semantics-driven, not enumeration-driven.** Candidacy should follow from the Semantic Representation's own computed properties (does this node have an interactive accessible role; does it have native interactive semantics; does it participate in a known disclosure/toggle pattern) rather than a maintained list of tags and roles that must be manually extended every time a new HTML pattern is encountered. A tag allowlist is architecturally a promise to be incomplete forever — new component libraries and design systems invent new interactive patterns continuously; a semantics-driven test asks the accessibility tree the question directly instead of re-guessing it per tag.
- **Disclosure patterns as a first-class candidate class.** `<summary>`/`<details>`, `aria-expanded` triggers, and other show/hide controls are not incidental buttons — they are a distinct interaction class whose candidacy test should be explicit (does this node control the visibility of another node), not incidentally caught by a generic "clickable" heuristic.
- **Custom widgets via role, not markup shape.** A `<div role="button">`, a web-component's shadow-internal control, or a JS-framework's synthetic input must be discoverable through the accessibility computation (Part 1's Accessibility Extraction layer), because their *markup* gives no reliable signal — only their *computed accessible role* does.
- **Canvas and opaque regions must be surfaced as a fact, not silently produce zero candidates.** When a region of the page (a `<canvas>`, a WebGL surface, a proprietary rendering layer) has no accessible children at all, Candidate Generation should mark that region as **opaque-to-DOM-grounding** rather than simply contributing nothing. A planner (or a future capability, Part 10) that sees "there is a large interactive-looking region here with zero extractable candidates" is in a fundamentally different, more actionable position than one that sees nothing and has no way to know a gap exists.
- **Dynamic-DOM awareness as a property, not a one-shot scan.** Because Observation re-invokes this whole pipeline every step, ordinary dynamic content (autocomplete lists, freshly-opened modals) is naturally covered by re-observation. What candidate generation should additionally guarantee is that a *mutation triggered by the just-executed action* is reflected in the very next candidate set — i.e., candidacy is computed against the DOM as it exists *after* settling, not against a stale pre-action snapshot.

---

## Part 4 — Candidate Ranking

**The Amazon and add-to-cart failures are both Ranking defects, but different ones** — one is a missing-signal problem (the correct button had no way to score well because nothing looked at its selector or its action-fitness), the other is a missing-disambiguation problem (eleven correct-and-equal candidates need *something* other than the same four features to distinguish them). A production ranking system should weigh distinct, named properties — stated here as responsibilities, not formulas:

- **Semantic relevance** — does the element's *meaning* (its computed role and accessible name, not literal keyword overlap alone) relate to the task's intent. A control described only as "a search box" should be recognizable as task-relevant to a search goal even without the literal word "search" appearing verbatim.
- **Structural relevance** — does the element's *position in the page's semantic structure* (Part 2's context fields: is it in the primary content region vs. navigation/footer/advertising) make it a priori more or less likely to be the intended target, independent of its own label.
- **Task relevance** — does the *specific* task (not a generic category match) align with this exact element, using the task's own descriptive terms against the element and its context together.
- **Context relevance** — does the element's *neighborhood* (nearby label, containing form/table/list, sibling content) supply the disambiguating signal its own label lacks. This is the property the add-to-cart case proved is currently entirely absent: eleven identically-labeled buttons are only distinguishable by what is near them, and nothing today looks near them at all.
- **Action relevance** — does the element's *affordance* (native interactive semantics vs. decorative or navigational role) match the kind of action implied by the task. A `role="link"` decoy and a genuine submit control can carry similar text while being fundamentally different affordances for a "search" action — this is exactly Amazon's failure mode, and action relevance is the property that should have separated them.
- **Duplicate disambiguation** — when multiple candidates tie on every other property, ranking must resolve the tie using *meaningful* distinguishing information (ordinal position within a repeated group, a unique nearby anchor) rather than an incidental artifact of extraction order.
- **Negative evidence** — a candidate that scores well on every other property but has a *known bad outcome* recorded for this task (consumed from Working Memory's Episodic Attempt Ledger, per the reasoning-feedback-loop architecture — not owned or stored here) should be actively deprioritized at ranking time, the earliest point such information can act, rather than left for the planner to avoid unassisted or for reflection to catch after another failed attempt.
- **Interaction history** — the broader, non-negative counterpart: candidates matching a *pattern that has worked* earlier in this session (not just avoiding known failures) can be weighed favorably. Like negative evidence, this is consumed from Working Memory, not maintained by Ranking itself.

These properties are independent axes, not a single number — a production system's responsibility is to make all of them *available* as separate signals to whatever scoring mechanism is chosen, not to guarantee any particular combination. Today's four-feature formula (keyword overlap, visibility, "has a name," "has a selector") covers a thin slice of *semantic relevance* only, and touches none of the other seven properties — which is the structural reason it could not have resolved either failure, however its weights were tuned.

---

## Part 5 — Duplicate Handling

**How identical controls become distinguishable:** not by anything intrinsic to the control itself (by definition, if two controls are truly indistinguishable in isolation, no amount of re-scoring their own label/role/text will separate them) — but by the **context** Part 2 and Part 3 already establish as part of the record: each instance's containing repeated-group identity, its ordinal position within that group, and its nearest unique distinguishing anchor (a product title, a row's first-column value, a card's heading). The eleven Amazon add-to-cart buttons are identical as *buttons*; they are not identical as *"the add-to-cart control associated with product card N, titled X."* The second description is what grounding should produce, and it is only available if Semantic Representation has already computed group membership and Context has already captured the nearby anchor — duplicate handling does not invent new information at ranking time, it *uses* information that earlier layers are responsible for having captured.

**How repeated controls should be represented:** as a **group**, not as N flat, independently-listed, near-identical records. A group representation carries the shared pattern once (the common role, label, action semantics) plus a compact table of per-instance distinguishing values (ordinal, anchor text, selector). This serves two purposes at once: it gives the planner a structurally correct way to say "the one associated with the USB-C cable, not any of the others," and — as Part 6 develops — it is dramatically cheaper to represent within a token budget than eleven full element records that differ in only one field.

---

## Part 6 — Candidate Compression

The planner cannot receive thousands of elements; a budget is unavoidable. The investigation already showed what compression must **not** do: today's extractor caps at a flat 150 elements by DOM order, and the ranker's top-30 cut is a flat score threshold — both are single-dimension truncations that can silently discard the one candidate that mattered (the Amazon submit button fell outside the top-30 *because* its score was already wrong, but the truncation mechanism itself has no awareness that it might be dropping something structurally necessary).

**Governing principles:**

- **Compress after ranking, never instead of it.** Compression's only legitimate inputs are an already-correct ordering (Part 4) and a budget — it should never be asked to also decide relevance under time/token pressure.
- **Group-aware budgeting.** Because Part 5 establishes that repeated candidates should already be represented as groups, compression can budget *across groups*, spending a small, bounded amount of budget on each distinct interaction pattern rather than letting one duplicate-heavy cluster (eleven near-identical buttons) crowd out a lone, differently-scored, genuinely necessary control purely because there are more instances of the former.
- **Category coverage as a compression invariant.** Even under tight budget, compression should aim to preserve at least one representative of each plausible interaction-affordance category present in the currently relevant region (at least one visible form control, one visible primary action, one visible navigational option, etc.) rather than optimizing purely for the highest N raw scores, which can — as observed — coincidentally exclude an entire *category* of control if its instances all scored modestly.
- **Summarize, don't just cut.** For a duplicate group, representing it compactly (pattern once + a distinguishing table) is compression *without loss* of the group's members, in contrast to truncating the list and losing group members outright.
- **Statelessness.** Compression is a pure function of (ranked+grouped candidates, budget) — it carries no memory of its own and produces the same output for the same input every time, consistent with every other layer in this pipeline.

---

## Part 7 — Cooperation with the rest of the loop, without duplicated responsibility

- **Observation** (the broader capture-the-world-now concept) *invokes* this entire seven-layer pipeline once per step; it does not itself rank or compress. This pipeline, in turn, does not decide *when* to observe — that remains Observation's exclusive concern.
- **Working Memory** owns the Episodic Attempt Ledger. Ranking *consumes* negative evidence and interaction history from it (Part 4) but stores nothing itself — grounding is stateless within a step; memory is the stateful, cross-step layer. No duplication: history lives in exactly one place.
- **Reflection** decides whether to override or re-plan a candidate the planner chose; it does not re-implement grounding. If reflection determines the page state requires a fresh look, it *triggers* a new pass through this same pipeline — it does not maintain a parallel grounding mechanism of its own.
- **Recovery**'s diagnoses (outside-viewport, overlay-intercept, wrong-element-type, and the rest of the M2 taxonomy) are discovered *reactively*, at execution time, today. This architecture's geometry (occlusion-aware visibility) and action-relevance (affordance-vs-task-implied-action) fields mean some of those same facts are, in principle, *already knowable* at grounding time — grounding's role is to **supply** those facts as candidate properties; deciding what to do when an action still fails despite them remains Recovery's exclusive responsibility. Grounding describes the world; Recovery reacts to a failure to act on it.
- **Planner** is a strict consumer of Planner Input's final rendering. It does not re-rank, re-filter, or infer missing candidates — if the planner needs something not present, that is by definition a Candidate Generation coverage gap to close upstream, never a planner-side workaround to invent.
- **Execution** consumes the chosen candidate's selector-candidate list (Part 2) to actuate the action; it does not decide which candidate to use, only how to interact with the one it is given.
- **Validation** independently compares before/after page state; it may itself *invoke* a fresh pass through this pipeline to obtain the "after" candidate set for comparison, but its judgment (did the goal advance) is separate from and does not feed back into grounding's own judgment (what exists and how relevant is it).
- **Benchmark** consumes this pipeline's output purely as data to measure and replay, exactly as the reasoning-feedback-loop architecture already establishes for the loop generally — a mirror, never an influence.
- **Trace Framework** records this pipeline's intermediate artifacts (candidate counts per layer, ranking scores, compression decisions) as additive observability, the same pattern already used for the planner/executor/validation stages — grounding does not need to be aware it is being traced.

---

## Part 8 — Compatibility analysis

**Unchanged:**
- `AnalyzeRequest` / `AnalyzeResponse` / `PriorStep` wire schemas — this architecture concerns what happens *before* a planner call is assembled, not the wire format itself.
- `POST /analyze`, and the extension ↔ backend and benchmark ↔ backend contracts generally.
- `InteractiveElement`'s existing fields remain valid; the richer representation in Part 2 is additive, in the same spirit the `state: dict` field already proved (M1.2) — new information rides inside an already-flexible container rather than requiring a schema break.

**What evolves (conceptually — not designed here):**
- `extractor_v2.ts`'s tag-allowlist-driven `INTERACTIVE_SELECTOR` becomes a properties-driven Candidate Generation test (Part 3).
- `RelevanceRanker`'s four-feature formula becomes a system weighing the eight properties of Part 4.
- The already-built-but-orphaned `website_intelligence` engine is the natural home for Semantic Representation (Part 1) — it already computes form/table/dialog/navigation structure; this architecture gives that existing, currently-isolated capability an explicit, load-bearing place in the live pipeline rather than inventing a new semantic layer from nothing.
- The already-built-but-orphaned `locator_engine.LocatorRanker` is the natural home for the "ranked selector candidates" field in Part 2 — again, reuse of existing, currently-dead work rather than new construction.

**Backward compatibility:** a caller unaware of the richer pipeline (an older extension build, or the benchmark's synthetic-mode injected script) still receives a valid, if less complete, candidate list at every stage — each layer is an enhancement over a base contract, not a hard new requirement the whole system must adopt atomically.

---

## Part 9 — Generalization analysis

Every property this architecture adds is a **generic, cross-site, structurally-computable fact** — an accessible name, a bounding box, a table-row index, a repeated-group ordinal — never a domain name, a specific CSS class, or hardcoded text. That is what makes the following claims hold without site-specific logic:

- **Amazon / Flipkart / Booking** (dense e-commerce, decoy-rich, duplicate-heavy) — directly addressed by both defects found: accurate accessible-name computation surfaces label-less-but-real controls (the Amazon submit button pattern generalizes to every icon-only or JS-driven affordance across all three sites), and group/context-aware disambiguation resolves repeated product-card controls (the add-to-cart pattern is architecturally identical to any product grid, any hotel-result list, any search-result list).
- **GitHub** (ARIA-heavy developer tooling, controls styled to look like other control types) — addressed by role computed from the real accessibility algorithm rather than tag-based guessing, which identifies a `<button>` masquerading with input-like `aria-label` text *as a button* at grounding time, rather than only discovering the mismatch reactively when a `fill()` fails.
- **LinkedIn** (feeds, infinite dynamic content, many structurally similar cards) — a feed of posts is, for grounding purposes, the same shape as a product grid: many near-identical repeated candidates needing the same group/ordinal/anchor disambiguation designed in Part 5.
- **Government portals** (older markup, sparse ARIA, table-based layout) — addressed by table/form-association context computation and full accessible-name fallback algorithms (including table-header association), which recover structure that a shallow heuristic misses regardless of how dated the markup is.
- **Banking sites** (heavy custom-styled controls, security-modal-heavy) — addressed by role/semantics-driven candidate generation (Part 3) rather than native-tag reliance, since custom `<div>`-based controls are common here, and by occlusion-aware visibility for the frequent overlay/modal security patterns.
- **SaaS dashboards** (data-dense, grid/table-heavy, icon-only actions) — addressed by table/list association context plus full accessible-name computation for icon-only controls — the same generalization of the Amazon submit-button pattern.
- **Unknown future websites** — the architecture's generalization claim rests on a single property: every layer computes something that is *objectively true of the page* (its real accessibility tree, its real semantic structure, its real geometry, its real repeated-group relationships) rather than encoding an assumption about how any particular site's authors chose to write their markup. A pipeline that asks "what is this, accessibly and structurally" generalizes by construction to any HTML that follows the same underlying web platform; a pipeline that asks "does this match a maintained list of known patterns" does not.

---

## Part 10 — Future evolution: connection points only

The organizing principle, carried over from the reasoning-feedback-loop architecture's own closing thesis: **every future capability should plug into an existing layer's contract by enriching one of its inputs or outputs — never by requiring a new pipeline stage or a parallel path.** Applied here:

- **Vision** — connects at **Candidate Generation** (as a supplementary source of candidates for regions Part 3 already flags as opaque-to-DOM-grounding — canvas, WebGL, proprietary rendering) and at **Candidate Ranking** (visual salience as one more relevance property, Part 4). Vision-derived candidates should conform to the *same* element representation (Part 2) so nothing downstream needs a parallel format.
- **OCR** — connects at **DOM/Accessibility Extraction** as a fallback text source when no accessible name exists (image-only or canvas-rendered text) — it fills the *same* text/accessible-name fields already defined, not a new field.
- **DOM embeddings** (learned semantic similarity in place of literal keyword overlap) — connects at **Candidate Ranking** as an additional or replacement mechanism for the *semantic relevance* property specifically (Part 4) — the layer's contract (consume candidates + task, produce an ordering) is unchanged regardless of what computes the ordering internally.
- **Learning** (cross-task, cross-site priors — e.g., recognizing a recurring decoy pattern) — connects at **Candidate Ranking**'s *negative evidence* and *interaction history* properties, the same connection point the reasoning-feedback-loop architecture identifies for long-term memory generally. Ranking *consumes* learned priors; it does not own or accumulate them.
- **Site adapters**, if ever reintroduced — connect only as an *optional bias fed into Candidate Ranking*, never as a replacement for Candidate Generation's coverage or a parallel execution path. This preserves the project's standing principle (established well before this document) that per-site logic must be a hint layered on a generic pipeline, never the pipeline itself.
- **Accessibility improvements** (e.g., consuming the browser's own accessibility tree via a native protocol instead of a hand-rolled computation) — connects as a direct internal upgrade to **Accessibility Extraction**; its output contract (role, name, description, state) is unchanged, so nothing downstream is aware the upgrade happened.
- **Multi-modal grounding** (combining DOM identity with pixel coordinates for a single action) — connects at the **Planner Input / Execution boundary**, consuming the geometry field that Part 2 already defines as part of every candidate's record, rather than requiring a new representation to be invented later.

---

## Closing statement

The investigation's finding — that Grounding is not one problem but (at least) an extraction-coverage defect, a ranking defect, and a representation defect, living in what today is one undifferentiated extractor-plus-ranker — is itself the argument for this document's structure. A pipeline with seven distinct, single-responsibility layers, each with a clean contract to its neighbors, ensures that a future coverage gap, scoring gap, or disambiguation gap is locatable in exactly one place, fixable without touching the other six, and — because every property added is a generic fact about arbitrary HTML rather than a fact about any one website — improves every site that exhibits the same *structural* pattern, not the one site where the pattern was first observed.
