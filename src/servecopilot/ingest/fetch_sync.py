import json
import logging
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GIT_API_KEY")
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)
DATA_STORE = Path("data/raw/issues.jsonl")
QUERY = """
query($cursor: String) {
    rateLimit {
        cost
        remaining
    }

  repository(owner: "vllm-project", name: "vllm") {
    issues(
      first: 100
      after: $cursor
      states: CLOSED
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      nodes {
        number
        title
        body
        createdAt
        closedAt
        labels(first: 20) {
          nodes {
            name
          }
        }
        closedByPullRequestsReferences(first: 10) {
            nodes {
                number
                mergedAt
            }
            }
      }

      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""

MIN_DOCS = 500


def write_jsonl(issues, output_path):
    with open(output_path, "w", encoding="utf-8") as file:
        file.writelines(
            json.dumps(issue, ensure_ascii=False) + "\n" for issue in issues
        )


def parse_issue(issue):
    fixing_prs = []

    for pr in issue["closedByPullRequestsReferences"]["nodes"]:
        if pr["mergedAt"] is not None:
            fixing_prs.append(pr["number"])

    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue["body"],
        "labels": [label["name"] for label in issue["labels"]["nodes"]],
        "created_at": issue["createdAt"],
        "closed_at": issue["closedAt"],
        "fixing_prs": fixing_prs,
    }


def check_graphql_errors(result):
    if "errors" in result:
        for error in result["errors"]:
            logger.error("GraphQL error: %s", error.get("message"))

        raise RuntimeError("GitHub GraphQL request failed")


def main():
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    all_issues = []
    cursor = None
    request_count = 0

    start_time = time.perf_counter()

    while len(all_issues) < MIN_DOCS:
        response = httpx.post(
            GITHUB_GRAPHQL_URL,
            headers=headers,
            json={
                "query": QUERY,
                "variables": {
                    "cursor": cursor,
                },
            },
            timeout=30,
        )
        request_count += 1
        response.raise_for_status()
        result = response.json()
        check_graphql_errors(result)
        rate_limit = result["data"]["rateLimit"]

        logger.info(
            "GraphQL request cost=%d remaining=%d",
            rate_limit["cost"],
            rate_limit["remaining"],
        )

        issues = result["data"]["repository"]["issues"]
        all_issues.extend(issues["nodes"])

        logger.info("Fetched %d issues", len(all_issues))

        if not issues["pageInfo"]["hasNextPage"]:
            break

        cursor = issues["pageInfo"]["endCursor"]

    logger.info("Total issues fetched: %d", len(all_issues))
    parsed_issues = [parse_issue(issue) for issue in all_issues]
    logger.info("Parsed %d issues", len(parsed_issues))
    # saving the issues into jsonl
    output_path = DATA_STORE

    write_jsonl(parsed_issues, output_path)

    logger.info("Wrote %d issues to %s", len(parsed_issues), output_path)

    logger.info("Api calls made for %d is %d  ", MIN_DOCS, request_count)
    elapsed_time = time.perf_counter() - start_time

    logger.info(
        "Total fetch time: %.2f seconds",
        elapsed_time,
    )


if __name__ == "__main__":
    main()
