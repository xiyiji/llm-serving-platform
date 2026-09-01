"""Application factory and entry point."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api import generate, platform_api
from .config import APP_VERSION, get_settings
from .core.platform import Platform
from .errors import install_error_handlers

log = logging.getLogger("gateway")


def create_app(settings=None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.platform = Platform(settings)
        log.info(
            "gateway up: %d backend(s), routing=%s, batching=%s, kv_cache=%s",
            len(settings.backends), settings.routing_strategy,
            settings.batch_enabled, settings.kv_cache_enabled,
        )
        yield
        log.info("gateway shutting down")

    app = FastAPI(
        title="LLM Serving Platform",
        version=APP_VERSION,
        description="Gateway, routing, batching, caching and ops for LLM inference.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    from fastapi.responses import JSONResponse

    from .core.ratelimit import RateLimiter

    limiter = RateLimiter(
        settings.rate_limit_rps, settings.rate_limit_burst, settings.rate_limit_enabled
    )
    app.state.limiter = limiter

    @app.middleware("http")
    async def auth_and_rate_limit(request: Request, call_next):
        path = request.url.path
        if path.startswith("/v1/"):
            caller = request.client.host if request.client else "anonymous"
            if settings.api_keys:
                auth = request.headers.get("authorization", "")
                key = auth.removeprefix("Bearer ").strip()
                if key not in settings.api_keys:
                    return JSONResponse(
                        status_code=401,
                        content={"error": {"code": "UNAUTHORIZED",
                                           "message": "Missing or invalid API key."}},
                    )
                caller = key
            ok, retry_after = limiter.check(caller)
            if not ok:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": f"{retry_after:.2f}"},
                    content={"error": {"code": "RATE_LIMITED",
                                       "message": "Too many requests; slow down."}},
                )
        return await call_next(request)

    @app.middleware("http")
    async def trace_requests(request: Request, call_next):
        trace_id = request.headers.get("x-request-id") or str(uuid.uuid4())[:8]
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["x-request-id"] = trace_id
        if request.url.path != "/metrics":
            log.info(
                "trace=%s %s %s -> %d %.1fms",
                trace_id, request.method, request.url.path,
                response.status_code, elapsed_ms,
            )
        return response

    app.include_router(generate.router)
    app.include_router(platform_api.router)
    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    run()
