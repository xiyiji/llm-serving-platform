"""The platform engine: one object wiring every subsystem together.

Request path::

    API -> Platform.completion()
        -> KV cache lookup ------------------- hit: return cached
        -> WarmPool.acquire(model) ----------- cold start if needed
        -> Router.route(model) --------------- pick backend
        -> BatchScheduler.submit() ----------- micro-batch
        -> BackendAdapter.generate() --------- engine call
        -> KV cache store, metrics, alerts
"""
from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from ..config import Settings
from ..schemas import CompletionRequest, CompletionResponse
from .adapters import build_adapter
from .alerts import AlertManager
from .batching import BatchScheduler
from .deployment import DeploymentManager
from .kv_cache import KVCache
from .metrics import (
    ACTIVE,
    BATCH_SIZE,
    CACHE_HITS,
    COLD_START,
    ERRORS,
    LATENCY,
    REQUESTS,
    TOKENS,
    LatencyWindow,
)
from .registry import ModelRegistry
from .router import Router
from .warm_pool import WarmPool

log = logging.getLogger("gateway.platform")


class Platform:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.started_at = time.time()
        self.adapters = [build_adapter(b) for b in settings.backends]
        self.router = Router(
            self.adapters,
            strategy=settings.routing_strategy,
            default_backend=settings.default_backend,
        )
        self.warm_pool = WarmPool(
            capacity=settings.warm_pool_capacity,
            eviction_policy=settings.warm_pool_eviction,
            ttl_s=settings.warm_pool_ttl_s,
            load_time_s=settings.cold_start_load_s,
        )
        self.batcher = BatchScheduler(
            window_ms=settings.batch_window_ms,
            max_size=settings.batch_max_size,
            enabled=settings.batch_enabled,
        )
        self.kv_cache = KVCache(capacity=settings.kv_cache_capacity, enabled=settings.kv_cache_enabled)
        self.window = LatencyWindow()
        self.alerts = AlertManager()
        self.deployments = DeploymentManager()
        self.registry = ModelRegistry()

    # ---- request path ----

    def _cache_key(self, request: CompletionRequest, model: str) -> str:
        prompt = (
            "\n".join(f"{m.role}:{m.content}" for m in request.messages)
            if request.messages else (request.prompt or "")
        )
        return KVCache.key(model, prompt, request.temperature, request.max_tokens)

    async def completion(self, request: CompletionRequest, endpoint: str) -> CompletionResponse:
        model = request.model or self.settings.default_model
        key = self._cache_key(request, model)
        cached = self.kv_cache.lookup(key)
        if cached is not None:
            CACHE_HITS.labels(result="hit").inc()
            return cached.model_copy(update={"request_id": request.request_id, "cached": True})
        CACHE_HITS.labels(result="miss").inc()

        start = time.perf_counter()
        ACTIVE.inc()
        try:
            adapter = self.router.route(model)
            pooled = await self.warm_pool.acquire(model, adapter.name)
            if pooled.load_time_s:
                COLD_START.observe(pooled.load_time_s)

            async def run() -> CompletionResponse:
                return await adapter.generate(request, model)

            response = await self.batcher.submit(run)
            latency_ms = (time.perf_counter() - start) * 1000
            response.latency_ms = round(latency_ms, 2)

            adapter.record(latency_ms)
            pooled.request_count += 1
            pooled.total_latency_ms += latency_ms
            self.window.observe(latency_ms)
            REQUESTS.labels(endpoint=endpoint, model=model, backend=adapter.name).inc()
            LATENCY.labels(endpoint=endpoint).observe(latency_ms / 1000)
            TOKENS.labels(kind="prompt").inc(response.usage.prompt_tokens)
            TOKENS.labels(kind="completion").inc(response.usage.completion_tokens)
            BATCH_SIZE.observe(1)

            self.kv_cache.store(key, response)
            self._evaluate_alerts()
            return response
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            self.window.observe(latency_ms, error=True)
            ERRORS.labels(endpoint=endpoint, code=type(exc).__name__).inc()
            self._evaluate_alerts()
            raise
        finally:
            ACTIVE.dec()

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Yield text deltas; metrics recorded when the stream ends."""
        model = request.model or self.settings.default_model
        start = time.perf_counter()
        ACTIVE.inc()
        adapter = self.router.route(model)
        error = False
        try:
            pooled = await self.warm_pool.acquire(model, adapter.name)
            if pooled.load_time_s:
                COLD_START.observe(pooled.load_time_s)
            async for delta in adapter.stream(request, model):
                yield delta
        except Exception:
            error = True
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            adapter.record(latency_ms, error=error)
            self.window.observe(latency_ms, error=error)
            REQUESTS.labels(endpoint="chat_stream", model=model, backend=adapter.name).inc()
            LATENCY.labels(endpoint="chat_stream").observe(latency_ms / 1000)
            ACTIVE.dec()
            self._evaluate_alerts()

    # ---- observability ----

    def _alert_snapshot(self) -> dict:
        return {
            **self.window.snapshot(),
            "queue_depth": self.batcher.max_queue_depth,
            "avg_cold_start_s": self.warm_pool.status()["avg_cold_start_s"],
        }

    def _evaluate_alerts(self) -> None:
        self.alerts.evaluate(self._alert_snapshot())

    def health(self) -> dict:
        return {
            "status": "healthy",
            "uptime_s": round(time.time() - self.started_at, 1),
            "details": {
                "backends": len(self.adapters),
                "models_warm": self.warm_pool.status()["pool_size"],
                "active_alerts": len(self.alerts.active),
                **self.window.snapshot(),
            },
        }

    def models(self) -> list[dict]:
        mapping = self.router.model_backend_mapping()
        pool = {m.model_id: m for m in self.warm_pool.models.values()}
        out = []
        for model, backend in mapping.items():
            entry = pool.get(model)
            out.append(
                {
                    "id": model,
                    "status": entry.status if entry else "cold",
                    "backend": backend,
                    "request_count": entry.request_count if entry else 0,
                    "avg_latency_ms": round(entry.avg_latency_ms, 2) if entry else 0.0,
                }
            )
        return out
