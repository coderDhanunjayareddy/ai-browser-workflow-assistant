# Trusted Grounding and Exact Postconditions

**Effective:** 2026-08-18  
**Scope:** Canonical click dispatch for the frozen MVP

## Authoritative click route

Clicks that need browser-native input use only:

```text
approved CanonicalActionContract
  -> service worker
  -> live policy enforcement
  -> canonical CDP controller
  -> Input.dispatchMouseEvent
  -> generic effect check
  -> exact application postcondition
  -> durable execution result
```

The page never receives a production `HTMLElement.click()` for this path. A failed grounding or postcondition returns a failed/no-effect result; it is not reinterpreted by another click executor.

## Grounding order

1. `stable_selector`: the selector must be syntactically valid, visible, unique, and consistent with the observed exact name when one is present.
2. `accessibility_name`: the normalized accessible name and optional role must match exactly and identify exactly one backend DOM node.
3. `verified_screenshot`: permitted only for an action already classified as `vision_region`, with an explicit verification flag, a bound screenshot hash that matches a fresh screenshot, an in-viewport point, and a compatible hit target.

Each attempted source records its result. If a fallback is used, `cdp_fallback_reason` states why the previous source was rejected. Screenshot coordinates without all verification bindings fail closed.

## Exact postconditions

After the browser reports a click effect, supported applications require the target entity to be visible:

- WhatsApp: exact visible conversation-header name;
- Gmail: exact visible main-thread subject;
- Google Docs: exact document-title input value;
- Google Drive: exact relevant item/folder heading.

A generic DOM change cannot substitute for the exact postcondition when the application and target identity are known. The verifier polls for bounded delayed rendering and records expected name, observed name, target kind, and evidence reason.

## Fail-closed boundaries

- Ambiguous exact text, duplicate accessibility nodes, selector/name drift, stale screenshot hashes, out-of-viewport points, incompatible hit targets, and unsupported child frames do not click.
- The immutable origin, tab, frame, resource, safety class, expected effect, and idempotency identity from Day 2 remain required.
- Sending, attaching, deleting, sharing, purchasing, submitting, and account-setting changes remain outside this non-sending gate and require their separate confirmation policy.

## Regression coverage

- CDP selector, accessibility, screenshot, attach/detach, and failure behavior;
- canonical contract and privileged message validation;
- exact WhatsApp, Gmail, and Docs target postconditions;
- backend policy rejection of a reordered or unverified grounding policy;
- full extension and backend regression suites.

