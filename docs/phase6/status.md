# Phase 6 — Live validation and hardening

Status: **controlled visual exit gate passed; authenticated third-party gate pending credentials**  
Date: 2026-08-17

## Completed in this phase

- Added a repeatable Phase 6 runner that executes 25 representative workflows in real Chromium.
- Captured a final-state screenshot and SHA-256 digest for every workflow.
- Added a read-only invoice extraction scenario so the suite covers rendered data reading as well as interaction.
- Ran the live Phase 1 policy boundary through seven adversarial probes covering prompt injection, cross-origin leakage, account confusion, and confirmation bypass.
- Visually inspected representative invoice, search, and delayed-content flows in the connected Chrome browser.
- Repaired stale regression expectations exposed by the full verification run.

## Controlled exit-gate evidence

| Check | Result |
|---|---:|
| Real Chromium workflows | 25/25 passed |
| Final-state screenshots | 25/25 captured |
| Policy red-team probes | 7/7 passed |
| Critical confirmation recall | 100% |
| Critical failures | 0 |
| Backend unit suite | 3,587 passed |
| Backend real-browser integration suite | 31 passed |
| Extension tests | 158 passed |
| Extension type-check and production build | passed |

The machine-readable evidence is in
[`controlled-visual-validation-2026-08-17.json`](controlled-visual-validation-2026-08-17.json),
with a readable summary in
[`controlled-visual-validation-2026-08-17.md`](controlled-visual-validation-2026-08-17.md).

Re-run it with:

```text
cd backend
.venv-codex\Scripts\python.exe tools\phase6_validation.py --output ..\docs\phase6\controlled-visual-validation-2026-08-17.json --screenshots ..\docs\phase6\screenshots
```

## Production boundary

This is strong engineering evidence from deterministic sites rendered and operated by real Chromium. It is not evidence that every public website or authenticated account flow works.

Disposable-account evaluation of Gmail, Google Workspace, shopping, booking, and similar third-party services is still pending because no disposable credentials were supplied. Credentials must be provisioned outside the repository, and destructive or financial actions must remain confirmation-gated. Phase 5 therefore remains continuous: new capabilities are promoted only after their own live evidence meets the configured gate.

