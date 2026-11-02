import asyncio
import json
import os
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv
from pgvector.asyncpg import register_vector

from servecopilot.db import create_pool
from servecopilot.retrieval.dense import search_by_vector
from servecopilot.retrieval.embed import QUERY_PREFIX, embed_documents, load_model

GOLD_PATH = Path("eval/data/gold_v1.jsonl")
K = 10
EXACT_SQL = """
    SELECT id FROM chunks WHERE source_ref <> $2
    ORDER BY embedding <=> $1 LIMIT $3
"""


def percentile(values, p):
    return statistics.quantiles(values, n=100)[p - 1]


async def timed_searches(conn, cases, vectors, ef_search, exact=False):
    latencies, results = [], []
    for case, vector in zip(cases, vectors):
        start = time.perf_counter()
        if exact:
            async with conn.transaction():
                # No index -> scan every row: the true top-k, used as the reference.
                await conn.execute("SET LOCAL enable_indexscan = off")
                rows = await conn.fetch(EXACT_SQL, vector, str(case["issue_id"]), K)
        else:
            rows = await search_by_vector(
                conn, vector, k=K, exclude=[str(case["issue_id"])], ef_search=ef_search
            )
        latencies.append((time.perf_counter() - start) * 1000)
        # Identify results by chunk id: one doc file has many chunks with the same source_ref.
        results.append({row["id"] for row in rows})
    return latencies, results


def load_cases():
    with GOLD_PATH.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file]


async def run(database_url, cases):
    model = load_model()
    # Embed all queries up front: we measure database latency, not the model.
    vectors = embed_documents(model, [QUERY_PREFIX + c["query_text"] for c in cases])

    pool = await create_pool(database_url, init=register_vector)
    try:
        async with pool.acquire() as conn:
            _, exact = await timed_searches(conn, cases, vectors, 0, exact=True)
            for label, ef, is_exact in [
                ("exact", 0, True),
                ("ef_search=40", 40, False),
                ("ef_search=100", 100, False),
            ]:
                await timed_searches(
                    conn, cases[:20], vectors[:20], ef, is_exact
                )  # warm-up
                latencies, results = await timed_searches(
                    conn, cases, vectors, ef, is_exact
                )
                recall = statistics.mean(len(r & e) / K for r, e in zip(results, exact))
                print(
                    f"{label:14} p50={percentile(latencies, 50):6.2f} ms  "
                    f"p95={percentile(latencies, 95):6.2f} ms  "
                    f"recall@{K} vs exact={recall:.3f}"
                )
    finally:
        await pool.close()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(run(os.environ["DATABASE_URL"], load_cases()))
