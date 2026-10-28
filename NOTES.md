## 5,000-issue extrapolation

Based on the 500-issue baseline:

- Estimated API calls: 50
- Estimated GraphQL points: 100
- Estimated wall time: ~113 seconds (~1.9 minutes)

This is an extrapolation, not a measured result.


100 issues
→ 1 API call
→ 1.98 seconds
→ 2 GraphQL points

500 issues
→ 5 API calls
→ 11.30 seconds
→ 10 GraphQL points

## Day 2 — Async PR ingestion benchmark

**Workload:** 268 PRs, three trials per concurrency level.

| Concurrency | Trial 1 (s) | Trial 2 (s) | Trial 3 (s) | Average (s) | Speedup |
|---:|---:|---:|---:|---:|---:|
| 1 | 148.86 | 151.56 | 150.15 | 150.19 | 1.00× |
| 4 | 36.12 | 35.65 | 36.50 | 36.09 | 4.16× |
| 8 | 18.56 | 17.78 | 18.17 | 18.17 | 8.27× |
| 16 | 9.69 | 9.05 | 9.13 | 9.29 | 16.17× |
| 32 | 6.12 | 5.74 | 5.48 | 5.78 | 25.99× |
| 64 | 3.43 | 2.93 | 3.38 | 3.25 | 46.19× |

**Observations**
- Async concurrency substantially reduced wall time for this network-bound workload.
- All trials fetched 268 PRs successfully, with zero retries and zero failures.
- Speedup was sublinear at higher concurrency.
- The optimal concurrency limit has not yet been established; higher limits require testing with rate-limit and error monitoring.

**Speedup formula:** baseline average wall time / concurrency-level average wall time.