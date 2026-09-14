Simulated engine, 300 requests per cell, concurrency 16, median of 3 runs, 32-request warm-up per scenario.
| scenario | workload | p50 ms | p95 ms | p99 ms | req/s | cache hit | errors | routed to |
|---|---|---:|---:|---:|---:|---:|---:|---|
| baseline | repeated prompts | 18 | 51 | 77 | 712 | 100% | 0.0% | - |
| baseline | unique prompts | 53 | 64 | 76 | 291 | 0% | 0.0% | - |
| batching_off | repeated prompts | 18 | 47 | 62 | 698 | 100% | 0.0% | - |
| batching_off | unique prompts | 50 | 57 | 69 | 332 | 0% | 0.0% | - |
| cache_off | repeated prompts | 52 | 63 | 69 | 296 | 0% | 0.0% | - |
| cache_off | unique prompts | 53 | 64 | 72 | 291 | 0% | 0.0% | - |
| routing_round_robin | repeated prompts | 18 | 52 | 72 | 710 | 100% | 0.0% | primary 307, slow-replica 307, flaky-replica 306 |
| routing_round_robin | unique prompts | 59 | 182 | 188 | 162 | 0% | 9.3% | primary 307, slow-replica 307, flaky-replica 306 |
| routing_latency | repeated prompts | 18 | 48 | 78 | 685 | 100% | 0.0% | primary 745, slow-replica 3, flaky-replica 171 |
| routing_latency | unique prompts | 52 | 64 | 77 | 293 | 0% | 2.3% | primary 745, slow-replica 3, flaky-replica 171 |
| routing_adaptive | repeated prompts | 17 | 51 | 86 | 704 | 100% | 0.0% | primary 884, slow-replica 16, flaky-replica 16 |
| routing_adaptive | unique prompts | 53 | 64 | 78 | 292 | 0% | 0.0% | primary 884, slow-replica 16, flaky-replica 16 |
