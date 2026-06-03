# Architecture — AI Browser Workflow Assistant

## System Overview

A Chrome Extension (MV3) that reads the active webpage, sends context to a FastAPI backend, receives structured AI-suggested actions, presents them to the user for approval, and executes only approved actions in the browser.

## Components

### Chrome Extension (MV3)

| Component | File | Responsibility |
|---|---|---|
| Service Worker | `background/service-worker.ts` | Message broker between side panel, content script, and backend. Manages session state in chrome.storage.session. |
| Content Script | `content/extractor.ts` | Builds structured DOM snapshot from active tab. No side effects. |
| Content Script | `content/executor.ts` | Executes a single approved action (click/fill/scroll/navigate). Returns result. |
| Side Panel | `sidepanel/App.tsx` | Root React app. Orchestrates workflow UI. |
| Side Panel | `sidepanel/components/ActionCard.tsx` | Displays one suggested action with Approve/Reject buttons. |
| Side Panel | `sidepanel/hooks/useWorkflow.ts` | All workflow state management. |

### Backend (FastAPI)

| Component | File | Responsibility |
|---|---|---|
| Router | `api/routes/analyze.py` | POST /analyze — thin HTTP boundary only |
| Router | `api/routes/workflow.py` | GET /workflow/history, POST /workflow/log |
| Service | `services/ai_service.py` | Calls Gemini API, parses structured response |
| Service | `services/context_service.py` | Assembles prompt, validates action schema |
| Service | `services/workflow_service.py` | PostgreSQL read/write |
| Config | `core/config.py` | All settings loaded from .env via pydantic-settings |
| DB | `core/database.py` | SQLAlchemy engine and session factory |

## Communication Flow

```
Side Panel → Service Worker → Backend → Gemini API
                  ↕
            Content Script
            (reads DOM, executes actions)
```

All backend calls go through the Service Worker. Content scripts cannot make cross-origin HTTP requests.

## Data Flow

1. User types task in Side Panel
2. Service Worker requests DOM snapshot from Content Script
3. Service Worker sends {task, page_context} to POST /analyze
4. Backend assembles prompt, calls Gemini, validates response
5. Structured action list returned to Service Worker
6. Side Panel renders ActionCard for each action
7. User approves → Service Worker sends action to Content Script
8. Content Script executes action, returns result
9. Backend logs the event to PostgreSQL

## Database Schema

### sessions
```
id          UUID PRIMARY KEY
created_at  TIMESTAMP
tab_url     TEXT
tab_title   TEXT
status      TEXT  -- active | completed | abandoned
```

### workflow_events
```
id               UUID PRIMARY KEY
session_id       UUID REFERENCES sessions(id)
event_type       TEXT  -- suggested | approved | rejected | executed
action_type      TEXT  -- click | fill | scroll | navigate
target_selector  TEXT
value            TEXT
description      TEXT
ai_reasoning     TEXT
confidence       FLOAT
approved_at      TIMESTAMP
executed_at      TIMESTAMP
execution_result TEXT  -- success | failure | element_not_found
created_at       TIMESTAMP
```

## Action Allowlist (MVP)

| Action Type | Description |
|---|---|
| click | Click a DOM element by CSS selector |
| fill | Set value of an input element |
| scroll | Scroll the page or an element |
| navigate | Navigate to a URL (requires approval) |

All other action types are rejected by context_service.py before reaching the extension.

## Security Boundaries

- Gemini API key lives in backend .env only — never in extension
- Page content passed as data to AI, never as instructions
- CSS selectors validated before use in executor.ts
- Password fields excluded from DOM snapshot
- Action allowlist enforced server-side regardless of AI output
