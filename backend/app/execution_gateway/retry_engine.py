"""
Phase B — Execution Gateway V1 — Retry Engine.

Deterministic, bounded retry policy. NEVER loops infinitely: the number of attempts
is strictly bounded by RetryConfig.max_attempts (= max_retries + 1).
"""
from __future__ import annotations

from app.execution_gateway.models import RetryConfig


class RetryEngine:

    def should_retry(
        self,
        attempt: int,                 # 1-based attempt number that just ran
        config:  RetryConfig,
        *,
        dispatch_failed:    bool,
        validation_failed:  bool,
    ) -> bool:
        """
        Decide whether another attempt is allowed after a failed attempt.

        attempt is the number of the attempt that just completed (1 = first run).
        Returns False once attempt has reached max_attempts (hard upper bound).
        """
        if attempt >= config.max_attempts:
            return False
        if dispatch_failed:
            return True
        if validation_failed:
            return config.retry_on_validation_failure
        return False

    def attempts_allowed(self, config: RetryConfig) -> int:
        return config.max_attempts


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = RetryEngine()


def should_retry(attempt: int, config: RetryConfig, *, dispatch_failed: bool, validation_failed: bool) -> bool:
    return _engine.should_retry(attempt, config, dispatch_failed=dispatch_failed, validation_failed=validation_failed)

def attempts_allowed(config: RetryConfig) -> int:
    return _engine.attempts_allowed(config)
