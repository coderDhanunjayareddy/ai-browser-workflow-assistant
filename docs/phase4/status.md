# Phase 4 — Tool routing and isolation

Status: **implemented and verified for the live assist/backend routing path**  
Date: 2026-08-17

## Risk-first router

Every routed request now evaluates the same ordered candidates and selects the lowest-risk adequate tool:

| Risk | Route | Intended use |
|---:|---|---|
| 0 | `context_answer` | Answer from already supplied page context |
| 1 | `structured_search` | Logged-out web research without GUI control |
| 2 | `connector_api` | Connected read-only API operations |
| 3 | `isolated_browser` | Dynamic, logged-out, untrusted exploration |
| 4 | `user_session_browser` | GUI work or the user's authenticated session |
| 5 | `native_messaging_handoff` | Separately reviewed native-only capability |

Each decision records every candidate, adequacy, risk score, rejection reason, selected route, and a human-readable explanation. `/assist` returns this trace and the side panel displays it in an expandable **Route** note.

## Structured and connector routes

The backend exposes:

- `POST /tool-routing/route` — explain a decision without executing it;
- `POST /tool-routing/search` — use the structured DuckDuckGo provider;
- `POST /tool-routing/connector` — execute a registered read-only connector operation;
- `GET /tool-routing/traces/{trace_id}` and `GET /tool-routing/traces` — inspect bounded route traces.

Mutating connector calls fail closed until they are bound to the Phase 1 action policy and explicit approval flow.

## Isolated managed browser

`POST /tool-routing/isolated/research` launches a fresh headless Chromium context for one request and closes it afterward. It has:

- no user cookies or profile;
- no stored authentication state;
- downloads disabled;
- extensions absent;
- service workers blocked;
- bounded time and extracted text;
- public HTTP/HTTPS-only navigation;
- DNS/IP checks that reject localhost, private, link-local, and reserved destinations on the main request and browser subrequests.

This mode is suitable for logged-out research and untrusted exploration. It is not represented as a hardened multi-tenant OS container.

## Native messaging decision

The extension does **not** request `nativeMessaging`. The router can only return a non-executing handoff for these narrow capability classes:

- a user-selected local file;
- an OS keychain reference;
- an enterprise device certificate.

Arbitrary OS control is rejected. A native host would require separate threat modeling, packaging, signing, policy integration, and user approval before implementation.

## Exit-gate evidence

The Phase 4 suite verifies lowest-risk selection, complete candidate explanations, trace retrieval, structured/API routing, connector mutation blocking, native allowlisting, ephemeral browser settings, cleanup, and private-network blocking.

Verification commands:

```text
cd backend && .venv-codex/Scripts/python.exe -m pytest tests/unit/test_phase4_tool_routing.py -q
cd extension && node --test --test-concurrency=1 tests/*.test.cjs
cd extension && npm run type-check
cd extension && npm run build
```

Current verification result: **158 extension tests passed**, **199 Phase 1/Phase 4 policy-routing tests passed**, **47 Assist/research integration tests passed**, TypeScript passed, Python compilation passed, and the production extension build passed.

Live backend check: `Research browser automation standards` selected `structured_search` at risk 1 and returned all six candidate explanations from the running API.

## Live check

1. Reload extension version **0.4.0** from `extension/dist`.
2. Open **Assist** and ask: `Research browser automation standards`.
3. Expand the returned **Route** note. It should select `structured search` and explain why browser control was unnecessary.
4. Send `Summarize this page`. It should select `context answer` at risk 0.
5. Inspect the same trace through `GET /tool-routing/traces/{trace_id}` if deeper diagnostics are needed.
