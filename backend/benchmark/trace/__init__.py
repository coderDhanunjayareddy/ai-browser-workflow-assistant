"""
M0.6 — Benchmark planner-observability layer.

Reconstructs, for every benchmark step, ONE complete execution record (observation →
planner input → provider request → raw provider response → parsed action → executor →
validation → loop decision) and renders a self-contained HTML viewer.

Completely isolated + optional: when tracing is disabled the recorder is a no-op and the
benchmark behaves identically. See docs/trace-observability.md.
"""
