import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from dotenv import load_dotenv
from pgvector.asyncpg import register_vector

from servecopilot.components import files_component
from servecopilot.db import create_pool
from servecopilot.retrieval.chunking import pack_paragraphs, split_by_headings
from servecopilot.retrieval.embed import embed_documents, load_model
from servecopilot.retrieval.text_prep import issue_text, pr_text

logger = logging.getLogger(__name__)

DOCS_ROOT = Path("data/raw/vllm/docs")
MIN_WORDS = 20  # skip heading-only stubs
LIMIT = None  # set to 300 for a quick first run

ISSUES_SQL = "SELECT number, title, body, created_at FROM issues ORDER BY number"
PRS_SQL = """
    SELECT p.number, p.title, p.body, p.merged_at,
           coalesce(array_agg(f.file_path ORDER BY f.file_path)
                    FILTER (WHERE f.file_path IS NOT NULL), '{}') AS files
    FROM pull_requests p
    LEFT JOIN pr_files f ON f.pr_number = p.number
    GROUP BY p.number
    ORDER BY p.number
"""
UPSERT_SQL = """
    INSERT INTO chunks (source_type, source_id, source_ref, chunk_index, heading_path,
                        content, created_at, component, version, embedding)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    ON CONFLICT (source_type, source_ref, chunk_index) DO UPDATE SET
        source_id = EXCLUDED.source_id,
        heading_path = EXCLUDED.heading_path,
        content = EXCLUDED.content,
        created_at = EXCLUDED.created_at,
        component = EXCLUDED.component,
        version = EXCLUDED.version,
        embedding = EXCLUDED.embedding
"""


class ChunkRow(NamedTuple):
    # Field order = column order in UPSERT_SQL ($1..$9; the vector is $10).
    source_type: str
    source_id: int | None
    source_ref: str
    chunk_index: int
    heading_path: str | None
    content: str
    created_at: datetime | None
    component: str | None
    version: str | None


def issue_rows(issues):
    return [
        ChunkRow(
            "issue",
            i["number"],
            str(i["number"]),
            0,
            None,
            issue_text(i["title"], i["body"]),
            i["created_at"],
            None,
            None,
        )
        for i in issues
    ]


def pr_rows(prs):
    return [
        ChunkRow(
            "pr",
            p["number"],
            str(p["number"]),
            0,
            None,
            pr_text(p["title"], p["body"], p["files"]),
            p["merged_at"],
            files_component(p["files"]),
            None,
        )
        for p in prs
    ]


def git_sha(repo):
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def doc_rows(docs_root):
    version = git_sha(docs_root)  # which vLLM commit these docs describe
    rows = []
    for path in sorted(docs_root.rglob("*.md")):
        ref = str(path.relative_to(docs_root))
        index = 0
        for heading_path, section in split_by_headings(
            path.read_text(encoding="utf-8")
        ):
            for piece in pack_paragraphs(section):
                if len(piece.split()) < MIN_WORDS:
                    continue
                content = f"{heading_path}\n\n{piece}" if heading_path else piece
                rows.append(
                    ChunkRow(
                        "doc",
                        None,
                        ref,
                        index,
                        heading_path,
                        content,
                        None,
                        None,
                        version,
                    )
                )
                index += 1
    return rows


async def run(database_url):
    pool = await create_pool(database_url, init=register_vector)
    try:
        async with pool.acquire() as conn:
            issues = await conn.fetch(ISSUES_SQL)
            prs = await conn.fetch(PRS_SQL)
        rows = (
            issue_rows(issues[:LIMIT])
            + pr_rows(prs[:LIMIT])
            + doc_rows(DOCS_ROOT)[:LIMIT]
        )
        logger.info("Rows to embed: %d", len(rows))

        model = load_model()
        start = time.perf_counter()
        vectors = embed_documents(model, [row.content for row in rows])
        elapsed = time.perf_counter() - start
        logger.info(
            "Embedded %d texts in %.1fs (%.1f texts/s)",
            len(rows),
            elapsed,
            len(rows) / elapsed,
        )

        async with pool.acquire() as conn, conn.transaction():
            await conn.executemany(
                UPSERT_SQL, [(*row, vector) for row, vector in zip(rows, vectors)]
            )
        logger.info("Upserted %d chunks", len(rows))
    finally:
        await pool.close()


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # hide model-download noise
    asyncio.run(run(os.environ["DATABASE_URL"]))


if __name__ == "__main__":
    main()
