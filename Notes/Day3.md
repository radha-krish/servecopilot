# ServeCopilot — Day 3: Postgres + pgvector

Day 3 gives the data a home.

After Day 2, issues and PRs lived in JSONL files. Files cannot be queried or joined, and re-running ingestion has no notion of "this row already exists". Later days also need vector search and keyword search over the same rows.

This day moves the data into **Postgres with pgvector**, running in Docker, through a loader that is **safe to re-run any number of times**.

## What I Built

1. `compose.yaml`: Postgres 18 with pgvector, a named volume and a healthcheck.
2. `db/001_schema.sql`: tables, foreign keys and indexes.
3. `src/servecopilot/db.py`: creates an asyncpg connection pool.
4. `src/servecopilot/ingest/load.py`: reads both JSONL files and upserts them:
   - Issues
   - Pull requests
   - Changed files per PR
   - Issue → fixing-PR links
5. The whole load runs in one transaction.
6. Re-running gives the same row counts (idempotent).
7. Three ways to send rows, selectable with `--method`: `row`, `many`, `copy`.

## How to Run

```bash
docker compose up -d                 # start Postgres
docker compose ps                    # STATUS should say (healthy)

uv run servecopilot-ingest --limit 10000
uv run servecopilot-fetch-prs --concurrency 16
uv run servecopilot-load             # default --method many
uv run servecopilot-load --method copy
uv run servecopilot-load --help
```

`.env` needs:

```text
DATABASE_URL=postgresql://servecopilot:<password>@localhost:5432/servecopilot
```

## Architecture

```text
issues.jsonl ─┐
              ├─► read_jsonl()
prs.jsonl ────┘        │
                       ▼
             row builders (pure functions)
             issue_row / pr_row / pr_file_rows / link_rows
                       │
                       ▼
             load()  ── one transaction
                       │
                       ├── issues          (upsert)
                       ├── pull_requests   (upsert)
                       ├── pr_files        (insert, skip existing)
                       └── issue_pr_links  (insert, skip existing)
                       │
                       ▼
             insert method: row | many | copy
                       │
                       ▼
             Postgres (Docker, pgvector)
```

## Docker Compose

```yaml
image: pgvector/pgvector:pg18
volumes:
  - postgres_data:/var/lib/postgresql        # data survives restarts
  - ./db:/docker-entrypoint-initdb.d:ro      # schema on first start
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U servecopilot -d servecopilot"]
```

- **Named volume:** `docker compose down` keeps the data. `docker compose down -v` deletes it.
- **Healthcheck:** "container is running" is not the same as "Postgres accepts connections". `pg_isready` checks the second one.
- **initdb scripts run only when the volume is empty.** Changing `001_schema.sql` later does nothing to an existing database. Every statement uses `IF NOT EXISTS`, so the file can also be applied by hand:

```bash
docker compose exec -T db psql -U servecopilot -d servecopilot < db/001_schema.sql
```

## Schema

| Table | Key | Notes |
|---|---|---|
| `issues` | `number` | `labels TEXT[]`, dates as `TIMESTAMPTZ` |
| `pull_requests` | `number` | |
| `issue_pr_links` | `(issue_number, pr_number)` | Foreign keys to both tables |
| `pr_files` | `(pr_number, file_path)` | Foreign key to `pull_requests` |
| `chunks` | `id` | Empty until Day 5 adds the vector column |

The file starts with `CREATE EXTENSION IF NOT EXISTS vector;` (pgvector 0.8.7).

Indexes:

- A primary key is also an index. `issue_pr_links` PK starts with `issue_number`, so "which PRs fixed this issue?" is fast.
- `issue_pr_links_pr_number_idx` serves the reverse: "which issues did this PR fix?".

## Idempotency

An ingestion job is **idempotent** when running it twice gives the same result as running it once.

Plain `INSERT` fails (or duplicates rows) on the second run. The loader uses upserts:

