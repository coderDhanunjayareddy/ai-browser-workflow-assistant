from typing import Any, Optional


def _infer_page_changed(execution_result: str) -> Optional[bool]:
    """
    M1.1: best-effort read of a progress signal out of execution_result. No caller writes
    a progress-qualified string yet (extension/benchmark still send bare "success"/an error
    message) — that convention is introduced by a later milestone — so this returns None
    (unknown) for every caller today. It exists now so completed_nodes entries carry the
    field without a second edit to this file once callers start writing qualified strings.
    """
    text = (execution_result or "").lower()
    if "unchanged" in text or "no change" in text or "did not change" in text:
        return False
    if "page changed" in text or "navigated" in text:
        return True
    return None


class StateSummarizer:
    def summarize(
        self,
        *,
        active_goal: str,
        verified_facts: dict[str, Any],
        prior_steps: list[Any],
    ) -> dict[str, Any]:
        completed, failures = [], []
        for step in prior_steps[-10:]:
            data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
            summary = data.get("description") or data.get("action_type") or "workflow step"
            if str(data.get("execution_result", "")).lower() == "success":
                # M1.1: preserve the selector/action/value so this successful step is
                # usable as episodic memory, not just a name in a completed-count.
                completed.append({
                    "description": summary,
                    "selector": data.get("target_selector"),
                    "action_type": data.get("action_type"),
                    "value": data.get("value"),
                    "page_changed": _infer_page_changed(data.get("execution_result", "")),
                })
            else:
                failures.append({"step": summary, "error": data.get("execution_result", "unknown")})
        return {
            "verified_facts": verified_facts,
            "active_goal": active_goal,
            "completed_nodes": completed,
            "pending_nodes": [active_goal] if active_goal else [],
            "important_failures": failures[-5:],
        }
