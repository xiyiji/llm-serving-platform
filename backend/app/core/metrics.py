"""Prometheus metrics + a rolling latency window for percentile queries."""
from __future__ import annotations

import time
from collections import deque

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REQUESTS = Counter("gateway_requests_total", "Requests", ["endpoint", "model", "backend"])
ERRORS = Counter("gateway_errors_total", "Errors", ["endpoint", "code"])
LATENCY = Histogram(
    "gateway_request_latency_seconds", "Request latency", ["endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)
ACTIVE = Gauge("gateway_active_requests", "In-flight requests")
TOKENS = Counter("gateway_tokens_total", "Tokens processed", ["kind"])
BATCH_SIZE = Histogram("gateway_batch_size", "Batch size", buckets=(1, 2, 4, 8, 16, 32))
CACHE_HITS = Counter("gateway_cache_events_total", "Cache events", ["result"])
COLD_START = Histogram("gateway_cold_start_seconds", "Model load time")


class LatencyWindow:
    """Rolling window of recent request latencies and outcomes."""

    def __init__(self, size: int = 500):
        self._lat = deque(maxlen=size)
        self._err = deque(maxlen=size)
        self.total_requests = 0
        self.total_errors = 0
        self.started_at = time.time()

    def observe(self, latency_ms: float, error: bool = False) -> None:
        self._lat.append(latency_ms)
        self._err.append(1 if error else 0)
        self.total_requests += 1
        self.total_errors += int(error)

    def percentile(self, p: float) -> float:
        if not self._lat:
            return 0.0
        data = sorted(self._lat)
        idx = min(len(data) - 1, int(p / 100 * len(data)))
        return round(data[idx], 2)

    @property
    def error_rate(self) -> float:
        return round(sum(self._err) / len(self._err), 4) if self._err else 0.0

    def snapshot(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "window_size": len(self._lat),
            "p50_latency_ms": self.percentile(50),
            "p95_latency_ms": self.percentile(95),
            "p99_latency_ms": self.percentile(99),
            "error_rate": self.error_rate,
        }


def prometheus_payload() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
