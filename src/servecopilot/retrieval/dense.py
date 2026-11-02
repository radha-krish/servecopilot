import argparse
import asyncio
import os

from dotenv import load_dotenv
from pgvector.asyncpg import register_vector

from servecopilot.db import create_pool
from servecopilot.retrieval.embed import embed_query, load_model

SEARCH_SQL = """
    SELECT id, source_type, source_ref, heading_path,
           left(content, 100) AS preview,
           1 - (embedding <=> $1) AS score
    FROM chunks
    WHERE ($2::text[] IS NULL OR source_type = ANY($2))
      AND ($3::text IS NULL OR component = $3)
      AND NOT (source_ref = ANY($4::text[]))
    ORDER BY embedding <=> $1
    LIMIT $5
"""


async def search_by_vector(
    conn, vector, k=10, types=None, component=None, exclude=(), ef_search=100
):
    async with conn.transaction():
        # SET LOCAL lasts only for this transaction; it can't take $1 params.
        await conn.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")
        # Filters run after the HNSW scan; without this you can get < k rows.
        await conn.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
        rows = await conn.fetch(SEARCH_SQL, vector, types, component, list(exclude), k)
    # relaxed_order may return rows slightly out of order.
    return sorted(rows, key=lambda row: row["score"], reverse=True)


async def search_dense(conn, model, query, **filters):
    return await search_by_vector(conn, embed_query(model, query), **filters)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Dense search over issues, PRs and docs."
    )
    parser.add_argument("query")
    parser.add_argument("-k", type=int, default=10)
    parser.add_argument(
        "--type",
        action="append",
        choices=["issue", "pr", "doc"],
        help="repeatable; default: all types",
    )
    parser.add_argument("--component")
    # 100 vs 40: +0.3 ms p50, recall vs exact 0.989 -> 0.998 (eval/bench_dense.py).
    parser.add_argument("--ef-search", type=int, default=100)
    return parser.parse_args(argv)


async def run(args, database_url):
    model = load_model()
    pool = await create_pool(database_url, init=register_vector)
    try:
        async with pool.acquire() as conn:
            rows = await search_dense(
                conn,
                model,
                args.query,
                k=args.k,
                types=args.type,
                component=args.component,
                ef_search=args.ef_search,
            )
    finally:
        await pool.close()

    for row in rows:
        where = row["heading_path"] or row["preview"].replace("\n", " ")
        print(
            f"{row['score']:.3f}  {row['source_type']:5}  {row['source_ref']:<35}  {where[:70]}"
        )


def main():
    load_dotenv()
    asyncio.run(run(parse_args(), os.environ["DATABASE_URL"]))


if __name__ == "__main__":
    main()
