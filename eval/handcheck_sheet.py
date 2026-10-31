"""Write a Markdown sheet for hand-checking a random sample of gold cases.

Fill in the verdict columns by opening each issue and PR on GitHub. The share
of "no" answers is the label-noise estimate for gold_v1.
"""

import asyncio
import json
import os
import random
from pathlib import Path

from dotenv import load_dotenv

from servecopilot.db import create_pool

GOLD_PATH = Path("eval/data/gold_v1.jsonl")
SHEET_PATH = Path("eval/data/handcheck_v1.md")
SAMPLE_SIZE = 20
SEED = 7
REPO_URL = "https://github.com/vllm-project/vllm"


async def pr_titles(database_url, pr_numbers):
    pool = await create_pool(database_url)
    try:
        rows = await pool.fetch(
            "SELECT number, title FROM pull_requests WHERE number = ANY($1)",
            pr_numbers,
        )
    finally:
        await pool.close()
    return {row["number"]: row["title"] for row in rows}


def main():
    load_dotenv()
    with GOLD_PATH.open(encoding="utf-8") as file:
        cases = [json.loads(line) for line in file]
    sample = sorted(
        random.Random(SEED).sample(cases, SAMPLE_SIZE), key=lambda c: c["issue_id"]
    )
    titles = asyncio.run(
        pr_titles(
            os.environ["DATABASE_URL"],
            [pr for case in sample for pr in case["gold_pr_ids"]],
        )
    )

    lines = [
        "# gold_v1 hand check",
        "",
        "For each case open the issue and PR(s). Fill in:",
        "- **Fixes?** yes / partly / no: does the PR actually fix this issue?",
        "- **Component?** yes / no: is the component label right?",
        "",
        "| # | Issue | Fixing PR(s) | Component | Fixes? | Component? | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for index, case in enumerate(sample, 1):
        issue_title = case["query_text"].split("\n", 1)[0][:70].replace("|", "/")
        prs = "<br>".join(
            f"[#{pr}]({REPO_URL}/pull/{pr}) {titles.get(pr, '')[:60].replace('|', '/')}"
            for pr in case["gold_pr_ids"]
        )
        lines.append(
            f"| {index} | [#{case['issue_id']}]({REPO_URL}/issues/{case['issue_id']}) "
            f"{issue_title} | {prs} | {case['component']} |  |  |  |"
        )
    lines += [
        "",
        "## Result",
        "",
        "- Fixes = no: _ / 20 → label noise ≈ _ %",
        "- Fixes = partly: _ / 20",
        "- Component wrong: _ / 20",
        "",
    ]
    SHEET_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {SHEET_PATH}")


if __name__ == "__main__":
    main()
