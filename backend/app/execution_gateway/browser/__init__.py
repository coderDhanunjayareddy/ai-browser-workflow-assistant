"""
Phase C — Real Browser Execution package (Playwright Adapter V1).

Replaces ONLY the MockBrowserAdapter with a real Playwright implementation behind
the existing ExecutionAdapter contract. The Execution Gateway, Dispatcher, Runner,
Retry / Validation / Rollback engines, and all upstream layers are UNCHANGED.

All Playwright imports are lazy (inside methods) so this package imports cleanly even
where Playwright/Chromium are not installed; unit tests inject fake page objects.
"""
