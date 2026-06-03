# API Specification — AI Browser Workflow Assistant

Base URL: `http://localhost:8000`

All requests and responses use `Content-Type: application/json`.

---

## GET /health

Health check.

**Response 200:**
```json
{
  "status": "ok",
  "db": "connected"
}
```

---

## POST /analyze

Analyze a page context and task. Returns structured action suggestions.

**Request body:**
```json
{
  "session_id": "uuid-string",
  "task": "Click the login button",
  "page_context": {
    "url": "https://example.com/login",
    "title": "Login — Example",
    "interactive_elements": [
      {
        "type": "button",
        "text": "Login",
        "selector": "#login-btn",
        "visible": true
      },
      {
        "type": "input",
        "input_type": "text",
        "placeholder": "Username",
        "selector": "#username",
        "visible": true
      }
    ],
    "headings": ["Welcome back", "Sign in to continue"],
    "selected_text": ""
  }
}
```

**Response 200:**
```json
{
  "session_id": "uuid-string",
  "analysis": "I found a Login button on this page. I will click it to proceed with the login flow.",
  "suggested_actions": [
    {
      "action_id": "uuid-string",
      "action_type": "click",
      "target_selector": "#login-btn",
      "value": null,
      "description": "Click the Login button",
      "reasoning": "The #login-btn element is the primary action button for this login form.",
      "confidence": 0.95,
      "safety_level": "safe"
    }
  ]
}
```

**Response 422:** Validation error (malformed request)
**Response 500:** AI service error or upstream failure

**Field constraints:**
- `task`: 1–500 characters
- `action_type`: one of `click | fill | scroll | navigate`
- `safety_level`: one of `safe | caution | danger`
- `confidence`: 0.0 to 1.0

---

## POST /workflow/log

Log a workflow event (approval, rejection, or execution result).

**Request body:**
```json
{
  "session_id": "uuid-string",
  "action_id": "uuid-string",
  "event_type": "approved",
  "execution_result": null,
  "timestamp": "2026-05-12T10:30:00Z"
}
```

`event_type` values: `approved | rejected | executed`
`execution_result` values (when event_type is `executed`): `success | failure | element_not_found`

**Response 201:**
```json
{
  "logged": true,
  "event_id": "uuid-string"
}
```

---

## GET /workflow/history

Retrieve past workflow sessions.

**Query parameters:**
- `limit` (int, default 20, max 100): number of sessions to return
- `offset` (int, default 0): pagination offset

**Response 200:**
```json
{
  "sessions": [
    {
      "id": "uuid-string",
      "created_at": "2026-05-12T10:30:00Z",
      "tab_url": "https://example.com/login",
      "tab_title": "Login — Example",
      "status": "completed",
      "event_count": 3
    }
  ],
  "total": 42
}
```

---

## GET /workflow/session/{session_id}

Retrieve all events for a specific session.

**Response 200:**
```json
{
  "session": {
    "id": "uuid-string",
    "created_at": "2026-05-12T10:30:00Z",
    "tab_url": "https://example.com",
    "tab_title": "Example Page",
    "status": "completed"
  },
  "events": [
    {
      "id": "uuid-string",
      "event_type": "executed",
      "action_type": "click",
      "target_selector": "#login-btn",
      "value": null,
      "description": "Click the Login button",
      "confidence": 0.95,
      "execution_result": "success",
      "created_at": "2026-05-12T10:30:05Z"
    }
  ]
}
```

---

## Internal Extension Message Types

These are chrome.runtime message schemas, not HTTP.

### EXTRACT_CONTEXT
Side panel → Service worker → Content script

Request:
```json
{ "type": "EXTRACT_CONTEXT", "tabId": 123 }
```

Response:
```json
{
  "type": "CONTEXT_RESULT",
  "context": { /* PageContext object */ }
}
```

### EXECUTE_ACTION
Service worker → Content script

Request:
```json
{
  "type": "EXECUTE_ACTION",
  "action": {
    "action_id": "uuid",
    "action_type": "click",
    "target_selector": "#login-btn",
    "value": null
  }
}
```

Response:
```json
{
  "type": "EXECUTION_RESULT",
  "action_id": "uuid",
  "result": "success",
  "error": null
}
```
