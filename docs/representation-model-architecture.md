# Representation Model Architecture

> Status: architecture design. No code, no milestones, no estimates.
> Scope: the model that sits between raw page observation and the planner.
> Grounding: every claim traces to the evidence phase recorded in
> [`observation-grounding-architecture.md`](observation-grounding-architecture.md)
> and the four benchmark failures analysed there (Amazon submit, Amazon
> Add‑to‑Cart duplicates, Accordion `<summary>`, GitHub search input).

---

## 0. Why this document exists

The investigation established a precise gap. Today an element is a **flat bag of
attributes**, and those attributes cover only four of the eight information
categories a browser agent needs:

| Category | Modeled today? | Evidence |
|---|---|---|
| Identity | ✅ | `element_id`, `selector`, `type` |
| Appearance | ✅ | `text`, `visible` |
| Accessibility | ✅ | `role`, `aria_label`, `accessibility_name`, `placeholder` |
| Geometry | ✅ | `bounding_box` |
| Interaction | ⚠️ partial / accidental | `state`, `input_type:"submit"` — captured but unsurfaced, sometimes corrupted (`role:"textbox"` on a submit control) |
| Semantics | ⚠️ accidental leakage only | no purpose field; leaks weakly via `role`/`type` |
| Relationship | ❌ absent | no field on any of 150 elements references another element |
| Context | ❌ absent | no element references its surrounding section/record |

Three of the four remaining failures converge on the **same** absent categories —
Relationship and Context — because in each case the correct control is
semantically blank (`text`/`aria`/`name` all empty) and is identifiable only by
*what it belongs to*: a form, a product card, a trigger widget. The fourth
(accordion) was a different problem — element *existence*, already resolved.

This document designs the complete model. It does not say how to build it.

---

## 1. What is an InteractiveElement?

**Today:** an InteractiveElement is a self-contained record — a dictionary of
intrinsic attributes with no awareness that any other element exists.

**Proposed:** an InteractiveElement is a **node in a typed observation graph**.
It carries its own intrinsic properties *and* participates in typed, directional
**relationships** to other nodes and to **container** nodes (forms, tables,
cards, dialogs, menus, tabs, lists, accordions, trees, groups). Its meaning is
no longer purely intrinsic — it is partly defined by its edges and its container.

The essential shift: an element stops being *"a thing on the page"* and becomes
*"a thing on the page, in a place, that does something, to something."*

Two consequences that the whole design turns on:

- **An element's identity is intrinsic; its purpose is often relational.** A blank
  submit `<input>` means nothing alone. It means "submit the search" only via its
  membership in the search form. Purpose must be derivable from structure, not
  demanded from labels the page never provided.
- **The graph is a superset, not a replacement.** The current flat list is one
  *projection* of the graph (nodes only, edges dropped). Backward compatibility is
  preserved by keeping that projection available (see §8).

---

## 2. What information belongs *inside* an element (intrinsic)

Intrinsic properties are those knowable from the element itself, independent of
any other element. They are grouped by the category vocabulary the investigation
fixed:

- **Identity** — what distinguishes *this* element from every other, and how to
  re-find it. Includes a stable **fingerprint** (a re-identification signal that
  survives minor DOM churn) in addition to the brittle CSS `selector`. Identity
  answers "is this the same element I saw last step?"
- **Appearance** — what a human sees: visible text, rendered visibility, relative
  visual prominence. Appearance answers "what does it look like / say?"
- **Accessibility** — the accessibility-tree view: role, accessible name,
  accessible description, and ARIA states. This is a *declared* view and may be
  absent, partial, or wrong — it is one input, never the sole arbiter.
- **Geometry** — position and size in the viewport, and viewport relation
  (in/above/below the fold). Geometry answers "where is it, and can it be acted on
  without scrolling?"
- **Interaction (affordance)** — *what the element does when acted on*: whether it
  activates, submits, toggles, edits, selects, or navigates; and whether it is
  currently enabled, disabled, read-only, checked, expanded, or holding a value.
  This is the category that today leaks through `input_type` and `state` but is
  **not modeled as affordance** and **not surfaced to ranking**. It belongs
  firmly *inside* the element because it is a property of the element's own type
  and current state.

