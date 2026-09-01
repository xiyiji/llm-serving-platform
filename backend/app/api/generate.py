"""Phase 1 endpoints: health, completions, chat completions (with SSE)."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from ..config import APP_VERSION
from ..errors import GatewayError
from ..schemas import CompletionRequest, CompletionResponse, HealthStatus
from ..core.platform import Platform

router = APIRouter()
log = logging.getLogger("gateway.api")


def _platform(request: Request) -> Platform:
    return request.app.state.platform


@router.get("/health", response_model=HealthStatus)
async def health(request: Request) -> HealthStatus:
    data = _platform(request).health()
    return HealthStatus(version=APP_VERSION, **data)


def _sse(payload: dict | str) -> str:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return f"data: {body}\n\n"


async def _stream_response(platform: Platform, req: CompletionRequest) -> StreamingResponse:
    async def event_gen():
        try:
            async for delta in platform.stream(req):
                yield _sse({"delta": delta, "finish_reason": None})
            yield _sse({"delta": "", "finish_reason": "stop"})
        except GatewayError as exc:
            yield _sse({"error": {"code": exc.code, "message": exc.message}})
        except Exception as exc:  # pragma: no cover - defensive
            yield _sse({"error": {"code": "INTERNAL_ERROR", "message": str(exc)}})
        yield _sse("[DONE]")

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/v1/completions")
async def completions(req: CompletionRequest, request: Request):
    platform = _platform(request)
    if req.stream:
        return await _stream_response(platform, req)
    return await platform.completion(req, endpoint="completions")


@router.post("/v1/chat/completions")
async def chat_completions(req: CompletionRequest, request: Request):
    platform = _platform(request)
    if req.stream:
        return await _stream_response(platform, req)
    return await platform.completion(req, endpoint="chat_completions")
