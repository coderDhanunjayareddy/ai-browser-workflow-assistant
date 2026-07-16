# Production Validation Sprint 2

PVS-2 is a production QA framework for validating the real browser assistant on real websites. It is documentation-only and must not change product code, prompts, execution, validation, or benchmark logic.

## Files

- `master-task-suite.md` — 100 real-world browser tasks.
- `failure-report-template.md` — reusable investigation template.
- `production-metrics.md` — measurable KPIs and aggregation rules.
- `failure-taxonomy.md` — root-cause classification system.
- `validation-procedure.md` — exact run procedure for every task.
- `completion-criteria.md` — definition of PVS-2 done.

## Recommended Execution Order

1. Smoke set from `master-task-suite.md`.
2. All Easy tasks.
3. Medium tasks by category.
4. Hard tasks by category.
5. Multi-tab, cross-site, and long-running tasks.
6. Rerun invalid environmental runs once.
7. Aggregate metrics and classify failures.

## Validation Principle

The validator's job is to identify the earliest architectural failure using evidence. Do not implement fixes during validation.
