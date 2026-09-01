# Deploying

Three tiers, cheapest first.

## Local (everything, one command)

```bash
docker compose up --build
# console :3000 · gateway :8000 · prometheus :9090 · grafana :3001
```

## Public demo: Render (gateway) + Vercel (console)

The gateway runs fine on Render's free tier because the default engine is
simulated — no GPU needed for the demo path.

**Gateway → Render**

1. In Render: *New → Blueprint*, pick this repo. `render.yaml` at the repo
   root describes the service (Docker build of `backend/`, health check on
   `/health`). Deploy and note the URL, e.g.
   `https://llm-serving-gateway.onrender.com`.
2. Free instances sleep after 15 idle minutes; the first request after that
   takes ~30–60 s while the instance wakes.

**Console → Vercel**

1. In Vercel: *Add New → Project*, import the repo, set **Root Directory**
   to `frontend`.
2. Add the environment variable `NEXT_PUBLIC_API_BASE` =
   `https://<your-gateway>.onrender.com` (no trailing slash), then deploy.

CORS is open by default, so no further wiring is needed. To require keys on
the public gateway, set `LSP_API_KEYS` on the Render service and paste the
key into the console's API Key field.

## Real inference: rent a GPU, point the gateway at it

Any GPU box that can run vLLM turns the demo into real inference without
touching the deployed gateway — it's three environment variables.

1. Rent a 24 GB GPU (RunPod / Lambda / Vast: RTX 4090 or A10G class) and
   expose an HTTP port.
2. Run vLLM's OpenAI server on it:

   ```bash
   pip install vllm
   python -m vllm.entrypoints.openai.api_server \
     --model meta-llama/Llama-3.1-8B-Instruct \
     --served-model-name llama-3.1-8b-instruct \
     --port 8001 --api-key <pick-a-secret>
   ```

   (Or run [InferenceGateway](https://github.com/xiyiji/InferenceGateway)
   for the full Ray Serve + vLLM engine layer.)
3. On the Render service, set:

   ```
   LSP_UPSTREAM_BASE_URL = https://<gpu-endpoint>:8001/v1
   LSP_UPSTREAM_MODELS   = llama-3.1-8b-instruct
   LSP_UPSTREAM_API_KEY  = <the same secret>
   ```

   Render restarts the gateway; the console's model dropdown picks up the
   real model automatically, and every chat request now runs on the GPU
   through the full gateway path — routing, batching, caching, metrics.

Stop the GPU when not demoing; the gateway falls back to errors you can see
in the console, and clearing the three variables returns it to the
simulated engine.

## Kubernetes / Terraform

`deploy/k8s/` and `deploy/terraform/` carry the manifests and
infrastructure scripts for a managed-cluster deployment (probed 2-replica
gateway, HPA, ECR + EKS). Use them when the platform needs to sit next to
the GPU fleet rather than on a free dyno.
