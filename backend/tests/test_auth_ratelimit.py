"""Auth and rate-limit behaviour."""
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def _client(**overrides) -> TestClient:
    app = create_app(make_settings(**overrides))
    return TestClient(app)


def test_auth_disabled_by_default(client):
    assert client.post("/v1/completions", json={"prompt": "x"}).status_code == 200


def test_auth_rejects_missing_and_wrong_key():
    with _client(api_keys=["sk-test"]) as c:
        assert c.post("/v1/completions", json={"prompt": "x"}).status_code == 401
        r = c.post(
            "/v1/completions", json={"prompt": "x"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_auth_accepts_valid_key():
    with _client(api_keys=["sk-test"]) as c:
        r = c.post(
            "/v1/completions", json={"prompt": "x"},
            headers={"Authorization": "Bearer sk-test"},
        )
        assert r.status_code == 200


def test_rate_limit_returns_429_with_retry_after():
    with _client(rate_limit_rps=1.0, rate_limit_burst=2) as c:
        codes = [c.get("/v1/batch/stats").status_code for _ in range(5)]
        assert 429 in codes
        r = c.get("/v1/batch/stats")
        if r.status_code == 429:
            assert "retry-after" in r.headers
            assert r.json()["error"]["code"] == "RATE_LIMITED"


def test_health_and_metrics_not_rate_limited():
    with _client(rate_limit_rps=0.1, rate_limit_burst=1) as c:
        for _ in range(5):
            assert c.get("/health").status_code == 200
            assert c.get("/metrics").status_code == 200
