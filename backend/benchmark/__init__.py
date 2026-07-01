"""
M0 — Real Website Benchmark.

The single source of truth for real-world browser task completion. Drives the LIVE
/analyze loop (real Gemini reasoning) against real websites + local fixtures, in two
executor modes (Playwright trusted input vs the extension's synthetic events), and
produces JSON / Markdown / HTML reports plus a locked baseline.

Reuses the Phase F certification framework (app.certification.{reliability,failure_catalog,
trace,fixtures}) rather than duplicating it. See docs/benchmark-m0.md.
"""
