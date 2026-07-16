# Production Validation Metrics

These metrics define PVS-2 success measurement. Collect them per task and aggregate by category, difficulty, website, and root-cause taxonomy.

## Core KPIs

| Metric | Definition | Formula / Measurement | Target Use |
|---|---|---|---|
| Task Success Rate | Percentage of tasks that fully satisfy success criteria. | completed / executed tasks | Overall production readiness |
| Partial Completion Rate | Tasks that gather some evidence but do not satisfy goal. | partial / executed tasks | Detect near-miss workflows |
| Environmental Block Rate | Tasks blocked by auth, CAPTCHA, rate limit, network, permissions. | environmental / executed tasks | Separate architecture from environment |
| Planner Accuracy | Planner turns whose chosen outcome/action matches mission needs. | correct planner turns / total planner turns | Planner quality |
| Outcome Contract Validity | Planner responses conforming to Planner Contract V2. | valid responses / planner responses | Contract health |
| Execution Success Rate | Browser actions that execute without runtime error. | successful executions / attempted executions | Browser execution health |
| Action Verification Rate | Executions with verification metadata. | verified actions / executions | Verification coverage |
| Verified Action Effect Rate | Executions verified as producing intended browser effect. | verification.verified / executions | Real browser success |
| No-Effect Rate | Executions that technically run but do not change meaningful state. | no_effect / executions | Selector/widget quality |
| Selector Recovery Rate | Eligible no-effect actions that attempt selector recovery. | recovery_attempted / eligible no_effect | Recovery coverage |
| Selector Recovery Success Rate | Recovery attempts that verify successfully. | recovery_verified / recovery_attempted | Selector recovery value |
| Widget Adapter Activation Rate | Actions routed through widget adapters. | adapter actions / executions | Dynamic UI coverage |
| Widget Adapter Success Rate | Adapter actions verified successful. | adapter verified / adapter actions | Widget reliability |
| File Upload Success Rate | Upload tasks completed and verified. | upload_completed / upload_attempted | Upload readiness |
| File Download Success Rate | Downloads completed with metadata. | download_completed / download_detected | Download readiness |
| Tab Control Success Rate | Tab operations verified. | verified tab ops / attempted tab ops | Multi-tab execution readiness |
| SGV Acceptance Rate | Report outcomes accepted by semantic validation. | sgv_verified / report outcomes | Report validity |
| SGV Rejection Rate | Report outcomes rejected and continued. | rejected reports / report outcomes | Premature reporting signal |
| Report Continuation Rate | Rejected reports followed by another planner turn. | continued rejected reports / rejected reports | PRC-1 health |
| Goal Convergence Frequency | Tasks where GC detects stagnation. | tasks with GC / executed tasks | Stagnation prevalence |
| Strategy Generation Frequency | Tasks receiving SG context. | tasks with SG / executed tasks | Recovery-context usage |
| Planner Recovery Frequency | Tasks entering PR mode. | tasks with PR / executed tasks | Recovery demand |
| Recovery Outcome Success Rate | PR turns that lead to new useful progress. | successful PR turns / PR turns | Recovery value |
| Average Planner Turns | Mean planner calls per task. | sum planner turns / tasks | Efficiency |
| Average Browser Actions | Mean executed actions per task. | sum actions / tasks | Efficiency |
| Average Completion Time | Mean wall-clock time for completed tasks. | sum completed durations / completed tasks | User experience |
| Average Recovery Attempts | Mean selector/widget/recovery attempts. | sum attempts / tasks | Execution friction |
| Mission Progress Accuracy | Whether Mission Snapshot progress matches actual task state. | manual rating: accurate / partial / wrong | MSM-1 quality |
| Workspace Fact Precision | Extracted facts that are relevant and correct. | correct facts / extracted facts sampled | Workspace quality |
| Tab Workspace Accuracy | Tab summaries matching actual open tabs and purposes. | correct tab summaries / sampled summaries | Multi-tab memory health |
| First Failure Turn | Earliest turn where progress diverges. | manual turn index | Root-cause priority |
| First Failure Layer Distribution | Count by taxonomy layer. | failures grouped by root cause | Roadmap prioritization |

## Per-Task Required Fields

- Task ID
- Category
- Difficulty
- Website
- Final status
- Planner turns
- Browser actions
- Completion time
- Report outcomes
- SGV verified/rejected
- Goal convergence count
- Strategy generation count
- Planner recovery count
- Selector recovery attempts/successes
- Widget adapter attempts/successes
- Upload/download attempts/successes
- Tab operations attempts/successes
- Mission progress accuracy
- First wrong decision
- Root cause
- Smallest fix

## Aggregation Views

### By Category

Use to identify product-surface bottlenecks such as shopping, GitHub, SaaS, or multi-tab research.

### By Architecture Layer

Use to decide the next engineering milestone.

### By Difficulty

Use to distinguish MVP readiness from advanced autonomy.

### By Website Restriction

Track auth, CAPTCHA, bot defenses, and rate limits separately from system failures.

### By Workflow Length

Group by:

- Short: 1-5 actions
- Medium: 6-15 actions
- Long: 16+ actions

Long-running workflow degradation should be attributed to memory, mission state, workspace, tab management, or planner drift only when supported by trace evidence.
