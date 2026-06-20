from typing import Any


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
                completed.append(summary)
            else:
                failures.append({"step": summary, "error": data.get("execution_result", "unknown")})
        return {
            "verified_facts": verified_facts,
            "active_goal": active_goal,
            "completed_nodes": completed,
            "pending_nodes": [active_goal] if active_goal else [],
            "important_failures": failures[-5:],
        }
