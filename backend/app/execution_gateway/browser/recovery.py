"""
Phase D — RecoveryEngine.

Deterministic recovery actions executed BEFORE a retry, driven by the FailureProfile's
recommended_recovery list. NO AI. NO LLM. Pure deterministic browser operations:

  ElementNotFound     -> wait + refresh locator
  ElementHidden       -> scroll into view
  DetachedElement     -> re-query (recover page)
  NavigationTimeout   -> wait for network idle
  NetworkIdleTimeout  -> wait
  PageCrash           -> reload page
  ValidationFailure   -> re-read page
  UnexpectedPopup     -> dismiss popup
  DownloadTimeout     -> wait

Best-effort: each action is guarded; a recovery never raises into the adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.execution_gateway.browser import adaptive_resolver
from app.execution_gateway.browser.failure_classes import FailureAnalysis, RecoveryAction

DEFAULT_RECOVERY_WAIT_MS:   int = 300
DEFAULT_NETWORK_IDLE_MS:    int = 3000


@dataclass
class RecoveryResult:
    category:  str
    actions:   list[str]      = field(default_factory=list)
    recovered: bool           = False
    notes:     list[str]      = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category":  self.category,
            "actions":   self.actions,
            "recovered": self.recovered,
            "notes":     self.notes,
        }


class RecoveryEngine:

    def recover(self, analysis: FailureAnalysis, session: Any, command: Any) -> RecoveryResult:
        result = RecoveryResult(category=analysis.category.value)
        params = getattr(command, "parameters", {}) or {}
        for action in analysis.profile.recommended_recovery:
            if action == RecoveryAction.none:
                continue
            ok = self._do(action, session, params, result)
            result.actions.append(action.value)
            if not ok:
                result.notes.append(f"{action.value} did not complete cleanly")
        # "recovered" = at least one concrete recovery action executed without error.
        result.recovered = bool(result.actions) and not result.notes
        return result

    def _do(self, action: RecoveryAction, session: Any, params: dict, result: RecoveryResult) -> bool:
        try:
            page = session.ensure_page()
        except Exception:
            return False
        try:
            if action == RecoveryAction.wait:
                page.wait_for_timeout(int(params.get("recovery_wait_ms", DEFAULT_RECOVERY_WAIT_MS)))
                return True
            if action == RecoveryAction.scroll_into_view:
                resolved = adaptive_resolver.resolve(page, params)
                resolved.locator.scroll_into_view_if_needed()
                return True
            if action == RecoveryAction.refresh_locator:
                # Re-querying happens on the next attempt; confirm a locator can be built.
                if adaptive_resolver.strategy_for(params):
                    adaptive_resolver.resolve(page, params)
                return True
            if action == RecoveryAction.requery:
                session.ensure_page()   # recover a detached/closed page
                return True
            if action == RecoveryAction.wait_network_idle:
                page.wait_for_load_state("networkidle",
                                         timeout=int(params.get("network_idle_ms", DEFAULT_NETWORK_IDLE_MS)))
                return True
            if action == RecoveryAction.reload_page:
                session.refresh()
                return True
            if action == RecoveryAction.reread_page:
                # No browser action needed; the next read re-reads fresh content.
                return True
            if action == RecoveryAction.dismiss_popup:
                return self._dismiss_popup(session)
        except Exception as e:
            result.notes.append(f"{action.value}: {type(e).__name__}")
            return False
        return False

    @staticmethod
    def _dismiss_popup(session: Any) -> bool:
        try:
            context = getattr(session, "context", None)
            page = session.ensure_page()
            if context is not None and hasattr(context, "pages"):
                for p in list(context.pages):
                    if p is not page:
                        try:
                            p.close()
                        except Exception:
                            pass
            return True
        except Exception:
            return False


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = RecoveryEngine()


def recover(analysis: FailureAnalysis, session: Any, command: Any) -> RecoveryResult:
    return _engine.recover(analysis, session, command)
