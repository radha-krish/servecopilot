"""Build the retrieval gold set from natural GitHub labels.

A merged PR that closes an issue is the "right answer" for that issue:
  - task (a): issue -> fixing PR
  - task (b): issue -> sibling issues (fixed by the same PR)
"""

import asyncio
import logging
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from servecopilot.components import files_component
from servecopilot.db import create_pool
from servecopilot.gold import sibling_issues, stratified_sample
from servecopilot.ingest.fetch_sync import atomic_write, write_jsonl_lines
from servecopilot.leakage import strip_issue_refs

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("eval/data/gold_v1.jsonl")
SIZE = 250
MIN_WITH_SIBLINGS = 75
SEED = 42

# Issues closed as fixed, with at least one merged fixing PR in the database.
CANDIDATES_QUERY = """
    SELECT
        i.number,
        i.title,
        i.body,
        array_agg(l.pr_number ORDER BY l.pr_number) AS gold_pr_ids
    FROM issues i
    JOIN issue_pr_links l ON l.issue_number = i.number
    WHERE i.state_reason = 'COMPLETED'
    GROUP BY i.number
    ORDER BY i.number
"""

PR_FILES_QUERY = """
    SELECT pr_number, array_agg(file_path ORDER BY file_path) AS files
    FROM pr_files
    GROUP BY pr_number
"""


async def fetch_data(database_url):
    pool = await create_pool(database_url)
    try:
        async with pool.acquire() as conn:
            candidates = [dict(row) for row in await conn.fetch(CANDIDATES_QUERY)]
            pr_files = {
                row["pr_number"]: row["files"]
                for row in await conn.fetch(PR_FILES_QUERY)
            }
    finally:
        await pool.close()
    return candidates, pr_files


async def run(database_url):
    candidates, pr_files = await fetch_data(database_url)
    logger.info("Candidates: %d issues", len(candidates))
    logger.info("PRs with file lists: %d", len(pr_files))

    siblings = sibling_issues(candidates)
    with_siblings = sum(1 for related in siblings.values() if related)
    logger.info(
        "Issues with siblings: %d (%.1f%%)",
        with_siblings,
        100 * with_siblings / len(candidates),
    )
    largest = max(siblings, key=lambda number: len(siblings[number]))
    logger.info(
        "Largest sibling group: issue #%d has %d siblings",
        largest,
        len(siblings[largest]),
    )

    # An issue's component: majority over all files of all its fixing PRs.
    components = {
        issue["number"]: files_component(
            [path for pr in issue["gold_pr_ids"] for path in pr_files.get(pr, [])]
        )
        for issue in candidates
    }
    logger.info(
        "Components (all candidates): %s",
        dict(Counter(components.values()).most_common()),
    )

    sample = set(
        stratified_sample(
            [issue["number"] for issue in candidates],
            siblings,
            SIZE,
            MIN_WITH_SIBLINGS,
            SEED,
        )
    )
    cases = [
        {
            "issue_id": issue["number"],
            # Cleaned on the query side too: some issues link their fixing PR.
            "query_text": strip_issue_refs(
                f"{issue['title']}\n\n{issue['body'] or ''}"
            ),
            "gold_pr_ids": issue["gold_pr_ids"],
            "gold_sibling_issue_ids": siblings[issue["number"]],
            "component": components[issue["number"]],
        }
        for issue in candidates
        if issue["number"] in sample
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with atomic_write(OUTPUT_PATH) as output_file:
        write_jsonl_lines(output_file, cases)

    sibling_cases = sum(1 for case in cases if case["gold_sibling_issue_ids"])
    logger.info("Wrote %d cases to %s", len(cases), OUTPUT_PATH)
    logger.info(
        "Cases with siblings: %d (%.1f%%)",
        sibling_cases,
        100 * sibling_cases / len(cases),
    )
    logger.info(
        "Components (gold set): %s",
        dict(Counter(case["component"] for case in cases).most_common()),
    )


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    asyncio.run(run(os.environ["DATABASE_URL"]))


if __name__ == "__main__":
    main()
