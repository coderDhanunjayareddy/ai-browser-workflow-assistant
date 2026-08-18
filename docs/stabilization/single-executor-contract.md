# Canonical Single-Executor Contract

**Effective:** 2026-08-18  
**Schema:** `CanonicalActionContract` version `1.0`

## Production pipeline

```text
observed planner action
  -> exact observation grounding
  -> durable execution reservation
  -> CanonicalActionContract v1.0
  -> backend policy evaluate / confirmation
  -> privileged extension message validation
  -> backend policy enforce
  -> service-worker canonical dispatcher
  -> canonical CDP click (click actions)
  -> structured effect verification
  -> contract-linked adapter trace
  -> durable completion ledger
```

The extension service worker is the only privileged policy and mutation boundary. Internal action-specific adapters may be selected only by its canonical action router. They are not independent entry points.

## Required immutable fields

Every approved mutation carries:

- `target_identity`: exact selector, observation selector ID, exact accessibility name, role, and semantic kind;
- `origin`: normalized origin and complete observed URL;
- `browser_binding`: tab, window, and frame;
- `resource_identity`: complete document/page URL and observed title;
- `expected_effect`: typed effect and human-readable postcondition;
- `safety_class`;
- `idempotency_key` from the durable execution reservation;
- the original action and a unique dispatch ID.

The side panel constructs this contract after the durable reservation and before policy evaluation. The same contract reaches policy evaluation, confirmation receipts, policy enforcement, service-worker dispatch, browser grounding, verification evidence, and the durable ledger result.

## Click invariant

`click` has exactly one production mutation route:

```text
service_worker > policy > canonical_cdp_click
```

- The exact approved selector must exist and resolve to one visible element.
- When an exact observed accessibility name exists, the resolved element label must match it.
- Failure returns no grounding; it cannot fall through to approximate accessibility, vision coordinates, a DOM `.click()`, another executor, or selector recovery.
- Child-frame clicks fail closed until exact CDP frame targeting is implemented.
- A verified no-effect returns to observation/replanning and cannot be clicked again through an alternative selector.

## Disabled competing click paths

- Removed the popup-safe direct DOM click implementation from the service worker.
- The generic action router explicitly rejects `click`.
- Click was removed from selector recovery.
- Click was removed from the CDP fallback set because CDP is now its primary route.
- The legacy DOM executors remain available for non-click action families but cannot receive a production click from the canonical dispatcher.

## Observable evidence

Each result records `dispatch_id`, `dispatch_path`, contract schema, idempotency key, exact target name, resource URL, frame, expected effect, safety class, and whether the selector remained unchanged.

