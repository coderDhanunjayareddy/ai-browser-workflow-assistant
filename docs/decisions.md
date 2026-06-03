# Engineering Decisions — AI Browser Workflow Assistant

## ADR-001: Chrome Extension MV3 as primary interface
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Use Chrome Extension Manifest V3 as the browser interface layer.

**Reason:** Direct access to any page's DOM without the user navigating to a specific app URL. Web apps cannot read or interact with other tabs. MV3 is required by Chrome for all new extensions.

**Alternatives considered:**
- Standalone web app with Playwright remote browser: far more complex, requires session/cookie sharing
- Browser bookmarklet: no persistent UI, severely limited capabilities

**Tradeoffs:** MV3 service workers have short lifetimes and no persistent in-memory state. Mitigated by using chrome.storage.session for state persistence.

---

## ADR-002: Side Panel over Extension Popup
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Use the Chrome Side Panel API for the extension UI.

**Reason:** Extension popups close when the user clicks elsewhere on the page, destroying all workflow state. Side Panel persists alongside the active tab, which is essential for multi-step workflows.

**Alternatives considered:** Popup with state serialized to storage on every change — too fragile, poor UX.

**Tradeoffs:** Requires Chrome 114+. Older Chrome versions not supported. Acceptable for production target.

---

## ADR-003: FastAPI for backend
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Use FastAPI (Python) as the backend framework.

**Reason:** Async by default, Pydantic schema validation natively integrated, auto-generated OpenAPI docs, minimal boilerplate, natural fit with Python AI/ML ecosystem.

**Alternatives considered:**
- Express.js: valid, but Python is preferred for AI service integration
- Django: too heavy for an API-only service

**Tradeoffs:** Python GIL limits CPU-bound concurrency. Not a concern for this I/O-bound workload.

---

## ADR-004: Gemini API called server-side only
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Gemini API is called only from the FastAPI backend. The extension never calls Gemini directly.

**Reason:** Chrome extension source code is visible to any user who inspects the extension. An API key in extension code is effectively public. Backend is the only safe place for API keys.

**Alternatives considered:** Extension calling Gemini directly — rejected on security grounds.

**Tradeoffs:** Every AI call requires a round-trip to localhost backend (~100-200ms additional latency). Acceptable.

---

## ADR-005: PostgreSQL over SQLite
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Use PostgreSQL for persistence.

**Reason:** Production-ready from day 1. SQLite has write concurrency limitations and would require migration later. The preferred stack already includes PostgreSQL.

**Alternatives considered:** SQLite — simpler for local dev but not production-ready.

**Tradeoffs:** Requires a running PostgreSQL instance for development. Mitigated by providing docker-compose.yml in Phase 1.

---

## ADR-006: No Playwright in MVP
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Defer Playwright integration to Phase 5+. MVP uses extension content scripts for all browser actions.

**Reason:** Extension content scripts have direct DOM access and are sufficient for all MVP actions (click, fill, scroll, navigate). Playwright would require a server-side browser instance with session/cookie synchronization — significant complexity with no MVP benefit.

**Alternatives considered:** All actions via server-side Playwright from day 1.

**Tradeoffs:** Content scripts cannot handle everything Playwright can (multi-tab, file downloads, network interception). These are post-MVP requirements.

---

## ADR-007: No WebSockets in MVP
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Use standard HTTP request/response. No WebSockets or SSE.

**Reason:** Every AI analysis is user-triggered. There is no server-initiated push in MVP. WebSockets add connection management complexity with no benefit in V1.

**Alternatives considered:** SSE for streaming AI response text.

**Tradeoffs:** AI response appears all at once (no streaming). Acceptable in V1.

---

## ADR-008: Vite + CRXJS for extension build
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Use Vite with the @crxjs/vite-plugin for the extension build pipeline.

**Reason:** CRXJS handles MV3 service worker bundling, content script injection, and hot-reload during development. Webpack alternatives require significantly more manual configuration for MV3.