```sql
-- issues, pull_requests: update the row if it already exists
INSERT INTO issues (...) VALUES (...)
ON CONFLICT (number) DO UPDATE SET title = EXCLUDED.title, ...

-- pr_files, issue_pr_links: nothing to update, keep the existing row
INSERT INTO pr_files (...) VALUES (...)
ON CONFLICT (pr_number, file_path) DO NOTHING
```

`EXCLUDED` is the row that was rejected by the conflict, i.e. the new values.

Proof from a real run (10,000 issues):

```text
Run 1  before: issues 500,   PRs 268,  files 1004, links 275
       after:  issues 10000, PRs 1983, files 8370, links 2108
Run 2  before: issues 10000, PRs 1983, files 8370, links 2108
       after:  issues 10000, PRs 1983, files 8370, links 2108   ← unchanged
```

The loader logs these counts on every run.

## One Transaction

```python
async with conn.transaction():
    for table, rows in steps:
        await insert_rows(conn, table, rows)
```

- Either all four tables are loaded, or nothing is.
- My first version caught every exception per row and carried on, which could leave half-loaded tables with only a printed message.
- Because the load is idempotent, a failed run can simply be run again.

## Load Order and Foreign Keys

```text
issues → pull_requests → pr_files → issue_pr_links
```

Links reference both issues and PRs, so both must exist first.

If an issue links to a PR that is not in `prs.jsonl` (for example its fetch failed), the link would violate the foreign key. `link_rows()` skips those links and the loader logs how many were skipped, instead of failing the whole load.

## Table Specs

Each table is described once:

```python
PULL_REQUESTS = Table(
    name="pull_requests",
    columns=("number", "title", "body", "merged_at"),
    key=("number",),
    update=True,          # False → ON CONFLICT DO NOTHING
)
```

The SQL is generated from it:

- `insert_values_sql()` → `INSERT ... VALUES ($1, ...) ON CONFLICT ...` (for `row` and `many`)
- `insert_select_sql(staging)` → `INSERT ... SELECT ... FROM staging ON CONFLICT ...` (for `copy`)

The rows are built by pure functions (`issue_row`, `pr_row`, ...), so all three insert methods load exactly the same rows. Only the way rows are sent differs.

asyncpg gotcha: `TIMESTAMPTZ` needs a `datetime`, not an ISO string. `parse_timestamp()` converts with `datetime.fromisoformat()`.

## Three Insert Methods

### row

```python
for row in rows:
    await conn.execute(query, *row)
```

Send one row, wait for the reply, send the next. One network round trip per row.

### many

```python
await conn.executemany(query, rows)
```

The statement is prepared once, and asyncpg sends all rows **without waiting for a reply after each one** (pipelining).

### copy

```python
CREATE TEMP TABLE staging_x (LIKE x INCLUDING DEFAULTS) ON COMMIT DROP
copy_records_to_table(staging_x, records=rows, columns=...)
INSERT INTO x SELECT ... FROM staging_x ON CONFLICT ...
```

COPY is Postgres's bulk-load protocol, but it **cannot do `ON CONFLICT`**. So rows are copied into an empty temporary table first, then upserted from there with one statement. The temp table is dropped at commit.

## Benchmark

**Workload:** 22,461 rows (10,000 issues, 1,983 PRs, 8,370 files, 2,108 links). Separate benchmark database, three trials per method.

### Total

| Method | Empty tables (s) | Full tables / re-run (s) | Speedup |
|---|---:|---:|---:|
| row | 4.82 | 4.85 | 1.0× |
| many | 1.09 | 1.12 | ~4.4× |
| copy | 1.11 | 1.10 | ~4.4× |

### Per table (empty tables)

