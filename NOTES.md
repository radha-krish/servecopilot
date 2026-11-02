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
## Day 4 — gold_v1 label noise

**Gold set:** 250 cases from 2,049 candidates (75 with siblings, 175 without, seed 42). Details: `eval/data/handcheck_v1.md`.

| Label | Checked | Wrong | Estimate |
|---|---:|---:|---|
| Issue → fixing PR link | 20 | 0 (+1 partly) | ~0–5 %, 95 % CI up to ~16 % |
| Component (fresh sample, after fix) | 20 | 2 (+1 ambiguous) | ~10 %, 95 % CI ~3–30 % |

- Checked by Claude (model) from issue text, PR description and changed files; GitHub comment threads not read.
- First check found a component bug (unmapped code fell back to `tests`), fixed before committing gold_v1.
- Reading metrics: with ~10 % component noise and 250 cases, per-component differences of a few points are noise. Small components (decoding 3, compile 2) cannot be compared at all.

## Day 5 — Dense retrieval

**Corpus:** 13,976 chunks: 10,000 issues, 1,983 PRs, 1,993 doc chunks (vLLM `docs/`, 248 files).
**Model:** `BAAI/bge-small-en-v1.5` (384 dims) via sentence-transformers on Apple M4 Max (MPS), default batching.

| Measurement | Result |
|---|---|
| Embedding throughput | 13,976 texts in 48.0 s → **290.9 texts/s** |
| HNSW build (`m=16, ef_construction=64`) | **1.05–1.06 s** (3 builds), index size 27 MB |
| Issue body cleaning | avg 8,337 → 4,146 chars (env dumps removed) |

**Query latency** (250 gold queries, k=10, query embedding excluded; two runs):

| Method | p50 (ms) | p95 (ms) | Recall@10 vs exact |
|---|---:|---:|---:|
| exact (no index) | 9.5–13.4 | 10.9–14.8 | 1.000 |
| HNSW ef_search=40 | 1.25–1.35 | 1.5–1.7 | 0.987–0.989 |
| HNSW ef_search=100 | 1.6–1.8 | 2.0–2.2 | 0.996–0.998 |

- HNSW is ~7× faster than exact at 14k vectors. On a 900-row test, exact was faster (1.3 vs 2.3 ms): the index only pays off as the table grows.
- ef_search 40 → 100 costs ~0.3–0.4 ms and recovers most missed neighbours. **Default is now 100.**
- Recall moves slightly between index rebuilds (0.989 → 0.987): HNSW builds a slightly different graph each time.
- "Recall vs exact" measures the index approximation only, not search quality. Quality vs gold_v1 is Day 6.
