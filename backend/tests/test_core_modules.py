"""Unit tests for router, batching, KV cache and warm pool."""
import asyncio

import pytest

from app.config import BackendConfig
from app.core.adapters import SimulatedAdapter, build_adapter
from app.core.batching import BatchScheduler
from app.core.kv_cache import KVCache
from app.core.router import Router
from app.core.warm_pool import WarmPool


def _adapters():
    return [
        build_adapter(BackendConfig(name="a", models=["m1", "m2"])),
        build_adapter(BackendConfig(name="b", models=["m2"])),
    ]


def test_router_respects_model_mapping():
    router = Router(_adapters(), strategy="round_robin")
    assert router.route("m1").name == "a"
    chosen = {router.route("m2").name for _ in range(10)}
    assert chosen == {"a", "b"}


def test_router_latency_strategy_prefers_faster_backend():
    a, b = _adapters()
    a.record(500.0)
    b.record(10.0)
    router = Router([a, b], strategy="latency")
    assert router.route("m2").name == "b"


def test_router_adaptive_avoids_erroring_backend():
    a, b = _adapters()
    b.record(1.0)
    for _ in range(10):
        a.record(1.0, error=True)  # 100% error rate but lower latency ties
    router = Router([a, b], strategy="adaptive")
    assert router.route("m2").name == "b"


@pytest.mark.asyncio
async def test_batch_scheduler_groups_requests():
    scheduler = BatchScheduler(window_ms=20, max_size=4)

    async def work(i):
        return i * 2

    results = await asyncio.gather(*(scheduler.submit(lambda i=i: work(i)) for i in range(8)))
    assert sorted(results) == [i * 2 for i in range(8)]
    stats = scheduler.stats()
    assert stats["total_batches"] >= 1
    assert stats["avg_batch_size"] > 1  # actually batched, not one-by-one


@pytest.mark.asyncio
async def test_batch_scheduler_propagates_errors():
    scheduler = BatchScheduler(window_ms=5, max_size=2)

    async def boom():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        await scheduler.submit(boom)


def test_kv_cache_lru_eviction_and_stats():
    cache = KVCache(capacity=2)
    k1, k2, k3 = (KVCache.key("m", p, 0.0, 10) for p in ("a", "b", "c"))
    cache.store(k1, "r1")
    cache.store(k2, "r2")
    assert cache.lookup(k1) == "r1"  # refresh k1
    cache.store(k3, "r3")            # evicts k2 (LRU)
    assert cache.lookup(k2) is None
    assert cache.lookup(k3) == "r3"
    stats = cache.stats()
    assert stats["evictions"] == 1
    assert stats["cache_hits"] == 2 and stats["cache_misses"] == 1


@pytest.mark.asyncio
async def test_warm_pool_cold_then_warm():
    pool = WarmPool(capacity=2, load_time_s=0.01)
    first = await pool.acquire("m1", "a")
    assert first.status == "warm"
    assert pool.cold_starts == 1
    await pool.acquire("m1", "a")
    assert pool.warm_hits == 1


@pytest.mark.asyncio
async def test_warm_pool_lru_eviction():
    pool = WarmPool(capacity=2, load_time_s=0.0)
    for m in ("m1", "m2", "m3"):
        await pool.acquire(m, "a")
    status = pool.status()
    assert status["pool_size"] == 2
    warm_ids = {m["id"] for m in status["models"] if m["status"] == "warm"}
    assert "m1" not in warm_ids  # least recently used got evicted


@pytest.mark.asyncio
async def test_simulated_adapter_streams_words():
    adapter = SimulatedAdapter(BackendConfig(name="x"))
    from app.schemas import CompletionRequest

    req = CompletionRequest(prompt="hello world")
    chunks = [c async for c in adapter.stream(req, "m")]
    assert len(chunks) > 3
    full = "".join(chunks)
    assert len(full.split()) >= 8
