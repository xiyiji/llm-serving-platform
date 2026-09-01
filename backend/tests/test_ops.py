"""Tests for phase 3 modules: deployments, alerts, registry."""
from app.core.alerts import AlertManager
from app.core.deployment import DeploymentManager
from app.core.registry import ModelRegistry
from app.schemas import DeployRequest, RegisterModelRequest


def test_canary_deployment_full_promotion():
    mgr = DeploymentManager()
    d = mgr.start(DeployRequest(model="m1", version="1.1.0", strategy="canary"))
    assert d.phase == "canary_10"
    d = mgr.advance(d.deployment_id)
    assert d.phase == "canary_50" and d.traffic_pct == 50
    d = mgr.advance(d.deployment_id)
    assert d.phase == "live" and d.traffic_pct == 100
    assert mgr.stable_versions["m1"] == "1.1.0"


def test_auto_rollback_on_high_error_rate():
    mgr = DeploymentManager(auto_rollback_threshold=0.10)
    d = mgr.start(DeployRequest(model="m1", version="1.2.0", strategy="canary"))
    d = mgr.advance(d.deployment_id, observed_error_rate=0.25)
    assert d.phase == "rolled_back"
    assert "error rate" in (d.rollback_reason or "")
    assert "m1" not in mgr.stable_versions


def test_manual_rollback_and_blue_green():
    mgr = DeploymentManager()
    d = mgr.start(DeployRequest(model="m2", version="2.0.0", strategy="blue_green"))
    assert d.phase == "standby"
    d = mgr.rollback(d.deployment_id, reason="operator decision")
    assert d.phase == "rolled_back" and d.traffic_pct == 0


def test_alert_fires_and_resolves():
    alerts = AlertManager()
    firing = alerts.evaluate({"p95_latency_ms": 5000, "error_rate": 0.0,
                              "queue_depth": 0, "avg_cold_start_s": 0})
    assert any(a.rule_name == "high_p95_latency" for a in firing)
    now_ok = alerts.evaluate({"p95_latency_ms": 100, "error_rate": 0.0,
                              "queue_depth": 0, "avg_cold_start_s": 0})
    assert not now_ok
    history = alerts.state()["history"]
    assert history[-1]["status"] == "resolved"


def test_registry_lifecycle_and_history():
    reg = ModelRegistry()
    reg.register(RegisterModelRequest(model_id="m1", version="1.0.0", stage="dev"))
    reg.promote("m1", "1.0.0", "production")
    reg.record_deployment("m1", "1.0.0", {"event": "deployment_started"})
    entry = reg.list()[0]
    assert entry.stage == "production"
    assert entry.deployment_history[0]["event"] == "deployment_started"


def test_registry_rejects_duplicates():
    import pytest
    from app.errors import GatewayError

    reg = ModelRegistry()
    reg.register(RegisterModelRequest(model_id="m1", version="1.0.0"))
    with pytest.raises(GatewayError):
        reg.register(RegisterModelRequest(model_id="m1", version="1.0.0"))


def test_platform_endpoints(client):
    # generate some traffic first
    client.post("/v1/completions", json={"prompt": "traffic"})

    models = client.get("/v1/models").json()["models"]
    assert any(m["id"] == "llama-3.1-8b-instruct" for m in models)

    pool = client.get("/v1/cold-start/pool").json()
    assert pool["pool_capacity"] > 0

    routing = client.get("/v1/routing/stats").json()
    assert routing["healthy_endpoints"] >= 1

    batch = client.get("/v1/batch/stats").json()
    assert batch["enabled"] is True

    backends = client.get("/v1/backends").json()
    assert backends["default_backend"] == "primary"

    metrics = client.get("/metrics")
    assert b"gateway_requests_total" in metrics.content

    # deployment flow over HTTP
    dep = client.post(
        "/v1/deployments",
        json={"model": "llama-3.1-8b-instruct", "version": "1.1.0", "strategy": "canary"},
    ).json()
    advanced = client.post(f"/v1/deployments/{dep['deployment_id']}/advance").json()
    assert advanced["phase"] in ("canary_50", "rolled_back")

    # registry over HTTP
    client.post("/v1/registry", json={"model_id": "llama-3.1-8b-instruct", "version": "1.1.0"})
    reg = client.get("/v1/registry").json()["models"]
    assert reg and reg[0]["model_id"] == "llama-3.1-8b-instruct"

    alerts = client.get("/v1/alerts").json()
    assert "active" in alerts and "rules" in alerts
