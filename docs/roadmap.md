# Roadmap — AI Browser Workflow Assistant

## V1 Phases

### Phase 1 — Project Foundation
**Status:** Complete
**Goal:** Runnable skeletons for both extension and backend.

Deliverables:
- Vite + CRXJS + React + TypeScript extension project
- manifest.json with sidePanel and activeTab permissions
- Side panel opens and renders "Hello" (proves build pipeline)
- FastAPI app on localhost:8000
- GET /health → {"status": "ok"}
- PostgreSQL connection verified
- .env.example with all variables documented
- docs/ folder initialized

Stop condition: Both processes run locally without errors.

---

### Phase 2 — Browser Context Extraction
**Status:** Complete
**Goal:** Extension reads current page and produces a structured snapshot.

Deliverables:
- extractor.ts: URL, title, interactive elements, headings, selected text
- Snapshot is structured and size-limited (not raw HTML)
- Side panel shows raw snapshot JSON (debug view)
- POST /analyze accepts AnalyzeRequest with page_context field

Stop condition: Side panel shows structured page data from current tab.

---

### Phase 3 — AI Analysis Engine
**Status:** Complete
**Goal:** Backend sends context + task to Gemini, returns structured action suggestions.

Deliverables:
- ai_service.py calls Gemini with system prompt + page context + task
- Response parsed into SuggestedAction[] with Pydantic validation
- context_service.py assembles prompt and validates response schema
- Side panel displays raw AI response (debug view)
- Error handling: malformed response, timeout, token limit

Stop condition: User types a task, AI returns structured action suggestion.

---

### Phase 4 — Approval Workflow
**Status:** Complete
**Goal:** User sees action cards and must explicitly approve before anything executes.

Deliverables:
- ActionCard.tsx: description, target, value, reasoning, confidence, safety badge
- Approve and Reject buttons
- Approval state managed in useWorkflow.ts
- Approved/rejected events logged to PostgreSQL
- Approved action passed to service worker (execution stub — logs "approved" for now)

Stop condition: User approves or rejects action, event is in DB.

---

### Phase 5 — Safe Browser Action Execution
**Status:** Complete
**Goal:** Approved actions are executed in the live browser.

Deliverables:
- executor.ts: click, fill, scroll, navigate
- Selector validation before use
- Element existence check before action
- Execution result returned to side panel
- ExecutionFeed.tsx shows live action log
- Backend logs execution result

Stop condition: User approves "click the login button," it actually clicks.

---

### Phase 6 — Workflow Persistence
**Status:** Complete
**Goal:** Workflow history stored and retrievable.

Deliverables:
- Full session + event log written to PostgreSQL
- GET /workflow/history returns last N sessions
- Side panel History tab shows past workflows

Stop condition: User sees past workflow history after reopening extension.

---

### Phase 7 — Multi-Step Workflows
**Status:** Complete
**Goal:** AI can suggest sequential actions; user approves one at a time.

Deliverables:
- Multiple suggested_actions in one AI response
- Side panel queues actions, shows one approval card at a time
- User can abort queue at any step
- Re-analyze after each step (page may have changed)
- Session context carries prior approved steps

Stop condition: User completes a 3-step workflow with approval at each step.

---

## Post-audit roadmap (real-world completion)

After the architecture review (`docs/architecture-review.md` → `-reconciliation.md` →
`-alignment.md`), the program is sequenced by measured real-world task completion:

- **M0 — Real Website Benchmark — IMPLEMENTED (2026-06-30).** `backend/benchmark/`,
  designed in `docs/benchmark-m0.md`. Drives the live `/analyze` loop against real sites +
  fixtures in two executor modes; emits JSON/MD/HTML + a locked baseline. Framework verified
  offline (35 validation checks, 63 tests, perf bench). **First real baseline pending** an
  operator run (`pip install -r requirements-benchmark.txt && playwright install chromium`,
  then `python -m benchmark.m0_runner --suite nightly --executor playwright`).
- **M1** — CDP trusted driver + shadow/iframe + ranked locators (gated by M0 baseline).
- **M2** — close the loop (validate → reflect → recover, risk-scoped approval).
- **M3** — wire website_intelligence + vision into in-loop perception.
- **M4** — merge mission/unified, multi-tab, persistence, learning layer.

## V2 Backlog (Out of scope for MVP)

- Playwright integration for server-side browser actions
- Multi-tab workflow coordination
- Workflow replay and templates
- Firefox/Edge support
- Authentication and multi-user support
- Streaming AI responses (SSE)
- Semantic search over workflow history
- Natural language workflow scheduling
