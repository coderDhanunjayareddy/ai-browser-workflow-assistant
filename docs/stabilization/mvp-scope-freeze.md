# Client MVP Scope Freeze

**Effective:** 2026-08-18  
**Status:** Active for the 15-working-day stabilization sprint

## Supported pilot workflows

1. **WhatsApp:** open one exact consenting test contact/self-chat, attach one explicitly approved synthetic file, require confirmation, send exactly once, and verify delivery.
2. **Gmail:** search synthetic messages, open the exact thread, create a draft, reload, verify persistence, and verify that no email was sent.
3. **Google Drive:** navigate exact synthetic folders, search files, create synthetic content, rename it, upload/download synthetic files, and verify final state.
4. **Google Docs:** enter and format synthetic text, wait for save, reload, and verify content plus formatting persistence.

## Permitted sprint changes

- Production runtime consolidation, browser grounding/execution, action verification, persistence/recovery, safety, observability, evidence collection, and performance work required by the four workflows.
- Tests and controlled fixtures that reproduce a failure observed in the four live workflows.
- Packaging, version identity, rollback, and pilot documentation.

## Frozen work

- New planner phases, capability registries, enterprise/product demonstration features, billing, SSO, SCIM, and unrelated API surfaces.
- New third-party workflow claims outside the four supported pilot workflows.
- Purchases, payments, bookings, production-data deletion, or account-setting changes.
- Website-specific patches that bypass the canonical target, policy, execution, verification, or evidence contracts.

## Evidence rule

Unit, contract, benchmark, and controlled-fixture tests are regression evidence only. A workflow is not pilot-ready until its real side-panel run meets the release gates in [the 15-day plan](../15-day-client-mvp-stabilization-plan.md).

## Change-control rule

Any proposed change outside the permitted sprint work must be documented with its reason, effect on the schedule, and explicit approval before implementation. Calendar progress cannot override a failed exit gate.
