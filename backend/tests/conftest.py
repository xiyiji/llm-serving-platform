from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import BackendConfig, Settings
from app.main import create_app


def make_settings(**overrides) -> Settings:
    base = dict(
        cold_start_load_s=0.01,
        batch_window_ms=2,
        backends=[
            BackendConfig(
                name="primary",
                kind="simulated",
                models=["llama-3.1-8b-instruct", "mistral-7b-instruct"],
            ),
            BackendConfig(name="secondary", kind="simulated", models=["mistral-7b-instruct"]),
        ],
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def client() -> TestClient:
    app = create_app(make_settings())
    with TestClient(app) as c:
        yield c
