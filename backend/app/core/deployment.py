"""Release management: canary / blue-green / rolling deployments with rollback.

The manager owns the release state machine and history. Phases:

- canary:      ``canary_10 -> canary_50 -> live``
- blue_green:  ``standby -> live`` (atomic switch)
- rolling:     ``rolling_33 -> rolling_66 -> live``

``advance()`` moves a deployment to its next phase; ``rollback()`` returns
traffic to the previous stable version and records why. If a deployment's
observed error rate crosses ``auto_rollback_threshold`` on advance, the
rollback happens automatically.
"""
from __future__ import annotations

import time
import uuid

from ..errors import GatewayError
from ..schemas import DeploymentInfo, DeployRequest

_PHASES = {
    "canary": ["canary_10", "canary_50", "live"],
    "blue_green": ["standby", "live"],
    "rolling": ["rolling_33", "rolling_66", "live"],
}
_TRAFFIC = {
    "canary_10": 10, "canary_50": 50,
    "standby": 0,
    "rolling_33": 33, "rolling_66": 66,
    "live": 100, "rolled_back": 0,
}


class DeploymentManager:
    def __init__(self, auto_rollback_threshold: float = 0.10):
        self.auto_rollback_threshold = auto_rollback_threshold
        self.deployments: dict[str, DeploymentInfo] = {}
        self.stable_versions: dict[str, str] = {}  # model -> live version

    def start(self, req: DeployRequest) -> DeploymentInfo:
        phases = _PHASES[req.strategy]
        info = DeploymentInfo(
            deployment_id=str(uuid.uuid4())[:8],
            model=req.model,
            version=req.version,
            strategy=req.strategy,
            phase=phases[0],
            traffic_pct=req.traffic_pct if req.strategy == "canary" else _TRAFFIC[phases[0]],
            started_at=time.time(),
        )
        self.deployments[info.deployment_id] = info
        return info

    def _get(self, deployment_id: str) -> DeploymentInfo:
        info = self.deployments.get(deployment_id)
        if not info:
            raise GatewayError(
                f"Deployment '{deployment_id}' not found",
                code="DEPLOYMENT_NOT_FOUND",
                status_code=404,
            )
        return info

    def advance(self, deployment_id: str, observed_error_rate: float = 0.0) -> DeploymentInfo:
        info = self._get(deployment_id)
        if info.phase in ("live", "rolled_back"):
            return info
        info.error_rate = observed_error_rate
        if observed_error_rate > self.auto_rollback_threshold:
            return self.rollback(
                deployment_id,
                reason=f"error rate {observed_error_rate:.1%} above "
                       f"{self.auto_rollback_threshold:.0%} threshold",
            )
        phases = _PHASES[info.strategy]
        idx = phases.index(info.phase)
        info.phase = phases[min(idx + 1, len(phases) - 1)]
        info.traffic_pct = _TRAFFIC[info.phase]
        if info.phase == "live":
            info.finished_at = time.time()
            self.stable_versions[info.model] = info.version
        return info

    def rollback(self, deployment_id: str, reason: str = "manual rollback") -> DeploymentInfo:
        info = self._get(deployment_id)
        info.phase = "rolled_back"
        info.traffic_pct = 0
        info.rollback_reason = reason
        info.finished_at = time.time()
        return info

    def history(self) -> list[DeploymentInfo]:
        return sorted(self.deployments.values(), key=lambda d: d.started_at, reverse=True)
