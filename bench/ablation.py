"""Per-feature ablation: start the gateway once per scenario, run the benchmark, tabulate.

    python bench/ablation.py --requests 300 --concurrency 16

Each scenario in bench/ablation/*.yaml flips one thing relative to baseline.yaml:
batching off, cache off, or the routing strategy on a three-replica pool
(healthy / +120 ms / 30% errors). Results land in bench/results/ablation.json
and bench/results/ablation.md. Uses the built-in simulated engine, so the
numbers measure the gateway's own behaviour, not GPU inference.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
from benchmark import run as run_bench  # noqa: E402

ORDER = ["baseline", "batching_off", "cache_off", "routing_round_robin", "routing_latency", "routing_adaptive"]
PORT = 8010


def start_gateway(config: Path) -> subprocess.Popen:
    env = {**os.environ, "LSP_CONFIG_FILE": str(config), "LSP_LOG_LEVEL": "WARNING"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=ROOT / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"gateway did not become healthy for {config.name}")


async def routing_split() -> dict[str, int]:
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", timeout=10) as c:
        r = await c.get("/v1/routing/stats")
        if r.status_code != 200:
            return {}
        return {e["name"]: e.get("routed", 0) for e in r.json().get("endpoints", [])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=300)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--repeats", type=int, default=3, help="runs per cell; the table reports the median")
    ap.add_argument("--only", nargs="*", help="subset of scenarios to run")
    args = ap.parse_args()
    order = [n for n in ORDER if not args.only or n in args.only]

    results = []
    for name in order:
        cfg = ROOT / "bench" / "ablation" / f"{name}.yaml"
        proc = start_gateway(cfg)
        try:
            # Warm the pool once so cold starts are not attributed to a feature.
            asyncio.run(run_bench(f"http://127.0.0.1:{PORT}", 32, args.concurrency, False, None))
            rec = {"scenario": name}
            for label, unique in (("repeated", False), ("unique", True)):
                runs = [asyncio.run(run_bench(f"http://127.0.0.1:{PORT}", args.requests, args.concurrency, unique, None,
                                              salt=f"r{rep}-"))
                        for rep in range(args.repeats)]
                rec[label] = {k: (median(r[k] for r in runs) if isinstance(runs[0][k], (int, float)) else runs[0][k])
                              for k in runs[0]}
                rec[label]["runs"] = runs
            rec["routing_split"] = asyncio.run(routing_split())
            results.append(rec)
            print(f"{name:22s} repeated p50={rec['repeated']['p50_latency_ms']:>6} p95={rec['repeated']['p95_latency_ms']:>7} "
                  f"rps={rec['repeated']['throughput_rps']:>6} hit={rec['repeated']['cache_hit_pct']:>5}% | "
                  f"unique p50={rec['unique']['p50_latency_ms']:>6} p95={rec['unique']['p95_latency_ms']:>7} "
                  f"rps={rec['unique']['throughput_rps']:>6} err={rec['unique']['error_rate']:.3f} split={rec['routing_split']}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    out = ROOT / "bench" / "results"
    out.mkdir(exist_ok=True)
    (out / "ablation.json").write_text(json.dumps({"requests": args.requests, "concurrency": args.concurrency, "results": results}, indent=2))
    lines = [f"Simulated engine, {args.requests} requests per cell, concurrency {args.concurrency}, "
             f"median of {args.repeats} runs, 32-request warm-up per scenario.", "",
             "| scenario | workload | p50 ms | p95 ms | p99 ms | req/s | cache hit | errors | routed to |", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for rec in results:
        for label in ("repeated", "unique"):
            r = rec[label]
            split = ", ".join(f"{k} {v}" for k, v in rec["routing_split"].items()) if len(rec["routing_split"]) > 1 else "-"
            lines.append(f"| {rec['scenario']} | {label} prompts | {r['p50_latency_ms']:.0f} | {r['p95_latency_ms']:.0f} | {r['p99_latency_ms']:.0f} | "
                         f"{r['throughput_rps']:.0f} | {r['cache_hit_pct']:.0f}% | {r['error_rate']*100:.1f}% | {split} |")
    (out / "ablation.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
