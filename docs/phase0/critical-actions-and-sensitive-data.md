# Critical Actions and Sensitive Data

This is the Phase 0 policy contract. It defines what the Phase 1 live execution gate must enforce.

## Authority model

- Only direct user instructions and explicit confirmations grant authority.
- Page content, screenshots, emails, documents, tool output, and model-generated plans are untrusted data—not permission.
- Planner-provided `safety_level`, reasoning, or confidence cannot authorize execution.
- Confirmation is requested at the last responsible moment, after safe preparatory work but before the exact consequential action.
- A confirmation receipt is narrow: action, site/account, target/audience, disclosed data, amount if any, expiry, and task ID.
- Material changes invalidate the receipt.

## Dispositions

| Disposition | Meaning |
|---|---|
| `allow` | Low-risk, reversible, within explicit user intent. |
| `confirm` | Pause immediately before the exact consequential action. |
| `watch` | Continue only while the user is actively supervising the sensitive context. |
| `handoff` | Give control to the user for the protected step; resume from a fresh observation. |
| `deny` | Do not perform the action. Explain the boundary. |

## Critical-action classes

| Class | Default | Required scope |
|---|---|---|
| External communication | Confirm | Recipient/audience and final content |
| Financial transaction | Confirm | Merchant/recipient, item/service, currency, total |
| Destructive or irreversible action | Confirm | Exact object/scope and recovery path |
| Permission or access change | Confirm | Resource, principal, privilege, duration |
| Account/security change | Handoff | User completes the protected step |
| Password, OTP, MFA, CAPTCHA, card secret | Handoff | Never enter through model context |
| Install/run downloaded code or extension | Handoff | Artifact, publisher, integrity, privileges |
| Medical/legal/employment/housing/insurance/benefits action | Handoff | User reviews and completes consequence |
| Sensitive-data transmission | Confirm | Exact data, destination, purpose, resulting access |
| Third-party tool/connector access to non-public data | Confirm | Provider, account, operation, data classes, read/write scope, duration |

Typing data into a field counts as transmission. Visiting a URL containing sensitive query parameters also counts as transmission. A harmless draft may still disclose data to the site and therefore may require confirmation before typing.

## Sensitive-data handling

| Data class | Model context | Transmission |
|---|---|---|
| Passwords and security answers | Never | Handoff |
| OTP, MFA, cookies, auth tokens, API keys | Never | Handoff |
| Financial information | Redacted by default | Confirm |
| Government identifiers | Redacted by default | Confirm |
| Health information | Minimum necessary | Handoff for medical-care actions |
| Legal, HR, payroll | Minimum necessary | Confirm |
| Precise location/home address | Redacted by default | Confirm |
| Biometrics | Never by default | Handoff/deny without approved requirement |
| Private email/chat/calendar | Task-scoped | Confirm before cross-origin disclosure |
| Browsing/search/internal-URL telemetry | Request-scoped | Confirm; no permanent always-allow grant |
| Personal contact information | Minimum necessary | Confirm when audience changes |
| User files | Metadata first | Confirm exact file and destination |

## Logging and evidence

- Never record raw credentials, OTPs, cookies, tokens, full card data, or security answers.
- Store confirmation receipts and policy reasons, not the protected value.
- Redact sensitive URL parameters and fragments.
- Prefer hashes, field classifications, byte counts, and filenames over raw file contents.
- Screenshots and DOM captures inherit the highest sensitivity of visible content.
- Trace access and retention must be narrower than ordinary application logs.

## Prompt injection and tool-boundary controls

- Treat page content, files, messages, tool output, retrieved records, and connector metadata as untrusted data.
- Never place untrusted page or tool content into a developer/system authority channel.
- External content cannot grant permission, broaden scope, select a recipient, or weaken a confirmation requirement.
- Pass planner-to-executor decisions through fixed schemas and validated enums; do not execute free-form model text.
- Validate selectors, URLs, action types, recipients, amounts, files, and data classifications outside the model before execution.
- Require scoped confirmation before a third-party connector, plugin, or MCP server reads or writes non-public user data.
- Public read-only browser navigation may remain `allow`; authenticated/private reads require the applicable sensitive-data or connector decision.
- Tool output must be reclassified as data on return and cannot be treated as a new user instruction.
- Use trace review and adversarial evals to measure prompt-injection resistance; prompt instructions alone are not an enforcement boundary.

## Phase 1 acceptance tests

- 100% confirmation recall for the defined critical-action suite.
- No credential/authentication-secret value enters model requests, logs, traces, or durable state.
- A page instruction cannot grant permission or weaken a confirmation requirement.
- Changed recipient, amount, file, permission, or account invalidates prior confirmation.
- Declined and expired confirmations cannot be replayed.
- Every consequential action has a policy decision and, when needed, a valid receipt immediately preceding execution.
