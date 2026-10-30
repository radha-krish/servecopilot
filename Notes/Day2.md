# ServeCopilot — Day 2: Concurrent PR Ingestion

Day 2 adds the second data-ingestion component of ServeCopilot.

Day 1 produced closed issues with the numbers of the PRs that fixed them. Day 2 fetches the details of each of those PRs (title, body, merge time and changed file paths) and stores them as JSONL.

Fetching one PR at a time is slow because the program spends almost all its time waiting on the network. This day focuses on **bounded concurrency with asyncio** and on **retrying failures safely**.

## What I Built

The PR fetcher:

1. Reads `data/raw/issues.jsonl` (Day 1 output).
2. Collects the unique fixing-PR numbers.
3. Fetches each PR through GitHub's GraphQL API:
   - Number
   - Title
   - Body
   - Merge time
   - Changed file paths
4. Runs many requests at the same time, with a fixed upper limit.
5. Applies a timeout to every request.
6. Retries temporary failures with exponential backoff and jitter.
7. Respects GitHub's `Retry-After` and rate-limit headers.
8. Keeps going when one PR fails, and reports the failed PRs at the end.
9. Writes `data/raw/prs.jsonl` with the Day 1 atomic writer.
10. Provides CLI configuration for input, output and concurrency.

## How to Run

```bash
uv run servecopilot-ingest --limit 500        # Day 1: issues.jsonl
uv run servecopilot-fetch-prs                 # Day 2: prs.jsonl
uv run servecopilot-fetch-prs --concurrency 8
uv run servecopilot-fetch-prs --help
```

## Architecture

```text
issues.jsonl
     │
     ▼
get_needed_prs()  ── unique fixing-PR numbers
     │
     ▼
fetch_all()
     │
     ├── one shared httpx.AsyncClient
     ├── asyncio.Semaphore(concurrency)
     └── asyncio.TaskGroup
              │
              ▼
        fetch_one(pr)   × N tasks
              │
              ▼
         fetch_pr()
              │
              ▼
      post_with_retry()
              │
              ├── semaphore slot + timeout around the request
              ├── success      → return response
              ├── retryable    → sleep (Retry-After or backoff) → try again
              └── not retryable / out of attempts → raise
              │
              ▼
     results (sorted) + failures
              │
              ▼
       atomic_write()
              │
              ▼
         prs.jsonl
```

## Bug Found: PRs From Other Repositories

While checking why 2 PRs could not be fetched, I found that `closedByPullRequestsReferences` can include PRs from **other repositories**:

```text
issue #59449 → PR #2396 in NovaSky-AI/SkyRL
issue #54337 → PR #1040 in MaplePrivacyLabs/Maple
```

Day 1 stored only the PR number, and Day 2 looked that number up in `vllm-project/vllm`.

The dangerous case is when the other repo's PR number also exists in vLLM. Then the fetcher silently gets the **wrong PR**, with no error.

Fix (in Day 1):

```graphql
closedByPullRequestsReferences(first: 10) {
  nodes {
    number
    mergedAt
    repository { nameWithOwner }
  }
}
```

`parse_issue` keeps only PRs whose `nameWithOwner` matches the repo being ingested. The comparison is case-insensitive, because GitHub accepts `VLLM-Project/VLLM` as input but returns `vllm-project/vllm`.

After the fix: 268 unique PRs, 268 fetched, 0 missing.

Lesson: a failure that looks like "PR does not exist" can be a data bug further back in the pipeline.

## Async Concepts

### Why async helps here

The work is **I/O-bound**: each request spends about 0.56 s waiting for GitHub and almost no time on the CPU.

With async, while one request waits, the event loop starts or finishes other requests on the same thread.

```text
Sync:   [req 1 wait.....][req 2 wait.....][req 3 wait.....]
Async:  [req 1 wait.....]
        [req 2 wait.....]
        [req 3 wait.....]
```

### One shared client

