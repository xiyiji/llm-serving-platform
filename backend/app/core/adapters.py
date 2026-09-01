"""Backend adapter layer.

Every inference engine the platform talks to sits behind one interface:
``generate()`` for a full response and ``stream()`` for token deltas.
The API layer never sees engine-specific request or error shapes.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from ..config import BackendConfig
from ..errors import (
    RequestTimeoutError,
    UpstreamAuthError,
    UpstreamUnavailableError,
)
from ..schemas import ChatMessage, CompletionRequest, CompletionResponse, Usage


class BackendAdapter(ABC):
    """Uniform interface over one inference backend."""

    def __init__(self, config: BackendConfig):
        self.config = config
        self.name = config.name
        self.request_count = 0
        self.error_count = 0
        self.total_latency_ms = 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.request_count if self.request_count else 0.0

    def record(self, latency_ms: float, *, error: bool = False) -> None:
        self.request_count += 1
        self.total_latency_ms += latency_ms
        if error:
            self.error_count += 1

    async def health(self) -> bool:
        return True

    @abstractmethod
    async def generate(self, request: CompletionRequest, model: str) -> CompletionResponse: ...

    @abstractmethod
    def stream(self, request: CompletionRequest, model: str) -> AsyncIterator[str]:
        """Yield text deltas."""
        ...


def _messages_to_prompt(messages: list[ChatMessage]) -> str:
    return "\n".join(f"{m.role}: {m.content}" for m in messages)


def _prompt_of(request: CompletionRequest) -> str:
    if request.messages:
        return _messages_to_prompt(request.messages)
    return request.prompt or ""


class SimulatedAdapter(BackendAdapter):
    """Deterministic local engine used for development and demos.

    Produces a short, plausible reply derived from the prompt so the full
    request path — routing, batching, caching, streaming — can be exercised
    with no external model server and no API key.
    """

    _CANNED = [
        "In an LLM serving platform the router picks a backend per request, "
        "weighing latency, cost and health.",
        "Dynamic batching groups requests that arrive within a small time "
        "window into one forward pass, trading a few milliseconds of wait "
        "for much higher GPU utilisation.",
        "The KV cache stores attention key/value tensors for prefixes that "
        "repeat across requests, so shared system prompts are prefilled once.",
        "Cold starts are hidden by a warm pool: models predicted to be needed "
        "soon are loaded ahead of the first request that wants them.",
    ]

    async def generate(self, request: CompletionRequest, model: str) -> CompletionResponse:
        start = time.perf_counter()
        prompt = _prompt_of(request)
        text = self._reply(prompt, request.max_tokens)
        # Simulate decode time proportional to output length.
        await asyncio.sleep(min(0.2, 0.002 * len(text.split())))
        latency_ms = (time.perf_counter() - start) * 1000
        p_tok, c_tok = len(prompt.split()), len(text.split())
        return CompletionResponse(
            request_id=request.request_id,
            model=model,
            text=text,
            usage=Usage(prompt_tokens=p_tok, completion_tokens=c_tok, total_tokens=p_tok + c_tok),
            latency_ms=round(latency_ms, 2),
            finish_reason="stop",
            backend=self.name,
        )

    async def stream(self, request: CompletionRequest, model: str) -> AsyncIterator[str]:
        text = self._reply(_prompt_of(request), request.max_tokens)
        for word in text.split(" "):
            await asyncio.sleep(0.015)
            yield word + " "

    def _reply(self, prompt: str, max_tokens: int) -> str:
        idx = int(hashlib.sha256(prompt.encode()).hexdigest(), 16) % len(self._CANNED)
        words = self._CANNED[idx].split()
        return " ".join(words[: max(8, min(max_tokens, len(words)))])


class OpenAICompatAdapter(BackendAdapter):
    """Adapter for any OpenAI-compatible HTTP endpoint (vLLM, TGI, Ollama,
    llama.cpp server, hosted APIs...)."""

    def _client(self) -> httpx.AsyncClient:
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return httpx.AsyncClient(
            base_url=self.config.base_url or "",
            headers=headers,
            timeout=self.config.timeout_s,
        )

    async def health(self) -> bool:
        try:
            async with self._client() as client:
                resp = await client.get("/models")
                return resp.status_code < 500
        except httpx.HTTPError:
            return False

    def _body(self, request: CompletionRequest, model: str, stream: bool) -> dict:
        messages = request.messages or [ChatMessage(role="user", content=request.prompt or "")]
        return {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": stream,
        }

    async def generate(self, request: CompletionRequest, model: str) -> CompletionResponse:
        start = time.perf_counter()
        try:
            async with self._client() as client:
                resp = await client.post("/chat/completions", json=self._body(request, model, False))
        except httpx.TimeoutException as exc:
            raise RequestTimeoutError(f"Upstream '{self.name}' timed out") from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(f"Upstream '{self.name}' unreachable: {exc}") from exc
        if resp.status_code in (401, 403):
            raise UpstreamAuthError(f"Upstream '{self.name}' rejected credentials")
        if resp.status_code >= 400:
            raise UpstreamUnavailableError(
                f"Upstream '{self.name}' returned {resp.status_code}: {resp.text[:200]}"
            )
        data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage") or {}
        return CompletionResponse(
            request_id=request.request_id,
            model=model,
            text=choice["message"]["content"],
            usage=Usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ),
            latency_ms=round((time.perf_counter() - start) * 1000, 2),
            finish_reason=choice.get("finish_reason") or "stop",
            backend=self.name,
        )

    async def stream(self, request: CompletionRequest, model: str) -> AsyncIterator[str]:
        import json

        try:
            async with self._client() as client:
                async with client.stream(
                    "POST", "/chat/completions", json=self._body(request, model, True)
                ) as resp:
                    if resp.status_code in (401, 403):
                        raise UpstreamAuthError(f"Upstream '{self.name}' rejected credentials")
                    if resp.status_code >= 400:
                        raise UpstreamUnavailableError(
                            f"Upstream '{self.name}' returned {resp.status_code}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        delta = (
                            json.loads(payload)["choices"][0].get("delta", {}).get("content")
                        )
                        if delta:
                            yield delta
        except httpx.TimeoutException as exc:
            raise RequestTimeoutError(f"Upstream '{self.name}' timed out") from exc
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(f"Upstream '{self.name}' unreachable: {exc}") from exc


def build_adapter(config: BackendConfig) -> BackendAdapter:
    if config.kind == "openai_compat":
        return OpenAICompatAdapter(config)
    return SimulatedAdapter(config)
