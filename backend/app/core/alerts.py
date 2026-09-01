"""Alerting: threshold rules evaluated over live platform state.

Rules cover the four failure classes the runbook cares about — latency,
error rate, resource pressure (queue depth as proxy), and cold starts.
Each evaluation transitions rules between ``firing`` and ``resolved``;
the full transition history is kept for the console.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from ..schemas import AlertInfo


@dataclass
class AlertRule:
    name: str
    severity: str  # info | warning | critical
    message: Callable[[dict], str]
    predicate: Callable[[dict], bool]


class AlertManager:
    def __init__(self) -> None:
        self.rules = [
            AlertRule(
                "high_p95_latency", "warning",
                lambda s: f"p95 latency {s['p95_latency_ms']:.0f} ms above 2000 ms target",
                lambda s: s.get("p95_latency_ms", 0) > 2000,
            ),
            AlertRule(
                "high_error_rate", "critical",
                lambda s: f"error rate {s['error_rate']:.1%} above 5% threshold",
                lambda s: s.get("error_rate", 0) > 0.05,
            ),
            AlertRule(
                "queue_pressure", "warning",
                lambda s: f"batch queue depth {s['queue_depth']} above 32",
                lambda s: s.get("queue_depth", 0) > 32,
            ),
            AlertRule(
                "cold_start_degradation", "info",
                lambda s: f"avg cold start {s['avg_cold_start_s']:.1f}s above 2s baseline",
                lambda s: s.get("avg_cold_start_s", 0) > 2.0,
            ),
        ]
        self.active: dict[str, AlertInfo] = {}
        self.history: list[AlertInfo] = []

    def evaluate(self, snapshot: dict) -> list[AlertInfo]:
        now = time.time()
        for rule in self.rules:
            firing = False
            try:
                firing = rule.predicate(snapshot)
            except (KeyError, TypeError):
                pass
            currently = rule.name in self.active
            if firing and not currently:
                alert = AlertInfo(
                    rule_name=rule.name, severity=rule.severity,
                    message=rule.message(snapshot), timestamp=now, status="firing",
                )
                self.active[rule.name] = alert
                self.history.append(alert)
            elif not firing and currently:
                resolved = self.active.pop(rule.name).model_copy(
                    update={"status": "resolved", "timestamp": now}
                )
                self.history.append(resolved)
        return list(self.active.values())

    def state(self) -> dict:
        return {
            "active": [a.model_dump() for a in self.active.values()],
            "history": [a.model_dump() for a in self.history[-50:]],
            "rules": [
                {"rule_name": r.name, "severity": r.severity} for r in self.rules
            ],
        }