```python
async with httpx.AsyncClient(headers=headers) as client:
```

All tasks share one client, so TCP/TLS connections are reused instead of being opened for every request.

### Semaphore: bounded concurrency

```python
semaphore = asyncio.Semaphore(settings.concurrency)
```

At most `concurrency` requests are in flight at once. Without a limit, all requests start together and trigger GitHub's secondary rate limits.

The semaphore is held **only while the request is in flight**, not while sleeping before a retry:

```python
async with semaphore, asyncio.timeout(REQUEST_TIMEOUT):
    response = await client.post(...)
# slot released here
await sleep(delay)
```

If the sleep were inside the semaphore, a task backing off for 30 s would block a slot for nothing.

### TaskGroup

```python
async with asyncio.TaskGroup() as tg:
    for pr_number in pr_numbers:
        tg.create_task(fetch_one(pr_number))
```

`TaskGroup` starts all tasks and waits for all of them.

Important: if **one** task raises, `TaskGroup` cancels **all** the others. So each task catches its own expected errors (see Failure Isolation).

### Timeout

```python
asyncio.timeout(REQUEST_TIMEOUT)   # 30 s
```

A request that hangs is cancelled and treated as a retryable failure.

## Retry Policy

### What is retried

| Response | Retry? | Reason |
|---|---|---|
| 429, 500, 502, 503, 504 | Yes | Temporary server or rate-limit problem |
| 403 with `retry-after` or `x-ratelimit-remaining: 0` | Yes | GitHub secondary rate limit |
| Plain 403, 401, 404 | No | Permission, bad token or missing PR will not fix itself |
| Connection error / timeout | Yes | Network problems are usually temporary |

### How long to wait

If the server says how long to wait, use that:

```text
Retry-After: 7          → wait 7 s
x-ratelimit-reset       → wait until the reset time
```

Otherwise, use exponential backoff with **full jitter**:

```python
cap = min(MAX_DELAY, BASE_DELAY * 2**attempt)   # 1, 2, 4, 8, 16, 30, ...
delay = random.uniform(0, cap)
```

Why jitter: if 32 tasks fail at the same moment, plain backoff makes all 32 retry at the same moment again. Random delays spread them out.

### Limits

```python
MAX_ATTEMPTS = 5
BASE_DELAY = 1.0
MAX_DELAY = 30.0
REQUEST_TIMEOUT = 30.0
```

After 5 failed attempts, the error is raised.

## Failure Isolation

```python
PR_FETCH_ERRORS = (httpx.HTTPError, TimeoutError, RuntimeError, KeyError, TypeError)

async def fetch_one(pr_number):
    try:
        results.append(await fetch_pr(...))
    except PR_FETCH_ERRORS as error:
        failures.append(pr_number)
```

- One failing PR does not cancel the other tasks.
- Only **expected** errors are caught. A real bug (for example `NameError`) still crashes loudly. Ruff's `BLE001` rule blocks `except Exception`.
- Successful PRs are written. If any PR failed, the program exits with a non-zero code and lists the failed PR numbers.

## Configuration

```python
@dataclass(frozen=True)
class PRSettings:
    token: str
    owner: str = Settings.owner
    repo: str = Settings.repo
    input_path: Path = Settings.output_path      # Day 1 output = Day 2 input
    output_path: Path = Path("data/raw/prs.jsonl")
    concurrency: int = 32
```

- Defaults come from Day 1's `Settings`, so the two steps stay linked.
- `--concurrency` must be between 1 and 100 (GitHub documents a limit of 100 concurrent requests).
- A missing input file gives: `not found — run servecopilot-ingest first`.
- `read_token()` is shared by both settings classes.
- `main()` is a normal function that calls `asyncio.run(run(settings))`, because script entry points cannot be async.

## Benchmark

**Workload:** 268 PRs, three trials per concurrency level.

