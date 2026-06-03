# Workflows — AI Browser Workflow Assistant

## Workflow 1: Single Action (Core MVP Flow)

```
User
  │
  │  Opens side panel on any webpage
  ▼
Side Panel (React)
  │
  │  User types: "Click the login button"
  ▼
useWorkflow.ts
  │
  │  sendMessage({ type: "EXTRACT_CONTEXT", tabId })
  ▼
Service Worker
  │
  │  chrome.tabs.sendMessage(tabId, { type: "EXTRACT_CONTEXT" })
  ▼
Content Script (extractor.ts)
  │
  │  Reads DOM → builds PageContext snapshot
  │  Returns: { url, title, interactive_elements[], headings[] }
  ▼
Service Worker
  │
  │  POST /analyze  { session_id, task, page_context }
  ▼
Backend: analyze route
  │
  ▼
context_service.py
  │  Sanitizes page_context
  │  Assembles system prompt + user message
  ▼
ai_service.py
  │  Calls Gemini API
  │  Parses JSON response
  │  Validates action schema
  ▼
Service Worker receives: { analysis, suggested_actions[] }
  │
  ▼
Side Panel renders ActionCard
  │  Shows: description, selector, reasoning, confidence, safety badge
  │
  ├── User clicks [Reject]
  │     │
  │     └── POST /workflow/log { event_type: "rejected" }
  │         Side panel: "Action rejected. Rephrase or cancel."
  │
  └── User clicks [Approve]
        │
        ▼
      Service Worker
        │
        │  chrome.tabs.sendMessage(tabId, { type: "EXECUTE_ACTION", action })
        ▼
      Content Script (executor.ts)
        │
        │  Validates selector
        │  Checks element exists
        │  Executes action
        │  Returns result
        ▼
      Service Worker
        │
        │  POST /workflow/log { event_type: "executed", execution_result }
        ▼
      Side Panel
        │
        └── Shows ExecutionFeed entry: "Clicked #login-btn — success"
```

---

## Workflow 2: Multi-Step Task (Phase 7)

```
User types: "Go to settings, find email field, update it to user@new.com"

AI returns suggested_actions: [
  { action_type: "click", target: "#settings-link", description: "Click Settings link" },
  { action_type: "fill", target: "#email-input", value: "user@new.com", description: "Fill email field" }
]

Side Panel: Queue loaded with 2 actions.

Step 1:
  ActionCard shown: "Click Settings link"
  User approves → executor.ts clicks → success
  POST /workflow/log (executed, success)
  Side Panel: re-analyzes page (page may have changed after navigation)

Step 2:
  ActionCard shown: "Fill email field with user@new.com"
  User approves → executor.ts fills → success
  POST /workflow/log (executed, success)
  Side Panel: "All steps completed"

At any step, user can click [Abort Queue] to stop.
```

---

## Workflow 3: Error Recovery

```
AI suggests action → User approves → executor.ts runs

  executor.ts: element not found
    │
    └── Returns { result: "element_not_found", error: "No element matching #old-selector" }
          │
          ▼
        Service Worker logs failure
          │
          ▼
        Side Panel shows:
          "Action failed: element not found. The page may have changed."
          [Retry] [Re-analyze page] [Cancel]

  User clicks [Re-analyze page]:
    → Full EXTRACT_CONTEXT + /analyze cycle restarts
    → Fresh action suggestion based on current page state
```

---

## Workflow 4: Approval with Caution Flag

```
AI returns action with safety_level: "caution"
  e.g., { action_type: "navigate", target_url: "https://different-domain.com", safety_level: "caution" }

ActionCard renders with yellow warning badge:
  ⚠ Caution: This action will navigate away from the current page.
  [Approve] [Reject]

User must explicitly approve despite warning.
```

---

## State Transitions

### Session State

```
[created] → [active] → [completed]
                └──────→ [abandoned]
```

A session is `abandoned` if no interaction for 30 minutes or user closes the tab.

### Action State

```
[suggested] → [approved] → [executed]
           └→ [rejected]
```

---

## Data Sensitivity Rules

Before building page_context snapshot:

1. Exclude all `<input type="password">` elements (selector and value)
2. Exclude elements with `autocomplete="cc-number"`, `autocomplete="cc-csc"`
3. Truncate visible_text to 2000 characters maximum
4. Truncate interactive_elements list to 50 elements maximum
5. Strip text content that matches common PII patterns:
   - SSN pattern: `\d{3}-\d{2}-\d{4}`
   - Credit card pattern: `\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}`

These rules are enforced in extractor.ts before context leaves the browser.
