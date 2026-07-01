"""
Isolated diagnostics layer (M0.6).

Exists ONLY to record what the planner received and produced when TRACE_MODE is enabled.
Nothing here influences planning, prompts, parsing, or execution. Every entry point is a
no-op unless settings.trace_mode is true, and no entry point may raise into the caller.
"""
