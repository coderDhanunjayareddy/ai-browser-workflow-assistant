# PVS-2 Completion Criteria

PVS-2 is complete only when the production validation framework has produced enough evidence to prioritize the next production engineering milestone.

## Required Execution Coverage

- All 100 tasks in `master-task-suite.md` executed at least once.
- Every category has at least one completed task or documented blocker.
- Every Hard task has a failure report if not completed.
- Every environmental blocker is separated from architecture failures.
- Every invalid run is rerun once after environment correction.

## Required Documentation Coverage

- Each failed or partial task has a completed failure report.
- Each failure report identifies the first wrong decision.
- Each failure report assigns one primary taxonomy code.
- Each failure report proposes exactly one smallest production fix.
- Each failure report includes Mission Snapshot and Workspace Snapshot evidence when available.
- Every recommendation is evidence-backed.

## Required Metrics Coverage

Aggregate metrics must include:

- Task Success Rate
- Partial Completion Rate
- Environmental Block Rate
- Planner Accuracy
- Execution Success Rate
- Verified Action Effect Rate
- Selector Recovery Rate
- Selector Recovery Success Rate
- SGV Acceptance/Rejection Rate
- Goal Convergence Frequency
- Strategy Generation Frequency
- Planner Recovery Frequency
- Average Planner Turns
- Average Browser Actions
- Average Completion Time
- Mission Progress Accuracy
- First Failure Layer Distribution

## Evidence Quality Bar

A run is valid only if:

- The production extension was used.
- The backend was healthy.
- The provider/model configuration was recorded.
- The browser state was known.
- The task was run as written.
- Trace or timeline evidence exists.
- The operator did not manually steer the workflow beyond normal approvals/user inputs.

## Prioritization Output

At completion, produce one roadmap-prioritization report containing:

- Top five architectural bottlenecks by failed-task count.
- Top five architectural bottlenecks by expected user impact.
- Top five lowest-risk fixes.
- Capabilities that are working reliably.
- Capabilities that are present but underused.
- Capabilities still blocked by environment/auth/site restrictions.
- One recommended next engineering milestone.

## Stop Condition

PVS-2 ends when:

- 100 tasks have valid outcomes.
- All non-completed outcomes are classified.
- Metrics are aggregated.
- Architectural gaps are ranked by evidence.
- The next production milestone can be selected without speculation.