**Alternatives considered:** Webpack with custom MV3 config, Parcel.

**Tradeoffs:** CRXJS is a community plugin, not Google-maintained. It is mature and widely used in production extensions.

---

## ADR-009: Single-user localhost backend for MVP
**Date:** 2026-05-12
**Status:** Accepted

**Decision:** Backend runs on localhost only in MVP. No authentication, no multi-user.

**Reason:** Simplest deployment. Avoids auth complexity (JWT, sessions, OAuth) that adds nothing to V1 feature validation.

**Alternatives considered:** Cloud-hosted backend from day 1.

**Tradeoffs:** Not suitable for sharing with other users. Authentication introduced post-MVP when deployment requirements are known.

---

## ADR-010: Use chrome.scripting.executeScript instead of declarative content scripts
**Date:** 2026-05-16
**Status:** Accepted (supersedes content script approach from Phase 2 initial design)

**Context:** Phase 2 initially used a declarative content script (`content/index.ts` injected via `manifest.json`) that imported `extractor.ts` and listened for messages. This caused the error "Could not establish connection. Receiving end does not exist."

**Root causes identified:**
1. `extractPageContext` referenced module-level constants and helpers (`INTERACTIVE_SELECTOR`, `buildSelector`, etc). When Chrome serializes a function for `executeScript`, the module scope is not included — those variables are undefined at runtime.
2. CRXJS v2 beta does not reliably bundle content scripts with ES module imports into a single IIFE. The `import { extractPageContext }` in `content/index.ts` caused the content script to fail silently on load, so the message listener was never registered.
3. The nested async callback pattern in the service worker (tabs.query → tabs.sendMessage) is unreliable because the MV3 service worker can be killed between the two async operations.

**Decision:** Use `chrome.scripting.executeScript({ func: extractPageContext })` from the service worker directly. The `extractPageContext` function is rewritten to be fully self-contained (all constants and helpers nested inside the function body) so it serializes correctly.

**Why this is better:**
- Eliminates injection timing issues — no content script needs to be pre-injected
- Eliminates ES module bundling dependency for extraction
- Single `await` instead of nested callbacks — clean async/await
- `scripting` + `activeTab` is a narrower permission footprint than `<all_urls>`

**Alternatives considered:**
- Fixing CRXJS bundling config to force IIFE output for content scripts — too fragile with a beta plugin
- Using `executeScript({ files: [...] })` — requires knowing the compiled output filename which changes with CRXJS versions

**Tradeoffs:** `extractPageContext` cannot use module-level scope. All helpers must live inside the function. This is enforced by a comment at the top of `extractor.ts`.

**Affected files:** `manifest.json`, `service-worker.ts`, `content/extractor.ts`. `content/index.ts` is now inactive and can be deleted.

---

## ADR-011: host_permissions instead of activeTab-only for scripting
**Date:** 2026-05-16
**Status:** Accepted

**Context:** `chrome.scripting.executeScript` with only `activeTab` permission requires the user to have clicked the toolbar icon as the direct trigger for the current service worker call. When the side panel is restored from a previous session, or the user navigates to a page without re-clicking the icon, `activeTab` is not granted for that tab and `executeScript` throws "Cannot access contents of url."

**Decision:** Add `host_permissions: ["http://*/*", "https://*/*"]` to the manifest. This grants stable scripting access to any http/https page regardless of how the session started.

**Why `activeTab`-only is wrong for this product:** `activeTab` is designed for one-shot toolbar actions (translate this page, capture screenshot). A persistent side panel assistant needs to read whatever page the user is on throughout the session — not just immediately after clicking the icon.

**Trade-off:** Chrome displays "Read and change all your data on websites" during installation. This is standard and expected for browser assistant extensions (Grammarly, Notion Clipper, etc.). The permission is limited to http/https — chrome:// pages remain inaccessible by design.

**Affected files:** `manifest.json`
