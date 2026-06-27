"""Phase B — Execution Gateway V1 package.

The single runtime responsible for executing an approved ExecutionPlan (V9.0).
It orchestrates only: it dispatches abstract execution commands to a pluggable
adapter. The V1 adapter is a deterministic MOCK — no Playwright, Selenium, CDP,
DOM interaction, or network automation.
"""
