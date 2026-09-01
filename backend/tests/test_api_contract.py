"""Contract tests for the phase 1 API surface."""
import json


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert {"status", "uptime_s", "version", "details"} <= body.keys()


def test_completions_non_stream(client):
    r = client.post(
        "/v1/completions",
        json={"prompt": "Hello", "model": "llama-3.1-8b-instruct", "max_tokens": 32},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["text"]
    assert body["model"] == "llama-3.1-8b-instruct"
    assert body["usage"]["total_tokens"] == (
        body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"]
    )
    assert body["finish_reason"] == "stop"
    assert body["latency_ms"] >= 0


def test_chat_completions_roles(client):
    r = client.post(
        "/v1/chat/completions",
        json={
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Explain KV cache."},
            ],
        },
    )
    assert r.status_code == 200
    assert r.json()["text"]


def test_chat_stream_sse(client):
    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "stream please"}], "stream": True},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [line[5:].strip() for line in r.iter_lines() if line.startswith("data:")]
    assert events[-1] == "[DONE]"
    deltas = [json.loads(e) for e in events[:-1]]
    assert any(d["delta"] for d in deltas)
    assert deltas[-1]["finish_reason"] == "stop"


def test_validation_error_shape(client):
    r = client.post("/v1/chat/completions", json={"messages": [{"role": "bogus", "content": "x"}]})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_FAILED"


def test_repeat_request_hits_cache(client):
    payload = {"prompt": "cache me", "temperature": 0.0}
    first = client.post("/v1/completions", json=payload).json()
    second = client.post("/v1/completions", json=payload).json()
    assert not first["cached"]
    assert second["cached"]
    assert second["text"] == first["text"]
    stats = client.get("/v1/kv-cache/stats").json()
    assert stats["cache_hits"] >= 1
