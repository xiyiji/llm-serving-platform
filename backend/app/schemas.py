"""API contract models — kept stable across all three phases."""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


def _rid() -> str:
    return str(uuid.uuid4())


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class CompletionRequest(BaseModel):
    request_id: str = Field(default_factory=_rid)
    model: str | None = None
    prompt: str | None = None
    messages: list[ChatMessage] | None = None
    max_tokens: int = 256
    temperature: float = 0.7
    stream: bool = False


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CompletionResponse(BaseModel):
    request_id: str
    model: str
    text: str
    usage: Usage
    latency_ms: float
    finish_reason: str = "stop"
    backend: str | None = None
    cached: bool = False


class HealthStatus(BaseModel):
    status: str
    uptime_s: float
    version: str
    details: dict


# ---- Phase 2 platform contracts ----

class ModelInfo(BaseModel):
    id: str
    status: str
    backend: str
    request_count: int = 0
    avg_latency_ms: float = 0.0


class WarmPoolStatus(BaseModel):
    pool_size: int
    pool_capacity: int
    models: list[dict]
    strategy: str
    eviction_policy: str


class RoutingStats(BaseModel):
    strategy: str
    total_endpoints: int
    healthy_endpoints: int
    endpoints: list[dict]


class BatchStats(BaseModel):
    enabled: bool
    total_batches: int
    avg_batch_size: float
    avg_wait_ms: float
    max_queue_depth: int


class KVCacheStats(BaseModel):
    enabled: bool
    size: int
    hit_rate: float
    cache_hits: int
    cache_misses: int
    evictions: int


class BackendStats(BaseModel):
    default_backend: str
    backends: list[dict]
    model_mapping: dict[str, str]


# ---- Phase 3 delivery contracts ----

class DeployRequest(BaseModel):
    model: str
    version: str
    strategy: Literal["canary", "blue_green", "rolling"] = "canary"
    traffic_pct: int = 10


class DeploymentInfo(BaseModel):
    deployment_id: str
    model: str
    version: str
    strategy: str
    phase: str
    traffic_pct: int
    error_rate: float = 0.0
    started_at: float
    finished_at: float | None = None
    rollback_reason: str | None = None


class AlertInfo(BaseModel):
    rule_name: str
    severity: Literal["info", "warning", "critical"]
    message: str
    timestamp: float
    status: Literal["firing", "resolved"]


class RegisterModelRequest(BaseModel):
    model_id: str
    version: str
    stage: Literal["dev", "staging", "production"] = "dev"
    artifact_path: str | None = None
    source: str | None = None


class RegistryInfo(BaseModel):
    model_id: str
    version: str
    stage: str
    artifact_path: str | None = None
    source: str | None = None
    registered_at: float
    deployment_history: list[dict] = Field(default_factory=list)


class BenchmarkReport(BaseModel):
    num_requests: int
    concurrency: int
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_rps: float
    error_rate: float
