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
        ranked: list[tuple[float, float, float, int, dict]] = []
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
            # Action relevance: a genuine actionable control (a real button / native
            # submit) is a better target for an action than a same-scoring navigational
            # link decoy (e.g. Amazon's #nav-assist-search shortcut hint).
            actionable = data.get("role") == "button" or data.get("input_type") in ("submit", "button")
            score += 3 if actionable else 0
            bbox = data.get("bounding_box") or {}
            bbox_y = bbox.get("y", 0) or 0
            bbox_x = bbox.get("x", 0) or 0
            # Ties: prefer topmost, then leftmost, then earliest DOM order.
            ranked.append((score, -bbox_y, -bbox_x, -index, data))
        ranked.sort(reverse=True, key=lambda row: (row[0], row[1], row[2], row[3]))
        return [data for *_, data in ranked[: self.limit]]
