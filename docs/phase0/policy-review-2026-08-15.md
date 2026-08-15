# Phase 0 Policy Review — 2026-08-15

## Decision

**Approved for Phase 0 exit and Phase 1 implementation, with enforcement conditions.**

This is an AI-assisted engineering/security desk review of the project policy contract. It is not a legal opinion, compliance certification, penetration test, or substitute for an independent organizational security review before public deployment.

## Review authority

| Role | Evidence | Decision |
|---|---|---|
| Product owner | User instruction on 2026-08-15 to complete the remaining review and then move to Phase 1 | Approved to complete the Phase 0 governance gate |
| Engineering/security desk review | Policy/document/code/test review against current official OpenAI agent-safety guidance | Approved with the mandatory Phase 1 conditions below |
| Independent legal/compliance/security audit | Outside Phase 0 scope | Required later when deployment jurisdiction, users, regulated data, and distribution channel are known |

## Source reviewed

- OpenAI, “Safety in building agents”: https://developers.openai.com/api/docs/guides/agent-builder-safety (retrieved 2026-08-15).

The official guidance identifies prompt injection and private-data leakage as core risks and recommends keeping untrusted data out of privileged instructions, using structured outputs, keeping tool approvals on, applying input guardrails, and running trace graders/evals.

## Control assessment

| Required property | Phase 0 contract | Result |
|---|---|---|
| Page/tool content cannot grant authority | Authority model explicitly treats it as untrusted data | Pass |
| Consequential actions require scoped approval | Critical-action rules define `confirm`/`handoff` and narrow receipts | Pass |
| Secrets do not enter model context/logs | Password/OTP/token rules use `never` plus user handoff | Pass |
| Sensitive transmission is recognized before final submit | Typing, uploads, and sensitive URL parameters count as transmission | Pass |
| Structured planner-to-executor boundary | Machine-readable enums/rules; Phase 1 must enforce validated action schemas | Pass for definition; implementation required in Phase 1 |
| Third-party connector/MCP trust boundary | Explicit confirmation rule for non-public data access | Pass |
| Trace/eval evidence | Raw Phase 0 traces, failure taxonomy, and Phase 1 acceptance tests are defined | Pass |
| Prompt-injection mitigation | Privileged-channel, data-flow, validation, and tool-output rules are explicit | Pass for definition; adversarial implementation eval required in Phase 1 |

## Mandatory Phase 1 conditions

1. The live execution gateway—not the planner—must make the final policy decision.
2. Every side-effecting action must carry a validated policy decision and any required unexpired confirmation receipt.
3. Passwords, OTP/MFA values, cookies, session tokens, API keys, security answers, and card secrets must never be sent to the model or written to traces.
4. Untrusted page/tool content must not enter system/developer instructions or become authorization.
5. Planner output must be parsed into a strict action schema and revalidated against the latest browser observation.
6. Connector/MCP access to non-public data requires explicit provider/account/scope confirmation; no permanent blanket grant.
7. Phase 1 cannot claim enforcement until the acceptance tests in `critical-actions-and-sensitive-data.md` pass on the live path.

## Verification record

- Post-review policy and benchmark regression suite: 162 passed.
- Combined changed-path/benchmark/policy suite before this review: 243 passed.
- Frozen dataset and paired-report gate: passed with zero errors.
- Policy changes from this review are additive and do not alter the frozen 38-task dataset or previously published raw baseline.

## Residual risk

The policy definition reduces ambiguity but does not itself enforce safety. Prompt injection remains an open adversarial risk until Phase 1 implements the independent policy gate, secret redaction, scoped approvals, and injection-focused evals. Phase 1 should begin with enforcement architecture and tests—not broader autonomous capability.
