from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass

from app.schemas.request import PageContext
from app.semantic_page.builder import BUILDER_VERSION, SemanticPageGraphBuilder, observation_hash
from app.semantic_page.graph import SemanticPageGraph


@dataclass(frozen=True)
class SemanticGraphCacheResult:
    graph: SemanticPageGraph
    cache_hit: bool
    build_ms: int


class SemanticGraphCache:
    def __init__(self, *, max_entries: int = 64, ttl_seconds: int = 300):
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = max(1, ttl_seconds)
        self._entries: OrderedDict[str, tuple[float, SemanticPageGraph]] = OrderedDict()
        self._builder = SemanticPageGraphBuilder()
        self.hits = 0
        self.misses = 0

    def cache_key(self, page_context: PageContext) -> str:
        return f"semantic_page_graph.v1:{BUILDER_VERSION}:{observation_hash(page_context)}"

    def get_or_build(self, page_context: PageContext) -> SemanticGraphCacheResult:
        started = time.perf_counter()
        key = self.cache_key(page_context)
        now = time.time()
        cached = self._entries.get(key)
        if cached is not None:
            cached_at, graph = cached
            if now - cached_at <= self.ttl_seconds:
                self._entries.move_to_end(key)
                self.hits += 1
                return SemanticGraphCacheResult(
                    graph=graph,
                    cache_hit=True,
                    build_ms=int((time.perf_counter() - started) * 1000),
                )
            del self._entries[key]

        self.misses += 1
        graph = self._builder.build(page_context)
        self._entries[key] = (now, graph)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        return SemanticGraphCacheResult(
            graph=graph,
            cache_hit=False,
            build_ms=int((time.perf_counter() - started) * 1000),
        )

    def hit_ratio(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def size(self) -> int:
        return len(self._entries)
