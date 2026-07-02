import re
from typing import Any


class RelevanceRanker:
    def __init__(self, limit: int = 30):
        self.limit = limit

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {term for term in re.findall(r"[a-z0-9]+", text.lower()) if len(term) > 2}

    def rank(self, task: str, elements: list[Any]) -> list[dict]:
        task_terms = self._terms(task)
        ranked: list[tuple[float, int, dict]] = []
        for index, item in enumerate(elements):
            data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            text = " ".join(str(data.get(key) or "") for key in (
                "text", "aria_label", "accessibility_name", "placeholder", "role", "type",
                "selector",
            ))
            overlap = len(task_terms & self._terms(text))
            score = overlap * 10 + (3 if data.get("visible", True) else 0)
            score += 2 if data.get("aria_label") or data.get("accessibility_name") else 0
            score += 1 if data.get("selector") else 0
            ranked.append((score, -index, data))
        ranked.sort(reverse=True, key=lambda row: (row[0], row[1]))
        return [data for _, _, data in ranked[: self.limit]]
