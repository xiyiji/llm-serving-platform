"""Model registry: versions, stages, and deployment history.

Models stop being anonymous runtime objects and become governed assets:
every version is registered with a stage (dev / staging / production), and
every deployment that touches it is appended to its history.
"""
from __future__ import annotations

import time

from ..errors import GatewayError
from ..schemas import RegisterModelRequest, RegistryInfo

_STAGES = ["dev", "staging", "production"]


class ModelRegistry:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], RegistryInfo] = {}

    def register(self, req: RegisterModelRequest) -> RegistryInfo:
        key = (req.model_id, req.version)
        if key in self._entries:
            raise GatewayError(
                f"{req.model_id}:{req.version} already registered",
                code="ALREADY_REGISTERED", status_code=409,
            )
        info = RegistryInfo(
            model_id=req.model_id,
            version=req.version,
            stage=req.stage,
            artifact_path=req.artifact_path,
            source=req.source,
            registered_at=time.time(),
        )
        self._entries[key] = info
        return info

    def _get(self, model_id: str, version: str) -> RegistryInfo:
        info = self._entries.get((model_id, version))
        if not info:
            raise GatewayError(
                f"{model_id}:{version} not in registry",
                code="NOT_REGISTERED", status_code=404,
            )
        return info

    def promote(self, model_id: str, version: str, stage: str) -> RegistryInfo:
        if stage not in _STAGES:
            raise GatewayError(f"Unknown stage '{stage}'", code="INVALID_STAGE", status_code=422)
        info = self._get(model_id, version)
        info.stage = stage
        return info

    def record_deployment(self, model_id: str, version: str, event: dict) -> None:
        key = (model_id, version)
        if key in self._entries:
            self._entries[key].deployment_history.append({**event, "at": time.time()})

    def list(self) -> list[RegistryInfo]:
        return sorted(self._entries.values(), key=lambda e: e.registered_at, reverse=True)
