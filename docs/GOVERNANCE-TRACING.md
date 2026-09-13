# Governance and tracing

The Admin console supports register, promote, load and unload. Enter the API
base URL and the same API key used for inference. Registry state and the warm
pool remain in memory. Loading/unloading affects gateway bookkeeping, not GPU
weights on a remote engine. Registering a version does not change backend routing.

## Promote contract

After registering a model, use:

```sh
curl -X POST http://localhost:8000/v1/registry/example/1.0/promote \
  -H 'Content-Type: application/json' -d '{"stage":"production"}'
```

Valid stages are `dev`, `staging`, `production`. The legacy `?stage=production`
query remains supported. Missing/invalid stages or conflicting body/query values
return 422; unknown model versions return 404.

## Streaming semantics

Both completion and streaming requests use the gateway scheduler. Streaming
startup (up to the first delta) is grouped within the batch window; each stream
then continues independently with consumer backpressure. This is concurrent HTTP
dispatch, not a GPU forward-pass batch. Continuous token batching remains an
engine responsibility.

The gateway cache stores complete responses or stream deltas, not attention KV
tensors. Streaming and non-streaming entries have separate keys. Only streams
that finish successfully are cached; errors, cancellation and early closure do
not publish partial entries. Streams exceeding 1 MiB of UTF-8 output bypass
storage. Cached deltas replay without artificial token delays. Cache behavior
also applies to sampling requests, so repeated parameters reuse an earlier
sample while cached. Stream cache hits do not estimate saved token counts.

## OpenTelemetry

FastAPI server spans extract W3C `traceparent`; instrumented httpx clients create
child spans and inject that context into upstream inference requests. Scheduler
entries capture each request's context so batching does not mix trace parents.
The gateway cannot create spans inside an uninstrumented remote engine.

To export traces using OTLP HTTP/protobuf, set these variables before starting
the backend:

```sh
export OTEL_SERVICE_NAME=llm-serving-platform
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
# Alternatively set OTEL_EXPORTER_OTLP_TRACES_ENDPOINT including /v1/traces.
# Optional authentication: OTEL_EXPORTER_OTLP_HEADERS=key=value
uvicorn app.main:app
```

An OTLP receiver must be reachable at that address. Without either endpoint
variable, tracing and propagation run without network export. Owned providers
flush/shutdown with the app; tests may inject their own provider and exporter.
Prometheus metrics continue at `/metrics`, independently from trace export.

## EKS outputs

Terraform exposes `cluster_name`, `cluster_endpoint`, public base64
`cluster_certificate_authority_data`, `oidc_provider_arn`, `region` and
`configure_kubectl`, alongside the two ECR URLs.

```sh
cd deploy/terraform
terraform output -raw configure_kubectl
aws eks update-kubeconfig \
  --region "$(terraform output -raw region)" \
  --name "$(terraform output -raw cluster_name)"
kubectl get nodes
```

The command uses AWS CLI authentication, not a stored token. The caller still
needs an EKS access entry and IAM permissions, plus network connectivity to the
cluster endpoint. Outputs do not grant cluster access. No cloud resources are
created merely by reading these outputs.
