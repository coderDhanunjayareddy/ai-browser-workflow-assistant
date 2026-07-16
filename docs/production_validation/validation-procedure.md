# Production Validation Procedure

This procedure must be followed for every PVS-2 task. Do not implement fixes during validation.

## Pre-Run Checklist

1. Confirm backend is running and healthy.
2. Confirm extension build under test is loaded.
3. Confirm provider/model configuration.
4. Confirm browser profile and authentication state.
5. Confirm task ID, goal, website, difficulty, max planner turns, and max browser actions.
6. Start trace/log capture if available.
7. Reset irrelevant tabs unless task requires existing tabs.
8. Record start time.

## Execution Workflow

1. Start the task exactly as written in the Master Task Suite.
2. Let the production assistant run through the normal workflow.
3. Do not manually correct planner actions unless the task explicitly requires user input or approval.
4. If approval is required, approve only actions that a real user would safely approve.
5. Stop immediately when success criteria are met.
6. Stop when max planner turns or browser actions are reached.
7. Stop on environmental blockers such as auth wall, CAPTCHA, rate limit, network failure, or permission block.

## Required Artifacts Per Task

Save or record:

- Planner timeline
- Browser action timeline
- Execution verification results
- Selector recovery metadata
- Widget adapter metadata if used
- File transfer metadata if used
- Tab control metadata if used
- Mission Snapshot
- Task Workspace summary
- Multi-Tab Workspace summary
- SGV outcomes
- Goal Convergence events
- Strategy Generation context
- Planner Recovery events
- Final browser state
- Final task status

## Outcome Classification

Use one:

- Completed: all success criteria satisfied.
- Partial: meaningful progress, but success criteria incomplete.
- Failed: architecture failed before success.
- Blocked: external website/environment prevented progress.
- Invalid Run: test setup broken; rerun allowed after environment fix.

## Failure Investigation

If the task is not Completed:

1. Reconstruct every planner turn.
2. Reconstruct every browser action.
3. Identify the first turn where progress diverged.
4. Determine what evidence was available before that decision.
5. Determine what evidence was missing before that decision.
6. Classify the earliest root cause using `failure-taxonomy.md`.
7. Record the smallest production change that would remove that blocker.
8. Record regression risk.
9. Do not implement the fix.

## Evidence Rules

- Use trace evidence, planner request/response, page observations, and execution metadata.
- Do not infer planner intent unless the planner response states it.
- Do not blame the planner if required evidence was missing from context.
- Do not blame execution if the planner chose the wrong semantic target.
- Do not blame SGV for rejecting unsupported reports.
- Separate website restrictions from assistant failures.

## Post-Run Metrics

For every task, record:

- Final status
- Planner turns
- Browser actions
- Completion time
- First failure turn
- Primary taxonomy code
- Secondary taxonomy codes
- Task success
- Partial completion
- Execution success rate
- Verification success rate
- Selector recovery attempts/successes
- SGV accept/reject count
- GC/SG/PR activation count
- Mission progress accuracy
- Workspace accuracy notes
- Tab workspace accuracy notes

## Review Cadence

- Daily: review smoke failures and invalid runs.
- Weekly: aggregate category-level success and failure taxonomy.
- Release: run all 100 tasks and produce a prioritized architecture gap report.

## Strict Boundary

Validation operators must not:

- Modify code.
- Modify planner prompts.
- Modify browser execution.
- Add benchmark scenarios.
- Change scoring.
- Patch a site-specific workaround.
- Continue debugging after identifying the earliest failure unless needed to classify it.
