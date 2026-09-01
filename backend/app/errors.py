"""Unified error types and handlers.

Every error leaving the gateway has the shape::

    {"error": {"code": "UPSTREAM_UNAVAILABLE", "message": "..."}}
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class GatewayError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class UpstreamUnavailableError(GatewayError):
    status_code = 502
    code = "UPSTREAM_UNAVAILABLE"


class UpstreamAuthError(GatewayError):
    status_code = 401
    code = "UPSTREAM_AUTH_FAILED"


class ModelNotFoundError(GatewayError):
    status_code = 404
    code = "MODEL_NOT_FOUND"


class RequestTimeoutError(GatewayError):
    status_code = 504
    code = "UPSTREAM_TIMEOUT"


def _payload(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(GatewayError)
    async def _gateway_error(_: Request, exc: GatewayError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_payload(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload("VALIDATION_FAILED", str(exc.errors()[:3])),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_payload("INTERNAL_ERROR", f"{type(exc).__name__}: {exc}"),
        )
