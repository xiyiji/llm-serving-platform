"""Dynamic micro-batching.

Requests entering ``submit()`` are queued; a batch is dispatched when either
the time window closes or the batch reaches ``max_size``. Each request in
the batch is executed concurrently against the backend (with a real engine
the batch would become one forward pass; the scheduler and its statistics
are engine-agnostic either way).
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Pending:
    run: Callable[[], Awaitable[Any]]
    future: asyncio.Future = field(default_factory=asyncio.Future)
    enqueued_at: float = field(default_factory=time.perf_counter)


class BatchScheduler:
    def __init__(self, window_ms: float = 8.0, max_size: int = 8, enabled: bool = True):
        self.window_ms = window_ms
        self.max_size = max_size
        self.enabled = enabled
        self._queue: list[_Pending] = []
        self._flush_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

        # stats
        self.total_batches = 0
        self.total_requests = 0
        self.total_batched_requests = 0
        self.total_wait_ms = 0.0
        self.max_queue_depth = 0
        self.size_triggered = 0
        self.window_triggered = 0

    async def submit(self, run: Callable[[], Awaitable[Any]]) -> Any:
        """Schedule a unit of work; resolves with its result."""
        self.total_requests += 1
        if not self.enabled:
            return await run()

        pending = _Pending(run)
        async with self._lock:
            self._queue.append(pending)
            self.max_queue_depth = max(self.max_queue_depth, len(self._queue))
            if len(self._queue) >= self.max_size:
                self.size_triggered += 1
                self._dispatch_locked()
            elif self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._window_flush())
        return await pending.future

    async def _window_flush(self) -> None:
        await asyncio.sleep(self.window_ms / 1000)
        async with self._lock:
            if self._queue:
                self.window_triggered += 1
                self._dispatch_locked()

    def _dispatch_locked(self) -> None:
        batch, self._queue = self._queue, []
        if not batch:
            return
        self.total_batches += 1
        self.total_batched_requests += len(batch)
        now = time.perf_counter()
        for p in batch:
            self.total_wait_ms += (now - p.enqueued_at) * 1000
        asyncio.create_task(self._run_batch(batch))

    async def _run_batch(self, batch: list[_Pending]) -> None:
        results = await asyncio.gather(*(p.run() for p in batch), return_exceptions=True)
        for p, result in zip(batch, results):
            if p.future.cancelled():
                continue
            if isinstance(result, BaseException):
                p.future.set_exception(result)
            else:
                p.future.set_result(result)

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "window_ms": self.window_ms,
            "max_size": self.max_size,
            "total_batches": self.total_batches,
            "avg_batch_size": round(
                self.total_batched_requests / self.total_batches, 2
            ) if self.total_batches else 0.0,
            "avg_wait_ms": round(
                self.total_wait_ms / self.total_batched_requests, 2
            ) if self.total_batched_requests else 0.0,
            "max_queue_depth": self.max_queue_depth,
            "size_triggered": self.size_triggered,
            "window_triggered": self.window_triggered,
        }
