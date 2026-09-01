"""Cold-start management: model lifecycle and warm pool.

A model is *cold* until it has been loaded once; loading is simulated with a
configurable delay (with a real engine this is weight loading + CUDA graph
capture). Loaded models live in a bounded warm pool with a pluggable
eviction policy (LRU / LFU / TTL). ``prefetch`` warms a model ahead of the
first request that needs it.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class PooledModel:
    model_id: str
    backend: str
    status: str = "loading"  # loading | warm | evicted
    loaded_at: float = 0.0
    last_used: float = 0.0
    use_count: int = 0
    load_time_s: float = 0.0
    request_count: int = 0
    total_latency_ms: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.request_count if self.request_count else 0.0


class WarmPool:
    def __init__(
        self,
        capacity: int = 4,
        eviction_policy: str = "lru",
        ttl_s: float = 600.0,
        load_time_s: float = 1.2,
    ):
        self.capacity = capacity
        self.eviction_policy = eviction_policy
        self.ttl_s = ttl_s
        self.load_time_s = load_time_s
        self.models: dict[str, PooledModel] = {}
        self.cold_starts = 0
        self.warm_hits = 0
        self.evictions = 0
        self.total_cold_start_s = 0.0

    async def acquire(self, model_id: str, backend: str) -> PooledModel:
        """Return a warm model, loading it first if needed."""
        self._expire_ttl()
        entry = self.models.get(model_id)
        if entry and entry.status == "warm":
            self.warm_hits += 1
        else:
            entry = self.models.setdefault(model_id, PooledModel(model_id, backend))
            async with entry.lock:
                if entry.status != "warm":  # re-check after awaiting the lock
                    await self._load(entry)
        entry.last_used = time.time()
        entry.use_count += 1
        return entry

    async def _load(self, entry: PooledModel) -> None:
        self.cold_starts += 1
        start = time.perf_counter()
        entry.status = "loading"
        await asyncio.sleep(self.load_time_s)
        entry.load_time_s = round(time.perf_counter() - start, 3)
        self.total_cold_start_s += entry.load_time_s
        entry.status = "warm"
        entry.loaded_at = time.time()
        self._evict_if_needed(keep=entry.model_id)

    async def prefetch(self, model_id: str, backend: str) -> PooledModel:
        return await self.acquire(model_id, backend)

    def unload(self, model_id: str) -> bool:
        if model_id in self.models:
            del self.models[model_id]
            self.evictions += 1
            return True
        return False

    def _warm(self) -> list[PooledModel]:
        return [m for m in self.models.values() if m.status == "warm"]

    def _expire_ttl(self) -> None:
        if self.eviction_policy != "ttl":
            return
        now = time.time()
        for m in list(self._warm()):
            if now - m.last_used > self.ttl_s:
                self.unload(m.model_id)

    def _evict_if_needed(self, keep: str) -> None:
        warm = self._warm()
        while len(warm) > self.capacity:
            candidates = [m for m in warm if m.model_id != keep]
            if not candidates:
                break
            if self.eviction_policy == "lfu":
                victim = min(candidates, key=lambda m: m.use_count)
            else:  # lru and ttl both fall back to least-recently-used
                victim = min(candidates, key=lambda m: m.last_used)
            self.unload(victim.model_id)
            warm = self._warm()

    def status(self) -> dict:
        return {
            "pool_size": len(self._warm()),
            "pool_capacity": self.capacity,
            "strategy": "on_demand_load_with_prefetch",
            "eviction_policy": self.eviction_policy,
            "models": [
                {
                    "id": m.model_id,
                    "status": m.status,
                    "backend": m.backend,
                    "load_time_s": m.load_time_s,
                    "use_count": m.use_count,
                    "last_used": m.last_used,
                }
                for m in self.models.values()
            ],
            "cold_starts": self.cold_starts,
            "warm_hits": self.warm_hits,
            "evictions": self.evictions,
            "avg_cold_start_s": round(
                self.total_cold_start_s / self.cold_starts, 3
            ) if self.cold_starts else 0.0,
        }
