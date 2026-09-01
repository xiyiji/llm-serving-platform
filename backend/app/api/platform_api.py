"""Phase 2 + 3 endpoints: platform state, ops, and governance."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from ..core.metrics import prometheus_payload
from ..core.platform import Platform
from ..schemas import (
    BackendStats,
    BatchStats,
    DeploymentInfo,
    DeployRequest,
    KVCacheStats,
    RegisterModelRequest,
    RegistryInfo,
    RoutingStats,
    WarmPoolStatus,
)

router = APIRouter()


def _p(request: Request) -> Platform:
    return request.app.state.platform


# ---- Phase 2: platform state ----

@router.get("/v1/models")
async def list_models(request: Request) -> dict:
    return {"models": _p(request).models()}


@router.post("/v1/models/{model_id}/load")
async def load_model(model_id: str, request: Request) -> dict:
    p = _p(request)
    adapter = p.router.route(model_id)
    entry = await p.warm_pool.prefetch(model_id, adapter.name)
    return {"id": model_id, "status": entry.status, "load_time_s": entry.load_time_s}


@router.post("/v1/models/{model_id}/unload")
async def unload_model(model_id: str, request: Request) -> dict:
    removed = _p(request).warm_pool.unload(model_id)
    return {"id": model_id, "unloaded": removed}


@router.get("/v1/cold-start/pool", response_model=WarmPoolStatus)
async def warm_pool(request: Request) -> WarmPoolStatus:
    return WarmPoolStatus(**_p(request).warm_pool.status())


@router.get("/v1/routing/stats", response_model=RoutingStats)
async def routing_stats(request: Request) -> RoutingStats:
    return RoutingStats(**await _p(request).router.stats())


@router.get("/v1/batch/stats", response_model=BatchStats)
async def batch_stats(request: Request) -> BatchStats:
    return BatchStats(**_p(request).batcher.stats())


@router.get("/v1/kv-cache/stats", response_model=KVCacheStats)
async def kv_cache_stats(request: Request) -> KVCacheStats:
    return KVCacheStats(**_p(request).kv_cache.stats())


@router.get("/v1/backends", response_model=BackendStats)
async def backends(request: Request) -> BackendStats:
    p = _p(request)
    stats = await p.router.stats()
    return BackendStats(
        default_backend=p.settings.default_backend,
        backends=stats["endpoints"],
        model_mapping=p.router.model_backend_mapping(),
    )


@router.get("/v1/stats")
async def request_stats(request: Request) -> dict:
    return _p(request).window.snapshot()


@router.get("/metrics")
async def metrics() -> Response:
    payload, content_type = prometheus_payload()
    return Response(content=payload, media_type=content_type)


# ---- Phase 3: deployments ----

@router.get("/v1/deployments")
async def deployments(request: Request) -> dict:
    p = _p(request)
    return {
        "stable_versions": p.deployments.stable_versions,
        "deployments": [d.model_dump() for d in p.deployments.history()],
    }


@router.post("/v1/deployments", response_model=DeploymentInfo)
async def start_deployment(req: DeployRequest, request: Request) -> DeploymentInfo:
    p = _p(request)
    info = p.deployments.start(req)
    p.registry.record_deployment(
        req.model, req.version,
        {"event": "deployment_started", "deployment_id": info.deployment_id,
         "strategy": info.strategy},
    )
    return info


@router.post("/v1/deployments/{deployment_id}/advance", response_model=DeploymentInfo)
async def advance_deployment(deployment_id: str, request: Request) -> DeploymentInfo:
    p = _p(request)
    info = p.deployments.advance(deployment_id, observed_error_rate=p.window.error_rate)
    p.registry.record_deployment(
        info.model, info.version,
        {"event": "phase_change", "deployment_id": deployment_id, "phase": info.phase},
    )
    return info


@router.post("/v1/deployments/{deployment_id}/rollback", response_model=DeploymentInfo)
async def rollback_deployment(deployment_id: str, request: Request) -> DeploymentInfo:
    p = _p(request)
    info = p.deployments.rollback(deployment_id)
    p.registry.record_deployment(
        info.model, info.version,
        {"event": "rollback", "deployment_id": deployment_id,
         "reason": info.rollback_reason},
    )
    return info


# ---- Phase 3: alerts ----

@router.get("/v1/alerts")
async def alerts(request: Request) -> dict:
    p = _p(request)
    p._evaluate_alerts()
    return p.alerts.state()


# ---- Phase 3: model registry ----

@router.get("/v1/registry")
async def registry(request: Request) -> dict:
    return {"models": [m.model_dump() for m in _p(request).registry.list()]}


@router.post("/v1/registry", response_model=RegistryInfo)
async def register_model(req: RegisterModelRequest, request: Request) -> RegistryInfo:
    return _p(request).registry.register(req)


@router.post("/v1/registry/{model_id}/{version}/promote", response_model=RegistryInfo)
async def promote_model(model_id: str, version: str, stage: str, request: Request) -> RegistryInfo:
    return _p(request).registry.promote(model_id, version, stage)
