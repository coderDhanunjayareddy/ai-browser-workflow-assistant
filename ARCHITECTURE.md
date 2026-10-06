# Proposed Version 1 architecture

This is the Phase 3 target, not a claim that every part is implemented. `docs/stabilization/canonical-runtime-map.md` describes the current production path. A booking example tests the general design; no booking-site condition belongs in the core loop.

## One task loop

```text
Task + allowed sites + success proof
  -> goal interpreter -> short-term task state -> planner / AI decision
  -> page reader (DOM and accessibility; optional screenshot)
  -> safety and permission gate -> human confirmation when needed
  -> exact action contract -> service-worker executor
  -> page observer -> action verifier -> goal verifier
  -> continue, bounded replan, human handoff, verified finish, or honest stop
```

The side panel owns user input and visible state. The backend owns goal interpretation and next-step reasoning. The extension service worker owns privileged browser dispatch. The page reader supplies evidence, never instructions. The verifier checks both the immediate action and the user's final goal. Storage keeps only a compact task checkpoint and approved diagnostic evidence.

## Module responsibilities

| Module | Responsibility |
|---|---|
| UI / task input | Take the goal; show progress, consent, result, and limits. |
| Goal interpreter | Record requested outcome, constraints, and proof of completion. |
| Planner | Propose one next step under step and time budgets. |
| Page perception | Produce a compact, current page state. |
| DOM/accessibility extractor | Identify visible text and named controls with tab/frame binding. |
| Optional screenshot reader | Supply bounded visual evidence when text structure is insufficient. |
| AI decision layer | Use trusted goal plus untrusted page facts to propose an action, ask, or stop. |
| Action executor | Dispatch one approved action to one bound tab and record its identity. |
| Page observer | Capture the resulting page after load or settle. |
| Action verifier | Compare the expected effect with the observed effect. |
| Recovery / replanning | Re-observe and change approach within limits; stop on uncertainty. |
| Short-term memory | Keep verified facts, attempts, and the current goal for this task. |
| Optional preference memory | Off in Version 1; add only with explicit opt-in. |
| Safety / permissions | Allow, confirm, or block access and actions by effect and origin. |
| Human confirmation | Show exact consequences immediately before commitment. |
| Logging / debugging | Record redacted first-failure and timing evidence. |
| Evaluation harness | Test final outcomes in fixtures and the real side panel. |

## Data flow and authority

`UserTask` -> goal interpreter -> `TaskState` and success criteria. `PageState` and verified history -> planner -> `ActionDecision`. The policy gate combines that decision with origin, tab, privacy rule, and user approval. The executor returns `ActionResult`; a new `PageState` lets the verifier return `VerificationResult`. The recovery module updates `RecoveryState` and `TaskState`. Only verified evidence can set `TaskState.phase` to `complete`.

The existing production contracts are in `backend/app/schemas/request.py`, `backend/app/schemas/response.py`, and `extension/src/execution/canonical_action_contract.ts`. Implement by mapping and tightening them, not by adding a second action route.

## Proposed JSON Schema