| Table | Rows | row (s) | many (s) | copy (s) |
|---|---:|---:|---:|---:|
| issues | 10,000 | 2.94 | 0.92 | 1.14 |
| pull_requests | 1,983 | 0.35 | 0.06 | 0.06 |
| pr_files | 8,370 | 1.20 | 0.05 | 0.04 |
| issue_pr_links | 2,108 | 0.30 | 0.02 | 0.02 |

All three methods produced **identical data**: the MD5 fingerprint of every table matched.

### Why row-by-row is slow

At about 215 µs per row, most of the time is **waiting for the reply**, not Postgres doing work. Same lesson as Day 2: the cost was waiting.

The database runs on the same machine, so this is a best case. With a database 1 ms away, row-by-row would take about 25 s while `many` would barely change.

### Why COPY did not beat executemany

The issues table is big:

```text
issue bodies: 83.7 MB total, 8.4 KB average, 66 KB max → 39 MB on disk (compressed)
```

1. **For `issues`, the cost is the bytes, not the round trips.** Postgres must receive, compress and write ~84 MB whichever method is used. `many` already removed the waiting.
2. **COPY writes the data twice** (staging, then the real table), so it is slightly slower for `issues`.
3. **For small rows (`pr_files`), round trips are the cost:** row 1.20 s → many 0.05 s (24×) → copy 0.04 s. COPY's advantage over `many` only becomes large at millions of small rows.

**Decision:** default `--method many`. As fast as COPY here, simpler, no staging step.

**Lesson:** measure per table. The total hid that three of the four tables already take ~0.1 s together.

### Re-runs are as cheap as first loads

Empty vs full tables made almost no difference, so the `ON CONFLICT` path costs about the same as a fresh insert at this size.

## Tests

`tests/test_load.py` (no database needed):

- `parse_timestamp` returns a timezone-aware `datetime`, and `None` for `None`
- `issue_row` / `pr_row` match the column order of the tables
- `pr_file_rows` produces one row per changed file
- `link_rows` skips PRs without details
- Generated SQL for an upsert table and a "do nothing" table
- CLI defaults, unknown `--method` rejected, `DATABASE_URL` required

## Known Limitations

- **No idempotency test against a test database yet** (required by Day 3's definition of done). Today idempotency is shown by the logged row counts.
- **No migration runner.** Schema changes need manual `psql` or `docker compose down -v`. Next step: numbered SQL files plus a `schema_migrations` table.
- **The password is written in `compose.yaml`.** It should come from `.env` via `${POSTGRES_PASSWORD}`.
- **Keys are PR/issue numbers only, without the repo.** Loading a second repo (`--owner/--repo`) would collide.
- **Stale rows are not removed.** If a PR's file list shrinks, old `pr_files` rows stay. Upserts add and update, they never delete.

## Interview Questions

**Why Postgres + pgvector instead of Pinecone/Qdrant? When would you switch?**
One database holds the rows, the joins (issue → PR → files), keyword search and vector search, with transactions across all of them. One system to run, back up and secure. At this size (thousands to a few million vectors) pgvector is fast enough. Switch when vector count or query load outgrows one Postgres node, or when you need features a vector DB does better (very large-scale ANN, multi-tenant vector sharding) and have measured that Postgres is the bottleneck.

**What is idempotency and why does every ingestion job need it?**
Running the job twice gives the same result as running it once. Jobs fail halfway, get retried, get scheduled twice. Without idempotency every retry creates duplicates or errors. Here: upserts keyed on primary keys, plus one transaction.

**How do you choose a connection-pool size?**
Start from what the database can handle (Postgres `max_connections`, CPU cores) and how many queries actually run at the same time. More connections than the database can serve in parallel only adds contention. The loader uses one connection (it runs sequentially); the pool (max 5) is for later, when the API serves concurrent requests. Measure under load and size to the knee, as with Day 2's concurrency.

**Why COPY, and why was it not faster here?**
COPY is the bulk-load protocol and wins for many small rows. Here the cost was dominated by ~84 MB of issue text, which every method has to write, and COPY's staging table writes it twice.
