from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass

from app.grounding.models import GroundingResult
from app.grounding.resolver import GroundingResolver, planner_intent
from app.context_packet.models import PlannerPacket
from app.schemas.response import SuggestedAction
from app.semantic_page.graph import SemanticPageGraph
from app.semantic_page.serializers import stable_hash


@dataclass
class GroundingCacheResult:
    result: GroundingResult
    cache_hit: bool
    resolve_ms: int


class GroundingCache:
    def __init__(self, *, max_entries: int = 128, ttl_seconds: int = 300):
        self.max_entries = max(1, max_entries)
        self.ttl_seconds = max(1, ttl_seconds)
        self._entries: OrderedDict[str, tuple[float, GroundingResult]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get_or_resolve(
        self,
        *,
        run_id: str,
        action: SuggestedAction,
        graph: SemanticPageGraph,
        packet: PlannerPacket | None = None,
        resolver: GroundingResolver,
    ) -> GroundingCacheResult:
        started = time.perf_counter()
        key = self.cache_key(action=action, graph=graph)
        now = time.time()
        cached = self._entries.get(key)
        if cached and now - cached[0] <= self.ttl_seconds:
            self._hits += 1
            self._entries.move_to_end(key)
            result = cached[1].model_copy(deep=True)
            result.cache_hit = True
            result.replay_metadata["cache_key"] = key
            return GroundingCacheResult(
                result=result,
                cache_hit=True,
                resolve_ms=int((time.perf_counter() - started) * 1000),
            )

        self._misses += 1
        result = resolver.resolve(
            run_id=run_id,
            action=action,
            graph=graph,
            packet=packet,
            cache_hit=False,
        )
        result.replay_metadata["cache_key"] = key
        if result.status == "resolved":
            self._entries[key] = (now, result.model_copy(deep=True))
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
        return GroundingCacheResult(
            result=result,
            cache_hit=False,
            resolve_ms=int((time.perf_counter() - started) * 1000),
        )

    def cache_key(self, *, action: SuggestedAction, graph: SemanticPageGraph) -> str:
        selector_hash = stable_hash(action.target_selector or "", length=12)
        intent_hash = stable_hash(planner_intent(action), length=16)
        return (
            f"grounding_result.v1:{graph.schema_version}:{graph.graph_id}:"
            f"{action.action_type}:{intent_hash}:{selector_hash}"
        )

    def size(self) -> int:
        return len(self._entries)

    def hit_ratio(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0
