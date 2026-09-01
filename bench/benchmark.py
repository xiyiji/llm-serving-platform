"""Load generator for the gateway.

Usage:
    python bench/benchmark.py --base-url http://localhost:8000 \
        --requests 200 --concurrency 16 [--unique-prompts] [--json out.json]

Reports p50/p95/p99 latency, throughput and error rate. Run it twice —
once with repeated prompts (cache-friendly) and once with --unique-prompts —
to see what the KV cache and batcher buy you.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx

PROMPTS = [
    "Explain how adaptive routing, batching and KV-cache work together.",
    "What does a warm pool buy you in an LLM serving platform?",
    "Why does dynamic batching improve GPU utilisation?",
    "Describe canary deployments for model rollouts.",
]


def pct(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    return data[min(len(data) - 1, int(p / 100 * len(data)))]


async def one_request(
    client: httpx.AsyncClient, prompt: str, model: str | None
) -> tuple[float, bool, bool]:
    start = time.perf_counter()
    body = {"messages": [{"role": "user", "content": prompt}], "max_tokens": 64}
    if model:
        body["model"] = model
    try:
        r = await client.post("/v1/chat/completions", json=body)
        ok = r.status_code == 200
        cached = ok and r.json().get("cached", False)
    except httpx.HTTPError:
        ok, cached = False, False
    return (time.perf_counter() - start) * 1000, ok, cached


async def run(
    base_url: str, n: int, concurrency: int, unique: bool, model: str | None
) -> dict:
    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0
    cache_hits = 0

    async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:
        if model is None:
            # Benchmark whatever the gateway actually serves.
            try:
                served = (await client.get("/v1/models")).json().get("models", [])
                if served:
                    model = served[0]["id"]
            except (httpx.HTTPError, ValueError, KeyError):
                pass
        print(f"# target model: {model or '(gateway default)'}")
        async def worker(i: int):
            nonlocal errors, cache_hits
            prompt = f"[{i}] {PROMPTS[i % len(PROMPTS)]}" if unique else PROMPTS[i % len(PROMPTS)]
            async with sem:
                latency, ok, cached = await one_request(client, prompt, model)
            latencies.append(latency)
            errors += not ok
            cache_hits += cached

        start = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(n)))
        wall = time.perf_counter() - start

    return {
        "num_requests": n,
        "concurrency": concurrency,
        "unique_prompts": unique,
        "p50_latency_ms": round(pct(latencies, 50), 1),
        "p95_latency_ms": round(pct(latencies, 95), 1),
        "p99_latency_ms": round(pct(latencies, 99), 1),
        "mean_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "throughput_rps": round(n / wall, 1),
        "error_rate": round(errors / n, 4),
        "cache_hit_pct": round(100 * cache_hits / n, 1),
        "wall_time_s": round(wall, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--unique-prompts", action="store_true")
    ap.add_argument("--model", help="model id; default: first model the gateway reports")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args()

    report = asyncio.run(
        run(args.base_url, args.requests, args.concurrency, args.unique_prompts, args.model)
    )
    print(json.dumps(report, indent=2))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
