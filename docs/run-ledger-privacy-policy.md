# Run Ledger Privacy Policy

V3 Run Ledger events are durable diagnostic records. They must preserve enough structure for replay and debugging without storing unnecessary browser content or secrets.

## Rules

- Do not persist credentials, passwords, API keys, auth tokens, session tokens, OTPs, cookies, JWTs, or secrets.
- Redact sensitive query parameter values.
- Strip URL fragments before persistence.
- Avoid storing raw DOM, HTML, screenshots, full visible text, or raw accessibility trees.
- Store compact metadata only unless a later feature flag explicitly permits richer traces.
- Treat ledger payloads as production records, not temporary debug logs.

## Sanitization

Ledger payloads and links pass through reusable sanitization helpers in `backend/app/run_ledger/privacy.py` before persistence.

The sanitization layer is intentionally conservative: keys containing sensitive terms such as `token`, `password`, `secret`, `session`, `cookie`, `auth`, or `credential` are redacted regardless of value type.

## Failure Policy

Ledger writes are best-effort. A ledger failure must never rollback workflow state, change planner behavior, change execution behavior, or alter workflow routing.
