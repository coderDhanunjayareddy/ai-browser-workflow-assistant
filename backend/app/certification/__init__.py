"""
Phase F — Real Website Certification & Reliability Program.

Additive certification infrastructure. Does NOT introduce a new orchestration layer:
the runner constructs READY ExecutionPlans and delegates to the UNCHANGED Execution
Gateway (execute_plan_with_browser / gateway.start). It only builds inputs (plans +
scenarios) and evaluates outputs (ExecutionRecords), then rolls up reliability metrics,
a failure catalog, a workflow trace, and a certification report.

No new managers/engines. No redesign. No LLM/Vision/OCR/AI healing. No breaking APIs.
"""