Intrinsic explicitly **excludes** anything that requires knowing about a second
element. That is the boundary in §3.

---

## 3. What information belongs *outside* an element (extrinsic)

Extrinsic information is relational or environmental — it cannot be a property of
one element because it *is* a fact about two or more elements, or about the
element's surroundings. It must live outside the node and be *referenced*, never
*copied*, so the model has one source of truth:

- **Relationships** — typed edges between nodes (§4). "This control submits *that*
  form." "This cell belongs to *that* row." An edge is owned by the graph, not by
  either endpoint.
- **Containers / collections** — forms, tables, cards, dialogs, menus, tabs,
  lists, accordions, trees, groups (§5). A container is its own node; elements
  reference the container they belong to rather than duplicating its identity.
- **Context** — the surrounding meaning: the owning section/heading/landmark, and
  the specific **record** an element acts upon, e.g. the product card whose
  "Add to cart" this is (§6).

The design rule: **intrinsic facts are stored on the node; extrinsic facts are
stored as edges and container nodes and attached to the node by reference.**
This is what prevents the combinatorial bloat of copying a product title onto
every one of its twelve buttons, and what lets one product card serve as the
shared context for all controls inside it.

---

## 4. What relationships should exist between elements

Relationships are **typed and directional**. The type is what carries meaning;
an untyped "these two are near each other" edge would repeat today's failure of
leaving the planner to guess. The relationship vocabulary a general-purpose agent
needs, each justified by an observed failure or a common pattern:

- **labels / labelled-by** — a caption or `<label>` names a blank control. (Would
  give the Amazon submit and the GitHub input the names their own attributes lack.)
