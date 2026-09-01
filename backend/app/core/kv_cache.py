"""Prefix cache abstraction with LRU eviction.

At gateway level we cache full responses keyed by a hash of
(model, normalised prompt, sampling params). This models the benefit of
engine-level KV/prefix caching — repeated system prompts and identical
requests skip the expensive path — and produces the same statistics
(hit rate, evictions, tokens saved) an engine cache would report.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from typing import Any


class KVCache:
    def __init__(self, capacity: int = 512, enabled: bool = True):
        self.capacity = capacity
        self.enabled = enabled
        self._store: OrderedDict[str, Any] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.tokens_saved = 0

    @staticmethod
    def key(model: str, prompt: str, temperature: float, max_tokens: int) -> str:
        raw = f"{model}|{temperature}|{max_tokens}|{prompt.strip()}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def lookup(self, key: str) -> Any | None:
        if not self.enabled:
            return None
        if key in self._store:
            self.hits += 1
            self._store.move_to_end(key)
            value = self._store[key]
            self.tokens_saved += getattr(getattr(value, "usage", None), "total_tokens", 0)
            return value
        self.misses += 1
        return None

    def store(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        self._store[key] = value
        self._store.move_to_end(key)
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)
            self.evictions += 1

    def invalidate(self, key: str | None = None) -> int:
        if key is None:
            n = len(self._store)
            self._store.clear()
            return n
        return 1 if self._store.pop(key, None) is not None else 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "size": len(self._store),
            "capacity": self.capacity,
            "hit_rate": self.hit_rate,
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "evictions": self.evictions,
            "tokens_saved": self.tokens_saved,
        }