These eight named objects are the target data shapes. `expectedEffect` and `successCriteria` must be converted to checkable rules before execution. All fields shown as required must be present.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$defs": {
    "UserTask": {
      "type": "object", "additionalProperties": false,
      "required": ["version", "taskId", "goal", "constraints", "successCriteria", "allowedOrigins"],
      "properties": {
        "version": {"const": "1"}, "taskId": {"type": "string", "minLength": 1},
        "goal": {"type": "string", "minLength": 1},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "successCriteria": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "allowedOrigins": {"type": "array", "items": {"type": "string"}}
      }
    },
    "Element": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "frameId", "selector", "role", "name", "visible", "enabled", "value"],
      "properties": {
        "id": {"type": "string"}, "frameId": {"type": "string"},
        "selector": {"type": ["string", "null"]}, "role": {"type": "string"},
        "name": {"type": "string"}, "visible": {"type": "boolean"},
        "enabled": {"type": "boolean"}, "value": {"type": ["string", "null"]}
      }
    },
    "PageState": {
      "type": "object", "additionalProperties": false,
      "required": ["version", "pageId", "observedAt", "tabId", "url", "title", "loadState", "elements", "visibleText", "signals", "screenshotRef"],
      "properties": {
        "version": {"const": "1"}, "pageId": {"type": "string"},
        "observedAt": {"type": "string", "format": "date-time"},
        "tabId": {"type": "integer", "minimum": 0}, "url": {"type": "string"},
        "title": {"type": "string"},
        "loadState": {"enum": ["loading", "ready", "blocked", "error"]},
        "elements": {"type": "array", "items": {"$ref": "#/$defs/Element"}},
        "visibleText": {"type": "string"},
        "signals": {"type": "array", "items": {"enum": ["popup", "login", "captcha", "form_error", "confirmation"]}},
        "screenshotRef": {"type": ["string", "null"]}
      }
    },
    "ActionDecision": {
      "type": "object", "additionalProperties": false,
      "required": ["version", "actionId", "kind", "targetElementId", "value", "expectedEffect", "risk", "reason"],
      "properties": {
        "version": {"const": "1"}, "actionId": {"type": "string"},
        "kind": {"enum": ["navigate", "click", "fill", "select", "scroll", "wait", "report", "ask"]},
        "targetElementId": {"type": ["string", "null"]},
        "value": {"type": ["string", "null"]},
        "expectedEffect": {"type": "string"},
        "risk": {"enum": ["read", "reversible", "consequential", "blocked"]},
        "reason": {"type": "string"}
      }
    },
    "ActionResult": {
      "type": "object", "additionalProperties": false,
      "required": ["version", "actionId", "dispatchId", "status", "beforePageId", "afterPageId", "message"],
      "properties": {
        "version": {"const": "1"}, "actionId": {"type": "string"},
        "dispatchId": {"type": ["string", "null"]},
        "status": {"enum": ["dispatched", "failed", "uncertain", "not_dispatched"]},
        "beforePageId": {"type": "string"},
        "afterPageId": {"type": ["string", "null"]}, "message": {"type": "string"}
      }
    },
    "VerificationResult": {
      "type": "object", "additionalProperties": false,
      "required": ["version", "actionId", "status", "expected", "observed", "evidenceRefs"],
      "properties": {
        "version": {"const": "1"}, "actionId": {"type": "string"},
        "status": {"enum": ["verified", "no_effect", "contradicted", "uncertain"]},
        "expected": {"type": "string"}, "observed": {"type": "string"},
        "evidenceRefs": {"type": "array", "items": {"type": "string"}}
      }
    },
    "TaskState": {
      "type": "object", "additionalProperties": false,
      "required": ["version", "taskId", "phase", "stepCount", "verifiedFacts", "attemptedActionIds", "lastPageId", "completionEvidenceRefs"],
      "properties": {
        "version": {"const": "1"}, "taskId": {"type": "string"},
        "phase": {"enum": ["observing", "planning", "awaiting_confirmation", "acting", "verifying", "recovering", "complete", "blocked", "failed"]},
        "stepCount": {"type": "integer", "minimum": 0},
        "verifiedFacts": {"type": "object", "additionalProperties": {"type": "string"}},
        "attemptedActionIds": {"type": "array", "items": {"type": "string"}},
        "lastPageId": {"type": ["string", "null"]},
        "completionEvidenceRefs": {"type": "array", "items": {"type": "string"}}
      }
    },
    "RecoveryState": {
      "type": "object", "additionalProperties": false,
      "required": ["version", "errorCode", "lastActionId", "attempts", "limit", "decision", "reason"],
      "properties": {
        "version": {"const": "1"}, "errorCode": {"type": "string"},
        "lastActionId": {"type": ["string", "null"]},
        "attempts": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 0},
        "decision": {"enum": ["retry_after_observation", "replan", "ask_user", "stop"]},
        "reason": {"type": "string"}
      }
    }
  }
}
```

## Error detection and recovery

| Signal | Check | Result |
|---|---|---|
| Page not loaded | Loading state or no usable content after timeout | Bounded wait, then stop. |
| Element absent or stale | Exact bound target missing at dispatch | Re-observe; never substitute a similar target. |
| Click or form failed | Expected field, URL, or confirmation did not appear | Record no effect or field error; replan within limit. |
| Popup | New dialog, overlay, or tab | Identify before proceeding. |
| Login or CAPTCHA | Login/challenge signal | Human handoff, then re-observe. |
| Wrong page | Origin, URL, or resource identity differs | Stop or safely replan. |
| Goal complete | All success criteria have independent evidence | Report verified completion. |
| Goal impossible or uncertain | Access block, exhausted budget, unsupported control, or uncertain final dispatch | Report blocked/partial; no false success. |

## Safety and privacy policy

- Automatic: reading, navigation, search, scroll, and reversible selection on an allowed page when the exact target is known.
- Confirmation: real-world commitment, including final no-charge booking submission, with exact details shown just before dispatch. One confirmation authorizes one action only.
- Human-only: login, passwords, one-time codes, and CAPTCHA. Re-observe after the person completes the step.
- Blocked in the first proposed version: payment details, purchase, cancellation, deletion, messaging, account creation, and repeated uncertain external submissions.
- Public-page AI input is limited to relevant snippets, page title, and URL. Private account pages and secrets do not go to the AI service without a separate owner decision.
- A payment-required travel flow is incomplete under this policy. It must stop and say why; it cannot claim a completed booking.

