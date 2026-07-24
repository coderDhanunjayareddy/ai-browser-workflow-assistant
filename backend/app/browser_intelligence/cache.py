from __future__ import annotations

from collections import OrderedDict
from typing import Any


class BoundedCache:
    def __init__(self, max_size: int = 64) -> None:
        self.max_size = max_size
        self._items: OrderedDict[str, Any] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        if key not in self._items:
            self.misses += 1
            return None
        self.hits += 1
        value = self._items.pop(key)
        self._items[key] = value
        return value

    def set(self, key: str, value: Any) -> None:
        if key in self._items:
            self._items.pop(key)
        self._items[key] = value
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "size": len(self._items),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }
