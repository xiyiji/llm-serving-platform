"""Configuration loading for the gateway.

Settings come from (in order of precedence):
1. Environment variables prefixed with ``LSP_``
2. A YAML config file (``LSP_CONFIG_FILE``, default ``config.yaml``)
3. Built-in defaults
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

APP_VERSION = "3.0.0"


class BackendConfig(BaseModel):
    """One inference backend the gateway can route to."""

    name: str
    kind: str = "simulated"  # "openai_compat" | "simulated"
    base_url: str | None = None
    api_key: str | None = None
    timeout_s: float = 60.0
    models: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    default_model: str = "llama-3.1-8b-instruct"
    default_backend: str = "primary"
    request_timeout_s: float = 60.0
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    log_level: str = "INFO"

    # Warm pool
    warm_pool_capacity: int = 4
    warm_pool_eviction: str = "lru"  # lru | lfu | ttl
    warm_pool_ttl_s: float = 600.0
    cold_start_load_s: float = 1.2  # simulated load time per model

    # Batching
    batch_enabled: bool = True
    batch_window_ms: float = 8.0
    batch_max_size: int = 8

    # KV cache
    kv_cache_enabled: bool = True
    kv_cache_capacity: int = 512

    # Routing
    routing_strategy: str = "adaptive"  # round_robin | latency | adaptive

    # Auth + rate limiting
    api_keys: list[str] = Field(default_factory=list)  # empty = auth disabled
    rate_limit_enabled: bool = True
    rate_limit_rps: float = 20.0
    rate_limit_burst: int = 40

    backends: list[BackendConfig] = Field(
        default_factory=lambda: [
            BackendConfig(
                name="primary",
                kind="simulated",
                models=["llama-3.1-8b-instruct", "mistral-7b-instruct"],
            )
        ]
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    return {}


def _env_overrides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    simple = {
        "LSP_HOST": "host",
        "LSP_PORT": "port",
        "LSP_DEFAULT_MODEL": "default_model",
        "LSP_DEFAULT_BACKEND": "default_backend",
        "LSP_LOG_LEVEL": "log_level",
        "LSP_ROUTING_STRATEGY": "routing_strategy",
    }
    for env, key in simple.items():
        if os.environ.get(env):
            out[key] = os.environ[env]
    if os.environ.get("LSP_API_KEYS"):
        out["api_keys"] = [k.strip() for k in os.environ["LSP_API_KEYS"].split(",") if k.strip()]
    if os.environ.get("LSP_RATE_LIMIT_ENABLED"):
        out["rate_limit_enabled"] = os.environ["LSP_RATE_LIMIT_ENABLED"].lower() in ("1", "true", "yes")
    if os.environ.get("LSP_RATE_LIMIT_RPS"):
        out["rate_limit_rps"] = float(os.environ["LSP_RATE_LIMIT_RPS"])
    if os.environ.get("LSP_RATE_LIMIT_BURST"):
        out["rate_limit_burst"] = int(os.environ["LSP_RATE_LIMIT_BURST"])
    # A single OpenAI-compatible upstream can be injected purely via env,
    # which is the quickest way to point the gateway at a real model server.
    if os.environ.get("LSP_UPSTREAM_BASE_URL"):
        out["backends"] = [
            {
                "name": "primary",
                "kind": "openai_compat",
                "base_url": os.environ["LSP_UPSTREAM_BASE_URL"],
                "api_key": os.environ.get("LSP_UPSTREAM_API_KEY"),
                "models": [
                    m.strip()
                    for m in os.environ.get("LSP_UPSTREAM_MODELS", "").split(",")
                    if m.strip()
                ],
            }
        ]
    return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    config_file = Path(os.environ.get("LSP_CONFIG_FILE", "config.yaml"))
    data = _load_yaml(config_file)
    data.update(_env_overrides())
    return Settings(**data)
