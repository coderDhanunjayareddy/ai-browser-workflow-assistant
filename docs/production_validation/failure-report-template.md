# Production Validation Failure Report Template

Use this template for every failed, partial, stuck, or ambiguous PVS task. The purpose is to identify the earliest architectural failure, not to describe only the final failure.

## Task

- Task ID:
- Goal:
- Website:
- Difficulty:
- Run date:
- Browser profile:
- Auth state:
- Provider/model:
- Extension build/version:
- Operator:

## Outcome

- Final status: Completed / Partial / Failed / Blocked / Environmental
- Completion evidence:
- Max planner turns:
- Actual planner turns:
- Max browser actions:
- Actual browser actions:
- Total elapsed time:

## Timeline

| Turn | Phase | Observation Summary | Planner Outcome | Browser Action | Execution Result | Validation / SGV | Mission Status |
|---:|---|---|---|---|---|---|---|
| 1 |  |  |  |  |  |  |  |
| 2 |  |  |  |  |  |  |  |

## Planner Decisions

For each planner turn include:

- Rendered planner goal/context summary:
- Outcome kind:
- Reasoning/analysis:
- Suggested action or report:
- Selector/action target:
- Confidence:
- Whether decision matched mission state:

## Browser Actions

For each executed action include:

- Action type:
- Target selector:
- Intended semantic target:
- Execution success:
- Verification result:
- Selector recovery attempted:
- Selector recovery result:
- Execution feedback appended:

## Validation

- Report outcome present:
- SGV result:
- Rejected report prior step present:
- Goal convergence triggered:
- Strategy generation context present:
- Planner recovery mode present:

## Mission Snapshot

Paste the final or relevant Mission Snapshot:

```text
Mission Snapshot
Goal:
Mission Status:
Progress:
Completed:
Remaining:
Evidence Collected:
Known Blockers:
Current Focus:
Confidence:
```

## Workspace Snapshot

Paste relevant workspace summary:

```text
Workspace Summary
Goal:
Completed:
Pending:
Visited:
Facts:
Current Target:
```

## Tab Workspace Snapshot

Paste relevant tab workspace summary:

```text
Tab Workspace
Active:
Open Tabs:
Current Target:
```

## First Wrong Decision

- Turn:
- Component:
- Exact incorrect decision:
- Expected decision:
- Evidence available before the decision:
- Evidence missing before the decision:

## Root Cause

Choose one primary root cause:

- Planner
- Prompt
- Model limitation
- Context compression
- Mission State Manager
- Task Workspace
- Multi-Tab Workspace
- Grounding
- Browser execution
- Action verification
- Selector recovery
- Widget adapter
- File transfer
- Tab control
- SGV
- Goal Convergence
- Strategy Generation
- Planner Recovery
- Environment
- Website restriction
- Other:

## Smallest Fix

- Smallest production change:
- Why this is the smallest fix:
- What it explicitly does not change:

## Architectural Impact

- Affected subsystem:
- Upstream dependencies:
- Downstream consumers:
- Does this alter planner authority? Yes / No
- Does this alter browser execution? Yes / No
- Does this alter validation? Yes / No

## Regression Risk

- Risk level: Low / Medium / High
- Existing workflows at risk:
- Tests required:
- Manual validation required:

## Recommendation

- Recommended next action:
- Evidence supporting it:
- Do not implement during validation: confirmed / not confirmed