- **member-of** — a control belongs to a form / fieldset / group. (Turns "submits
  *something*" into "submits *the search form*.")
- **controls / triggers** — activating element A reveals, focuses, or toggles
  element B: a search button that reveals a search input, a menu button that opens
  a menu, a `<summary>` that discloses its panel, a tab that shows its panel.
  (Directly the GitHub trigger→input and the accordion disclosure relationship.)
- **contained-in / acts-on-record** — a control lives inside a repeating record
  (card, row, list item) and acts on that record. (The single relationship that
  distinguishes twelve identical Add-to-Cart icons: *which product*.)
- **row / column / cell membership** — table structure, so a cell is addressable
  as "the price cell of the HP row."
- **option-of / item-of** — an option belongs to a menu/combobox/listbox; an item
  belongs to a list or tree; a tree node has a parent node.
- **sibling-in-group** — peers within the same logical group (radio set, button
  group, pagination), so "the next one" and "the selected one" are expressible.
- **owns-state / described-by** — an element whose accessible state or description
  is provided by another node.

Every edge is a first-class, queryable fact. "Find the submit control of the form
that contains the focused search box" becomes a graph query, not a lexical guess.

---

## 5. How composite structures should be represented

Each composite is a **container node with a declared type and typed membership
edges to its parts**. The container is not a bounding box drawn around elements;
it is a semantic grouping with its own identity, so the planner can reason about
the whole ("this dialog", "this row") and the parts interchangeably.

- **Form** — container of its fields and its submit/reset controls; members carry
  `member-of` edges; the submit carries an affordance of "submits" *and* a
  `member-of` edge to this form. Resolves the Amazon case structurally.
- **Table** — container of rows; each row a sub-container of cells; cells addressed
  by (row, column). Enables record-relative extraction ("HP row → price cell").
- **Card / repeating record** — container representing one logical item (a product,
  a result, a post). Every control inside references the card, and the card carries
  the descriptive **context** (title, price) once. Resolves the Add-to-Cart case.
- **Dialog / popover / sheet** — a modal container with a trigger relationship from
  the element that opened it, and an "active/topmost" flag so the planner knows
  which surface currently owns interaction.
- **Menu / combobox / listbox** — a container of options with a trigger control and
  an expanded/collapsed state; options carry `option-of` edges.
- **Tabs** — a tablist container; each tab has a `controls` edge to its panel and a
  selected state.
- **List** — an ordered container of items; ordering is a first-class property so
  "first result" is expressible.
- **Accordion** — a set of disclosure pairs: each header (`<summary>` or ARIA
  disclosure button) has a `controls` edge to its region and an expanded state.
  Note the evidence: once the header is *extracted*, its text suffices — so the
  accordion's representation need is the disclosure *relationship*, while its
  historical failure was upstream *existence* (candidate coverage). The model must
  distinguish these two so neither masks the other.
- **Tree** — a hierarchy of nodes with parent/child edges, expanded state, and
  level, so navigation and "expand the parent of X" are expressible.
- **Group** — a generic labelled grouping (fieldset, radiogroup, toolbar, button
  group) for peers that share a label or purpose.

A single principle covers all ten: **the container carries the shared meaning
once; members reference it.** This is both the disambiguation mechanism and the
compression mechanism.

---

## 6. How surrounding context should be represented

Context is what a human reads *around* a control to know what it is for. Today it
exists only page-globally (`headings`, `content_blocks`) and is never attached to
any element. The design attaches context **by reference** at two granularities:

- **Structural context** — the nearest owning landmark / section / heading for each
  element (which region of the page it lives in). Answers "is this the site search
  or an in-page filter?"
- **Record context** — when an element lives inside a repeating record (card, row,
  list item), the record's descriptive content *is* its context, held once on the
  record node and shared by reference to every control inside it.

Context is **derived and attached, not duplicated**. An element points at its
section and its record; the descriptive text lives on those container nodes. This
keeps the model normalized and lets Compression decide how much context to inline
per element within budget (§7).

---

## 7. Which layer owns each responsibility

The failures were mislocated precisely because responsibilities were blurred. The
model assigns each responsibility to exactly one owner.

- **Observation** — *capture raw truth faithfully and completely.*
  Owns: intrinsic facts as the DOM/accessibility tree actually present them, and
  the *raw relational signals that already exist in the DOM* — form membership,
  label associations, `aria-controls`/`aria-labelledby`, container nesting, native
  control kind. Observation's mandate is fidelity: it must not flatten a submit
  control into a textbox, and it must not discard the affordance and membership
  signals the page already carries. Observation does **not** invent meaning.

- **Representation** — *normalize raw observations into the typed node+edge graph.*
  Owns: the node schema and category vocabulary, edge typing, container assembly,
  **derived Semantics** (naming a blank control by its role in its container), and
  context attachment. Representation is where "an `<input type=submit>` inside the
  search form" becomes "the search-submit control." It is the owner the
  investigation identified as the true root of the remaining failures.

- **Ranking** — *order candidates for a goal using the full representation.*
  Owns: relevance scoring across *all* categories — including interaction
  affordance, relationship, and context — so it is no longer forced to fall back on
  labeledness (the signal that was inverted on the Amazon page). Ranking consumes
  the graph; it does not repair it.

- **Compression** — *select and shape the minimal sub-graph the planner needs.*
  Owns: choosing which nodes, which of their edges, and how much attached context
  survive into the planner payload, within budget, without losing the relational
  facts that make a blank control interpretable. Compression decides *how much of
  the graph to show*, never *what is true*.

- **Planner** — *reason and decide over the representation.*
  Owns: action choice, disambiguation using relationships, and recovery using
  identity/context. The planner is a consumer of perception, never a source of it;
  no planner prompt change can substitute for a fact the lower layers never
  supplied.

The dividing line, stated once: **Observation captures, Representation organizes
and names, Ranking orders, Compression rations, Planner decides.** Every remaining
failure was a Representation gap being wrongly asked of Ranking or the Planner.

---

## 8. Compatibility with the existing architecture

The model is a **superset reachable additively**, not a rewrite:

- **The flat `InteractiveElement` list is preserved as a projection.** Existing
  consumers that read nodes-only continue to work unchanged; the graph adds edges,
  containers, and context *alongside* the current fields, not in place of them.
- **The two-executor fidelity discipline is unchanged in principle.** Whatever the
  extension's extractor observes, the benchmark's mirror observes identically; the
  drift-guard contract (the two must stay in sync) extends to any new observation
  signal rather than being weakened by it.
- **The compressed-context contract grows additively.** The planner-facing payload
  gains relational and context information as new, optional structure; the existing
  keys keep their meaning, so nothing that reads today's contract breaks.
- **Ranking keeps its interface.** It still takes a goal and candidates and returns
  an ordering; it simply has richer features to score on.
- **Derivations degrade gracefully.** When a relationship or container cannot be
  observed, the element falls back to exactly today's intrinsic-only record. The
  model never does *worse* than the current one; it only adds signal when signal
  exists.

Backward compatibility is therefore a property of the design, not an afterthought:
the graph with all edges removed *is* the current representation.

---

## 9. How this improves every website, not Amazon specifically

The model contains **no site-specific logic**. It improves outcomes by modeling
*categories of structure* that recur on every site:

- **Any unlabeled control in a form** (checkout buttons, login submits, search
  submits everywhere) becomes interpretable through `member-of` + affordance —
  Amazon was one instance of a universal pattern.
- **Any control inside a repeating record** (search results, feeds, tables, product
  grids, email lists) becomes disambiguable through `acts-on-record` + record
  context — the Add-to-Cart pattern is every list on the web.
- **Any reveal-then-act interaction** (search triggers, menus, modals, popovers,
  disclosures) becomes navigable through `controls`/`triggers` — the GitHub input
  and the accordion are the same shape as countless site menus and dialogs.
- **Any native or ARIA composite** (tabs, trees, comboboxes) gets a faithful
  structural representation instead of a scatter of disconnected nodes.

Because the unit of improvement is a structural category rather than a URL, one
model change raises capability across all sites that use that structure — which is
all of them. Site-specific tuning becomes unnecessary by construction.

---

## 10. How this supports future reasoning, reflection, validation, recovery, learning

A relational, typed representation is the substrate these capabilities need:

- **Reasoning** — the planner can justify a choice by structure ("this is the
  submit of the form containing the box I just filled") instead of by lexical
  coincidence, and can express goals relationally ("the price cell of the HP row").
- **Reflection** — stable **Identity fingerprints** let repeat-detection recognize
  "I acted on this same element again and nothing changed," which the current
  index-based identity cannot reliably do. Reflection gains a dependable notion of
  sameness.
- **Validation** — relationships supply grounded post-conditions: submitting a form
  should change the region that form owns; opening a dialog should make that dialog
  the active surface. Success/failure can be checked against expected structural
  change rather than raw text presence.
- **Recovery** — when a brittle `selector` goes stale, the element is still
  re-locatable by its role in the graph ("the submit control of the search form",
  "the Add-to-cart of the HP card"). Relationship and context become the durable
  handle that survives DOM churn.
- **Learning** — typed edges and derived semantics form a **stable vocabulary** to
  accumulate knowledge against. Site- and pattern-level lessons ("on this site the
  search submit is unlabeled and lives here") attach to structural facts that
  persist across sessions, rather than to selectors that rot. This is the
  connection point to the reasoning-feedback loop: an episodic ledger keyed on
  stable identity and relationship is one that can generalize.

---

## Summary

An InteractiveElement should be a **node in a typed observation graph**: intrinsic
properties inside it (Identity, Appearance, Accessibility, Geometry, Interaction),
relational and environmental facts outside it as **typed edges** and **container
nodes** with **attached-by-reference context** (Relationship, Context), and
**Semantics derived** from the two. Observation captures the raw signals
faithfully; Representation organizes and names them; Ranking, Compression, and the
Planner consume the result. The current flat list is the edge-free projection of
this graph, so the model is additive and never regresses. Because it models
recurring *structures* rather than specific sites, it lifts capability everywhere —
and because it is relational and identity-stable, it is the substrate on which
reflection, validation, recovery, and learning can finally stand.
