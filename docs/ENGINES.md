# Wiring real engines

The gateway treats every engine as an OpenAI-compatible HTTP backend. The
adapter layer normalises requests, streams, errors and usage accounting, so
the rest of the platform (routing, batching, caching, releases, metrics)
does not care what is behind it.

## Quick version

```bash
LSP_UPSTREAM_BASE_URL=http://<engine-host>:<port>/v1 \
LSP_UPSTREAM_MODELS=<model-id> \
uvicorn app.main:app --port 8000
```

## vLLM

```bash
python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --port 8001
```

```yaml
# backend/config.yaml
backends:
  - name: vllm
    kind: openai_compat
    base_url: http://localhost:8001/v1
    models: [meta-llama/Llama-3.1-8B-Instruct]
default_backend: vllm
```

## InferenceGateway (Ray Serve + vLLM)

[InferenceGateway](https://github.com/xiyiji/InferenceGateway) is the engine
layer this platform pairs with: Ray Serve ingress, vLLM `AsyncLLMEngine` with
prefix caching, queue backpressure, DCGM GPU metrics, and a benchmark harness
of its own. It exposes the same OpenAI-compatible surface on its ingress
port, so the pairing is one backend entry:

```yaml
backends:
  - name: inference-gateway
    kind: openai_compat
    base_url: http://<gpu-box>:8000/v1
    models: [llama-3.1-8b-instruct]
default_backend: inference-gateway
```

Division of labour in that setup:

| Concern | Lives in |
|---|---|
| Engine-level continuous batching, PagedAttention, KV blocks | InferenceGateway (vLLM) |
| GPU utilisation, TTFT/TPOT measurement | InferenceGateway |
| Cross-engine routing, gateway prefix cache, request micro-batching | this platform |
| Releases, rollback, registry, alerts, ops console | this platform |

Both layers keep their own Prometheus metrics; point one Prometheus at both
`/metrics` endpoints and the committed Grafana dashboard shows the gateway
side.

## Ollama

```yaml
backends:
  - name: ollama
    kind: openai_compat
    base_url: http://localhost:11434/v1
    models: [llama3.1]
```

## Several backends at once

List multiple backends and give each its `models` list. The router maps a
requested model to the backends that serve it, then picks by strategy
(`round_robin`, `latency`, or `adaptive` — latency-aware with error-rate
demotion). Backends with an empty `models` list accept anything, which is a
convenient catch-all during development.
