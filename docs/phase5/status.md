# Phase 5 — Production evidence

Status: continuous evidence infrastructure implemented; real third-party disposable accounts must be provisioned by an operator.

## What is live

- A durable, secret-free disposable-account/evaluation ledger at `/production-evidence`.
- Exact account-lease and origin binding. Evidence from the wrong account, lease, or origin is rejected.
- A red-team suite that exercises the real Phase 1 `LivePolicyEngine` for prompt injection, cross-origin grants, account confusion, and confirmation bypass; every API run is retained in the evidence ledger.
- Independent capability gates with `off`, `shadow`, `canary`, `active`, and `rollback` stages, plus durable decision history.
- Promotions require sufficient samples, success/completion thresholds, 100% confirmation recall by default, and zero leakage, account-confusion, bypass, duplicate-side-effect, or critical events.
- Critical evidence forces the affected capability to `rollback`; other capabilities keep their own state.
- Phase 0 `dead` and `stub` modules are archived from production claims in a generated retirement register. Source is retained until dynamic-import review and paired end-to-end evidence approve physical removal.

## Operator flow

1. Provision a short-lived test account outside the application.
2. Register only its alias, provider, allowed origin, persona, and expiry. Never send credentials to the evidence API.
3. Lease it, run the task, attach raw trace references, and record the result.
4. Evaluate only the relevant capability gate. Promotion fails closed when evidence is insufficient.
5. Quarantine the account after suspicious behavior; reset it before reuse.

The controlled suite manifest is `docs/phase5/disposable-account-suite.json`. It intentionally contains no credentials and does not claim that external accounts have already been created.

Refresh and verify the quarantine register after runtime-map changes:

```powershell
.venv-codex\Scripts\python.exe tools\phase5_retirement_report.py `
  --inventory ..\docs\phase0\runtime-inventory.json `
  --output ..\docs\phase5\scaffold-retirement-register.json

.venv-codex\Scripts\python.exe tools\phase5_retirement_report.py `
  --inventory ..\docs\phase0\runtime-inventory.json `
  --output ..\docs\phase5\scaffold-retirement-register.json --check
```

## API

- `POST /production-evidence/accounts`
- `POST /production-evidence/accounts/{account_id}/lease`
- `POST /production-evidence/accounts/{account_id}/release` (optionally quarantine)
- `GET /production-evidence/accounts`
- `POST /production-evidence/evaluations`
- `PUT /production-evidence/gates/{capability}`
- `POST /production-evidence/gates/{capability}/evaluate`
- `POST /production-evidence/red-team/run`
- `GET /production-evidence/scaffolding/retirement-register`
- `GET /production-evidence/summary`

## Honest exit status

The automated safety suite can prove the enforcement logic and promotion gates. Phase 5 is continuous, so production evidence is never permanently “finished.” Promotion remains blocked until real disposable-account runs provide the configured sample count. Physical source deletion also remains blocked until paired end-to-end evidence shows no benefit.
