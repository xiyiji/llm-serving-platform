"""Request routing across backends.

Strategies:
- ``round_robin`` — rotate over healthy backends serving the model
- ``latency``     — pick the healthy backend with the lowest average latency
- ``adaptive``    — latency-based, but any backend whose recent error rate
                    exceeds 20% is deprioritised
"""
from __future__ import annotations

import itertools

from ..errors import ModelNotFoundError
from .adapters import BackendAdapter


class Router:
    def __init__(self, adapters: list[BackendAdapter], strategy: str = "adaptive", default_backend: str = "primary"):
        self.adapters = {a.name: a for a in adapters}
        self.strategy = strategy
        self.default_backend = default_backend
        self._rr = itertools.count()
        self.decisions: dict[str, int] = {a.name: 0 for a in adapters}

    def candidates_for(self, model: str) -> list[BackendAdapter]:
        serving = [
            a for a in self.adapters.values()
            if not a.config.models or model in a.config.models
        ]
        return serving or list(self.adapters.values())

    def model_backend_mapping(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for a in self.adapters.values():
            for m in a.config.models:
                mapping.setdefault(m, a.name)
        return mapping

    def route(self, model: str) -> BackendAdapter:
        candidates = self.candidates_for(model)
        if not candidates:
            raise ModelNotFoundError(f"No backend serves model '{model}'")

        if self.strategy == "round_robin":
            chosen = candidates[next(self._rr) % len(candidates)]
        elif self.strategy == "latency":
            chosen = min(candidates, key=lambda a: a.avg_latency_ms)
        else:  # adaptive
            def score(a: BackendAdapter) -> tuple:
                err_rate = a.error_count / a.request_count if a.request_count else 0.0
                return (err_rate > 0.2, a.avg_latency_ms)
            chosen = min(candidates, key=score)

        self.decisions[chosen.name] = self.decisions.get(chosen.name, 0) + 1
        return chosen

    async def stats(self) -> dict:
        endpoints = []
        healthy = 0
        for a in self.adapters.values():
            ok = await a.health()
            healthy += ok
            endpoints.append(
                {
                    "name": a.name,
                    "kind": a.config.kind,
                    "healthy": ok,
                    "request_count": a.request_count,
                    "error_count": a.error_count,
                    "avg_latency_ms": round(a.avg_latency_ms, 2),
                    "routed": self.decisions.get(a.name, 0),
                }
            )
        return {
            "strategy": self.strategy,
            "total_endpoints": len(self.adapters),
            "healthy_endpoints": healthy,
            "endpoints": endpoints,
        }
