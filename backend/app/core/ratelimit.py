"""API-key authentication and token-bucket rate limiting.

- If ``api_keys`` is configured, every ``/v1/*`` request must carry
  ``Authorization: Bearer <key>``; anything else gets 401.
- Each caller (API key, else client IP) gets a token bucket refilled at
  ``rate_limit_rps`` with capacity ``rate_limit_burst``. An empty bucket
  returns 429 with ``Retry-After`` — backpressure instead of an unbounded
  queue.
"""
from __future__ import annotations

import time


class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.capacity = burst
        self.tokens = float(burst)
        self.updated = time.monotonic()

    def allow(self) -> tuple[bool, float]:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True, 0.0
        return False, (1 - self.tokens) / self.rate


class RateLimiter:
    def __init__(self, rate: float, burst: int, enabled: bool = True):
        self.rate = rate
        self.burst = burst
        self.enabled = enabled
        self._buckets: dict[str, TokenBucket] = {}
        self.rejected = 0

    def check(self, caller: str) -> tuple[bool, float]:
        if not self.enabled:
            return True, 0.0
        bucket = self._buckets.setdefault(caller, TokenBucket(self.rate, self.burst))
        ok, retry_after = bucket.allow()
        if not ok:
            self.rejected += 1
        return ok, retry_after

    def stats(self) -> dict:
        return {
            "enabled": self.enabled,
            "rate_rps": self.rate,
            "burst": self.burst,
            "callers": len(self._buckets),
            "rejected": self.rejected,
        }
