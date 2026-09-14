Simulated engine, 300 requests per cell, concurrency 16, median of 1 runs, 32-request warm-up per scenario.

| scenario | workload | p50 ms | p95 ms | p99 ms | req/s | cache hit | errors | routed to |
|---|---|---:|---:|---:|---:|---:|---:|---|
| baseline | repeated prompts | 24 | 72 | 90 | 504 | 100% | 0.0% | - |
| baseline | unique prompts | 54 | 64 | 73 | 288 | 0% | 0.0% | - |