| Concurrency | Average (s) | Speedup |
|---:|---:|---:|
| 1 | 150.19 | 1.00× |
| 4 | 36.09 | 4.16× |
| 8 | 18.17 | 8.27× |
| 16 | 9.29 | 16.17× |
| 32 | 5.78 | 25.99× |
| 64 | 3.25 | 46.19× |

All trials: 268 PRs fetched, 0 retries, 0 failures. Full trial data is in `NOTES.md`.

### Why speedup falls off

At concurrency 1, one PR takes about 150.19 / 268 ≈ **0.56 s**.

Ideal time = (number of rounds of requests) × 0.56 s:

| Concurrency | Ideal (s) | Actual (s) | Efficiency |
|---:|---:|---:|---:|
| 4 | 37.5 | 36.1 | ~100% |
| 16 | 9.4 | 9.3 | ~100% |
| 32 | 4.7 | 5.8 | ~81% |
| 64 | 2.4 | 3.3 | ~72% |

Up to 16, scaling is almost perfect. After that:

1. **The slowest request decides when the run ends.** At 64 the job is only about 4 rounds, so one slow response in the last round sets the total time.
2. **The last round is not full.** 268 / 64 = 4.2, so the final round uses only about 12 of 64 slots.

### Zero retries does not mean 64 is safe

This workload was too small to hit GitHub's limits.

GitHub's secondary limit for GraphQL is roughly 2,000 points per minute (check the current docs). Each PR query costs about 1 point:

```text
268 PRs at 64   → 268 points in ~3 s       → fine (small total)
~5,000 PRs at 64 → ~5,000 points in ~1 min → over the limit → 403s and retries
```

The right concurrency depends on the **total number of requests**, not only on speed. Reasonable default: 16–32.

## Tests

No network: `httpx.MockTransport` is a fake GitHub, and `sleep` is passed in so tests do not actually wait.

`tests/test_fetch_async.py`:

- 503 → 502 → 200: 3 attempts, 2 sleeps, success
- 401: 1 attempt, no retry
- 429 with `retry-after: 7`: slept exactly 7 s
- 403 rate limit is retried; plain 403 is not
- `ConnectError` is retried
- Gives up after `MAX_ATTEMPTS`
- Backoff delay always stays within its cap
- Semaphore: 20 PRs with limit 3 → at most 3 requests in flight
- One PR returns 404 → the other PRs still succeed, `failures == [2]`

`tests/test_fetch_async_settings.py`:

- CLI defaults match `PRSettings`
- `--in`, `--out`, `--concurrency` override defaults
- `0`, `-1`, `abc`, `101` are rejected for `--concurrency`
- `from_env` combines the token with CLI values

## Known Limitations

- `files(first: 100)` has no `totalCount` check, so a very large PR can lose files without a warning.
- GitHub can report rate limiting as **HTTP 200 with a `RATE_LIMITED` GraphQL error**. This is treated as a failure, not retried.
- The benchmark did not reach GitHub's limits, so the real "knee" for large runs is still unmeasured.

## Interview Questions

**async vs threads vs processes — when to pick each?**
- async: many I/O waits on one thread (network calls like this). Cheapest per task.
- threads: I/O with libraries that are blocking and have no async version.
- processes: CPU-bound work, to use several cores and avoid the GIL.

**What happens if you call a blocking function inside an async function?**
It blocks the whole event loop, so every other task stops until it returns. Use the async version, or `asyncio.to_thread(...)` to run it in a thread.

**How do you choose the concurrency limit for an external API?**
Start from the provider's documented limits (here: 100 concurrent, ~2,000 points/min), measure wall time and retries at several levels, and pick the lowest level near the knee. Re-check when the total request count grows.

**Why add jitter to backoff?**
Without jitter, clients that failed together retry together and cause the same burst again. Jitter spreads retries out over time.

**Why did throughput stop improving?**
Above 16, there are only a few rounds of requests, so the slowest response in the last round and the partly empty last round dominate total time. At larger scale, rate limits become the limit instead.
