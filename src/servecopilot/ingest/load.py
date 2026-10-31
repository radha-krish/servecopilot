import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from servecopilot.db import create_pool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoadSettings:
    database_url: str
    issues_path: Path = Path("data/raw/issues.jsonl")
    prs_path: Path = Path("data/raw/prs.jsonl")
    method: str = "many"

    @classmethod
    def from_env(cls, **overrides):
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise SystemExit("DATABASE_URL not set — add it to .env")
        return cls(database_url=database_url, **overrides)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Load issues and PRs from JSONL into Postgres (safe to re-run)."
    )
    parser.add_argument(
        "--issues",
        dest="issues_path",
        type=Path,
        default=LoadSettings.issues_path,
        help="issues JSONL (default: %(default)s)",
    )
    parser.add_argument(
        "--prs",
        dest="prs_path",
        type=Path,
        default=LoadSettings.prs_path,
        help="PRs JSONL (default: %(default)s)",
    )
    parser.add_argument(
        "--method",
        choices=sorted(INSERT_METHODS),
        default=LoadSettings.method,
        help="how rows are sent to Postgres (default: %(default)s)",
    )
    return parser.parse_args(argv)


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[str, ...]
    key: tuple[str, ...]
    # True: on conflict, overwrite the other columns. False: keep the existing row.
    update: bool

    def conflict_clause(self):
        key = ", ".join(self.key)
        if not self.update:
            return f"ON CONFLICT ({key}) DO NOTHING"
        updates = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in self.columns
            if column not in self.key
        )
        return f"ON CONFLICT ({key}) DO UPDATE SET {updates}"

    def insert_values_sql(self):
        columns = ", ".join(self.columns)
        placeholders = ", ".join(f"${i}" for i in range(1, len(self.columns) + 1))
        return (
            f"INSERT INTO {self.name} ({columns}) VALUES ({placeholders}) "
            f"{self.conflict_clause()}"
        )

    def insert_select_sql(self, source):
        columns = ", ".join(self.columns)
        return (
            f"INSERT INTO {self.name} ({columns}) SELECT {columns} FROM {source} "
            f"{self.conflict_clause()}"
        )


ISSUES = Table(
    name="issues",
    columns=(
        "number",
        "title",
        "body",
        "labels",
        "created_at",
        "closed_at",
        "state_reason",
    ),
    key=("number",),
    update=True,
)
PULL_REQUESTS = Table(
    name="pull_requests",
    columns=("number", "title", "body", "merged_at"),
    key=("number",),
    update=True,
)
PR_FILES = Table(
    name="pr_files",
    columns=("pr_number", "file_path"),
    key=("pr_number", "file_path"),
    update=False,
)
ISSUE_PR_LINKS = Table(
    name="issue_pr_links",
    columns=("issue_number", "pr_number"),
    key=("issue_number", "pr_number"),
    update=False,
)

COUNTS_QUERY = """
    SELECT
        (SELECT count(*) FROM issues) AS issues,
        (SELECT count(*) FROM pull_requests) AS pull_requests,
        (SELECT count(*) FROM pr_files) AS pr_files,
        (SELECT count(*) FROM issue_pr_links) AS issue_pr_links
"""


def read_jsonl(path):
    if not path.exists():
        raise SystemExit(f"{path} not found — run the fetchers first")

    with path.open(encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def parse_timestamp(value):
    # asyncpg needs datetime objects for TIMESTAMPTZ, not ISO strings.
    return datetime.fromisoformat(value) if value else None


def issue_row(issue):
    return (
        issue["number"],
        issue["title"],
        issue["body"],
        issue["labels"],
        parse_timestamp(issue["created_at"]),
        parse_timestamp(issue["closed_at"]),
        issue["state_reason"],
    )


def pr_row(pr):
    return (
        pr["number"],
        pr["title"],
        pr["body"],
        parse_timestamp(pr["merged_at"]),
    )


def pr_file_rows(prs):
    return [(pr["number"], path) for pr in prs for path in pr["changed_files"]]


def link_rows(issues, loaded_pr_numbers):
    # A link needs both ends to exist (foreign keys). Skip PRs we have no
    # details for (e.g. their fetch failed) instead of failing the whole load.
    rows = []
    skipped = []
    for issue in issues:
        for pr_number in issue["fixing_prs"]:
            if pr_number in loaded_pr_numbers:
                rows.append((issue["number"], pr_number))
            else:
                skipped.append(pr_number)
    return rows, skipped


async def insert_row_by_row(conn, table, rows):
    # Baseline: one execute() per row, each waiting for the server's reply.
    query = table.insert_values_sql()
    for row in rows:
        await conn.execute(query, *row)


async def insert_many(conn, table, rows):
    # One prepared statement; asyncpg pipelines all rows to the server
    # without waiting for a reply after each one.
    await conn.executemany(table.insert_values_sql(), rows)


async def insert_copy(conn, table, rows):
    # COPY streams rows in bulk but cannot do ON CONFLICT. So COPY into an
    # empty temporary table first, then upsert from it with one INSERT ... SELECT.
    staging = f"staging_{table.name}"
    await conn.execute(
        f"CREATE TEMP TABLE {staging} (LIKE {table.name} INCLUDING DEFAULTS) "
        "ON COMMIT DROP"
    )
    await conn.copy_records_to_table(staging, records=rows, columns=table.columns)
    await conn.execute(table.insert_select_sql(staging))


INSERT_METHODS = {
    "row": insert_row_by_row,
    "many": insert_many,
    "copy": insert_copy,
}


async def table_counts(conn):
    return dict(await conn.fetchrow(COUNTS_QUERY))


async def load(conn, issues, prs, insert_rows):
    links, skipped = link_rows(issues, {pr["number"] for pr in prs})
    if skipped:
        logger.warning("Skipped %d links to PRs not in the PR file", len(skipped))

    # Order matters: links and files reference issues and pull_requests.
    steps = [
        (ISSUES, [issue_row(issue) for issue in issues]),
        (PULL_REQUESTS, [pr_row(pr) for pr in prs]),
        (PR_FILES, pr_file_rows(prs)),
        (ISSUE_PR_LINKS, links),
    ]

    # One transaction: either everything is loaded or nothing is. Upserts make
    # a failed run safe to simply re-run.
    async with conn.transaction():
        for table, rows in steps:
            start_time = time.perf_counter()
            await insert_rows(conn, table, rows)
            logger.info(
                "%-15s %5d rows in %.2fs",
                table.name,
                len(rows),
                time.perf_counter() - start_time,
            )


async def run(settings):
    issues = read_jsonl(settings.issues_path)
    prs = read_jsonl(settings.prs_path)
    logger.info("Read %d issues and %d PRs", len(issues), len(prs))

    pool = await create_pool(settings.database_url)
    try:
        async with pool.acquire() as conn:
            before = await table_counts(conn)
            start_time = time.perf_counter()
            await load(conn, issues, prs, INSERT_METHODS[settings.method])
            elapsed_time = time.perf_counter() - start_time
            after = await table_counts(conn)
    finally:
        await pool.close()

    logger.info("Row counts before: %s", before)
    logger.info("Row counts after:  %s", after)
    logger.info("Total load time (%s): %.2fs", settings.method, elapsed_time)


def main(argv=None):
    args = parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    asyncio.run(run(LoadSettings.from_env(**vars(args))))


if __name__ == "__main__":
    main()
