# Phase 0 Harness Diagnostic — 2026-08-14

## Outcome

The Phase 0 baseline is blocked at the fixture health gate. This is a valid measurement result, not a reason to weaken the gate.

| Check | Result |
|---|---|
| Backend `/health` | OK, database connected |
| Provider configuration | Present; secret not recorded |
| Python Playwright import | Available |
| Fixture self-test | Failed: 0/3 completed |
| Infrastructure errors | 0 |
| Login diagnostic | `TIMEOUT`, five steps, `max_steps reached` |

## First wrong decision

The runner opened the login fixture before the first planner turn. The first blueprint-produced action was nevertheless:

```text
action_type: navigate
value/URL: absent
reasoning: Blueprint node objective: Reach target state
```

Execution correctly rejected it as `navigate: no url`.

The semantic phase remained `OPEN` with an objective requiring one opened page, even though an observed page was already available. Later planner output attempted `fill`, but the phase gate rejected it because only open/focus/switch/wait/navigate actions were allowed. Retries were exhausted and the task reached the five-step limit.

## Failure chain

```text
Fixture start URL already open
  -> mission blueprint initializes OPEN as incomplete
  -> emits navigate without grounded URL
  -> executor rejects invalid navigate
  -> OPEN never reconciles with observed page
  -> valid fill intent rejected by phase gate
  -> retry budget exhausted
  -> max_steps TIMEOUT
```

## Smallest production fix

Reconcile the initial blueprint/semantic phase with the first observation:

- if a valid observed page already satisfies the OPEN postcondition, mark OPEN complete before choosing an action;
- never emit `navigate` without a validated HTTP(S) URL;
- when a phase-generated action is invalid, do not mask a grounded planner action that is valid for the observed page;
- add the login, pagination, and modal fixtures as regression tests for this transition.

The relevant files currently have pre-existing user modifications, so Phase 0 did not overwrite them.

## Secondary harness issue

The traced task wrote its JSON/Markdown/HTML report and per-step viewer after roughly 24 seconds, but the CLI process remained alive and required termination. The benchmark must guarantee process exit after report publication and cleanup of Playwright, fixture-server, trace, and HTTP resources.

## Rerun gate

Do not start the 38-task baseline until:

1. `python -m benchmark.m0_runner --self-test` reaches at least 90%;
2. infrastructure errors remain zero;
3. the command exits without manual termination;
4. a traced login fixture completes and its report passes `benchmark.phase0_gate`.
